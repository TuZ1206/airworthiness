"""Offline import of exact web.run open-response strings (no network requests).

Public API: parse_remote_responses(url, responses) returns header metadata and
``lines: {number: (zero_based_page_or_None, text)}``; validate_remote_snapshot
returns that metadata plus selected ``text``, ``method``, ``non_text_elements``.
Neither function writes files. import_remote_snapshot(root, snapshot) validates
everything first, binds explicit source_ids to current CSV rows, and returns the
merged manifest. All validation failures raise ValueError without writing.

HTML bounds are inclusive, caller-selected article bounds, not proof of complete
legal content. PDF requires every declared line and page. Tool provenance is
structurally checked, not cryptographically authenticated; identity_evidence
binds explicit CSV hash/code/date and traceable version quotations through the
shared cached_import validator, always pending review. No original
HTTP/PDF bytes are available. Serialized snapshot and Markdown have separate
hashes. Known link labels are unwrapped without inventing hrefs; images become
counted placeholders. Other tool artifacts are rejected in selected content.

Persistence is single-writer: files are individually atomic, not a multi-file
transaction. Do not run alongside acquire or another importer. Historical
report requests/results remain historical; counts describe the merged manifest,
unique_url_counts the best available kind per current CSV landing URL.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .acquire import NOTICE, RANK, _existing, load_sources
from .acquire_http import atomic_write, canonical_url, digest, now, write_json
from .cached_import import validate_identity_evidence

LINE = re.compile(r"^L(\d+)(?:@P(\d+))?: ?", re.M)
REFERENCE = r"turn[\w.-]*?(?:view|fetch)\d+"
CITATION = rf"(?:cite{REFERENCE}|【{REFERENCE}】)"
LINK = re.compile(r"cite\d+†([^\n]+)|【\d+†([^【】\n]+)】")
PLACEHOLDER = "[原文包含图像/公式，见官方原文]"
ERROR = re.compile(r"access denied|request blocked|(?:403|404|502|503)\s*(?:forbidden|not found|bad gateway|service unavailable)"
                   r"|internal (?:server )?error|failed to fetch|timeout fetching|页面不存在|访问被拒绝|安全验证|验证码"
                   r"|output (?:is )?truncated|\d+ tokens? truncated|\[truncated\]|搜索摘要[：:]", re.I)
ARTIFACT = re.compile(r"[]|【(?:turn|\d+†)|\[(?:Input|Button|Select|Image)(?:\s|:|\])", re.I)


def _one(pattern, header, label):
    matches = re.findall(pattern, header, re.I)
    # Count field names too, so a malformed duplicate cannot evade the pattern.
    fields = re.findall(re.escape(pattern.split(":", 1)[0]) + ":", header, re.I)
    if len(matches) != 1 or len(fields) != 1:
        raise ValueError(f"Missing or repeated {label} in response header")
    return matches[0]


def parse_remote_responses(url: str, responses: list[str]) -> dict:
    """Parse actual open windows; gaps are allowed here, conflicts never are.

    Only physical line starts delimit records; embedded Lxx text remains literal.
    Pure inline response strings are rejected as ambiguous. Internal/trailing
    whitespace is preserved. Overlap equality includes text and PDF page identity.
    """
    url = canonical_url(url)
    if not isinstance(responses, list) or not responses:
        raise ValueError("responses must be a nonempty list of actual strings")
    combined, metadata = {}, None
    for raw in responses:
        if not isinstance(raw, str):
            raise ValueError("Each response must be an actual string")
        parts = raw.replace("\r\n", "\n").split("\n", 2)
        if len(parts) != 3:
            raise ValueError("Missing response header or numbered lines")
        heading, header, body = parts
        match = re.fullmatch(r"(?:(.+?) )?\((https?://[^\n]+)\)", heading)
        if not match or canonical_url(match[2]) != url:
            raise ValueError("Response header URL does not match the official snapshot URL")
        title = match[1] or ""
        if ERROR.search(heading) or ARTIFACT.search(heading):
            raise ValueError("Error page or tool artifact in title")
        if not re.match(CITATION + r"\s+\[wordlim:\s*\d+\]", header):
            raise ValueError("Expected an open response reference, not a search summary")
        media = _one(r"Content type:\s*([^;\s]+)", header, "content type").lower()
        total = int(_one(r"Total lines:\s*(\d+)(?=\s*(?:;|$))", header, "total lines"))
        if media not in {"text/html", "application/pdf"} or total < 1:
            raise ValueError("Unsupported content type or invalid total lines")
        is_pdf = media == "application/pdf"
        if not title and not is_pdf:
            raise ValueError("Missing HTML title")
        pages = int(_one(r"Number of pages:\s*(\d+)(?=\s*(?:;|$))", header, "PDF page count")) if is_pdf else 0
        if (is_pdf and pages < 1) or (not is_pdf and urlsplit(url).path.lower().endswith(".pdf")):
            raise ValueError("PDF provenance requires PDF content type and page count")
        if not is_pdf and re.search(r"Number of pages:", header, re.I):
            raise ValueError("HTML response cannot declare PDF pages")
        if "Source:" in header:
            source = _one(r"Source:\s*(?:open|click)\((\{.*?\})\)", header, "open/click source")
            action = re.search(r"Source:\s*(open|click)\(", header)[1]
            try:
                request = json.loads(source)
                ref = request["ref_id"]
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("Invalid open source reference") from exc
            if action == "click" and (type(request.get("id")) is not int or request["id"] < 0):
                raise ValueError("Invalid click link ID")
            # Opening a search result is allowed; a search-summary header is not.
            if not isinstance(ref, str):
                raise ValueError("Invalid source reference")
            if not re.fullmatch(r"turn[\w.-]*?(?:view|fetch|search)\d+", ref):
                source_url = canonical_url(ref)  # click's parent may differ from the destination.
                if action == "open" and source_url != url:
                    raise ValueError("Conflicting open source URL")
            if action not in {"open", "click"}:
                raise ValueError("Conflicting open source URL")
        current = dict(url=url, title=title or "官方PDF逐页提取", content_type=media, total_lines=total, page_count=pages)
        if metadata is not None and current != metadata:
            raise ValueError("Inconsistent title, content type, total lines or page count across windows")
        metadata = current
        if "\n" not in body.rstrip("\n") and re.search(r"\sL\d+(?:@P\d+)?:", body):
            raise ValueError("Ambiguous inline lines; physical newline boundaries required")
        matches = list(LINE.finditer(body))
        if not matches or matches[0].start() != 0:
            raise ValueError("Missing numbered lines or unnumbered response preamble")
        previous_number = -1
        for index, match in enumerate(matches):
            number = int(match[1])
            page = int(match[2]) if match[2] is not None else None
            if not previous_number < number < total:
                raise ValueError("Out-of-order or out-of-range response line")
            previous_number = number
            if (is_pdf and (page is None or not 0 <= page < pages)) or (not is_pdf and page is not None):
                raise ValueError("Invalid or missing PDF page marker")
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            value = body[match.end():end]
            if value.endswith("\n"):
                value = value[:-1]
            if "\n" in value or "\r" in value:
                raise ValueError("Unnumbered continuation or truncation in response")
            if ERROR.search(value):
                raise ValueError(f"Error page or truncated response at L{number}")
            if number in combined and combined[number] != (page, value):
                raise ValueError(f"Conflicting overlapping line L{number}")
            combined[number] = (page, value)
    return dict(metadata, lines=combined)


def _visible(value):
    count = 0

    def replace(match):
        nonlocal count
        label = match[1] if match[1] is not None else match[2]
        if re.match(r"Image(?:\b|:)", label, re.I):
            count += 1
            return PLACEHOLDER
        return label

    text = LINK.sub(replace, value)
    if ARTIFACT.search(text):
        raise ValueError("Selected body contains unsupported navigation/tool markers")
    return text, count


def validate_remote_snapshot(snapshot: dict, *, root=None) -> dict:
    """Validate snapshot shape, official evidence and inclusive merged coverage.

    Identity schema is documented in cached_import. Supplying root additionally
    verifies current CSV bindings and enables hashed-cache version evidence.
    PDF bounds must be 0..total_lines-1 and cover every page 0..page_count-1.
    non_text_elements counts image occurrences after deduplicating overlap.
    """
    required = {"url", "source_ids", "responses", "line_start", "line_end", "captured_at", "identity_evidence"}
    if not isinstance(snapshot, dict) or not required <= snapshot.keys():
        raise ValueError("Missing required snapshot fields")
    ids = snapshot["source_ids"]
    if (not isinstance(ids, list) or not ids or any(not isinstance(s, str) or not s.strip() for s in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("source_ids must be a nonempty list of distinct IDs")
    try:
        captured = datetime.fromisoformat(snapshot["captured_at"])
        if captured.utcoffset() is None:
            raise ValueError("Timezone required")
    except (ValueError, TypeError) as exc:
        raise ValueError("captured_at must be an ISO timestamp with timezone") from exc
    url = canonical_url(snapshot["url"])
    evidence = snapshot["identity_evidence"]
    if (not isinstance(evidence, dict) or not isinstance(evidence.get("note"), str) or not evidence["note"].strip()
            or not isinstance(evidence.get("urls"), list) or not evidence["urls"]):
        raise ValueError("identity_evidence requires official URLs and a same-version note")
    if url not in {canonical_url(u) for u in evidence["urls"]}:
        raise ValueError("identity_evidence must include the actual URL")
    if urlsplit(url).hostname == "std.samr.gov.cn":
        raise ValueError("Standard status pages are metadata, not importable full-body snapshots")
    parsed = parse_remote_responses(url, snapshot["responses"])
    start, end = snapshot["line_start"], snapshot["line_end"]
    if type(start) is not int or type(end) is not int or not 0 <= start <= end < parsed["total_lines"]:
        raise ValueError("Invalid inclusive line bounds")
    selected = sorted(n for n in parsed["lines"] if start <= n <= end)
    if len(selected) != end - start + 1:
        raise ValueError("Missing lines in selected body; truncated content cannot be imported")
    is_pdf = parsed["content_type"] == "application/pdf"
    if is_pdf:
        pages = [parsed["lines"][n][0] for n in selected]
        if (start != 0 or end != parsed["total_lines"] - 1 or pages != sorted(pages)
                or set(pages) != set(range(parsed["page_count"]))):
            raise ValueError("PDF requires all lines and all pages in document order")
    chunks, non_text, current_page, visible = [], 0, None, []
    for number in selected:
        page, raw = parsed["lines"][number]
        text, count = _visible(raw)
        non_text += count
        visible.append(text)
        if is_pdf and page != current_page:
            chunks.append(("\n" if chunks else "") + f"## 第 {page + 1} 页\n")
            current_page = page
        chunks.append(text)
    if not "".join(visible).strip():
        raise ValueError("Selected body is empty")
    proof_text = "\n".join([parsed["title"]] + [value for _, (_, value) in sorted(parsed["lines"].items())])
    records = validate_identity_evidence(root, url, ids, evidence, response_text=proof_text)
    return dict(parsed, text="\n".join(chunks), non_text_elements=non_text,
                source_records=records,
                text_chars=len("\n".join(visible).replace(PLACEHOLDER, "")),
                method="web-tool-pdf-text" if is_pdf else "web-tool-html-text")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _keep(root, previous, row, new):
    if (not previous or previous.get("source_sha256") != row["sha256"]
            or previous.get("landing_url") != row["url"]):
        return False
    old = _existing(root, previous)
    if old is None:
        return False
    rank = RANK[old["content_kind"]]
    if rank != RANK[new["content_kind"]]:
        return rank > RANK[new["content_kind"]]
    # Tool text has no original bytes. More characters/pages cannot justify
    # discarding existing raw provenance (single/multi-PDF, archive, OCR, HTML).
    raw_hash = old.get("original_sha256")
    if isinstance(raw_hash, str) and re.fullmatch(r"[0-9a-fA-F]{64}", raw_hash):
        return True
    # Missing placeholders do not prove their image/formula content was recovered.
    if old.get("non_text_elements", 0) != new["non_text_elements"]:
        return True
    before = old.get("text_chars", 0), old.get("page_count", 0)
    after = new["text_chars"], new["page_count"]
    return not (all(a >= b for a, b in zip(after, before)) and after != before)


def import_remote_snapshot(root: Path, snapshot: dict) -> dict:
    """Persist one validated snapshot and merge only strictly better source entries.

    Writes .cache/acquisition/remote/<snapshot SHA>.json, content-addressed
    data/acquired/documents/*.md, manifest.json, report.json and appends attempts.
    Original CSVs/documents, unselected entries, and earlier evidence are untouched.
    Run parse/validate alone for a read-only preflight on the real repository.
    """
    root = Path(root).resolve()
    checked = validate_remote_snapshot(snapshot, root=root)
    rows = load_sources(root)
    records = checked["source_records"]
    output = root / "data/acquired"
    manifest, report = _load(output / "manifest.json"), _load(output / "report.json")
    encoded = (json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    snapshot_hash = digest(encoded)
    snapshot_path = f".cache/acquisition/remote/{snapshot_hash}.json"
    note = (NOTICE + " 远端web工具逐行文字；未取得原始HTML/PDF字节，original_sha256留空。"
            " 同文件同版本依据为提交者提供，待人工核验；行覆盖不代表版式、图表或法律内容完整。"
            f" 原文包含图像/公式占位 {checked['non_text_elements']} 项，未提取其内容。")
    body = (f"# {checked['title']}\n\n> {note}\n\n- 官方原文：{checked['url']}\n"
            f"- 内容类型：extracted\n- 工具快照 SHA-256：{snapshot_hash}\n\n"
            f"## 正文\n\n{checked['text']}\n").encode("utf-8")
    entry = dict(content_kind="extracted", path=f"data/acquired/documents/remote-{digest(body)}.md",
                 url=checked["url"], actual_url=checked["url"], sha256=digest(body), original_sha256="",
                 crawled_at=snapshot["captured_at"], method=checked["method"], page_count=checked["page_count"],
                 note=note, error="", review_status="pending", text_chars=checked["text_chars"],
                 tool_snapshot_sha256=snapshot_hash, snapshot_path=snapshot_path,
                 source_lines=[snapshot["line_start"], snapshot["line_end"]], total_lines=checked["total_lines"],
                 non_text_elements=checked["non_text_elements"], identity_evidence=snapshot["identity_evidence"])
    updated, preserved = [], []
    event = dict(url=checked["url"], actual_url=checked["url"], status="remote-text-retrieved",
                 crawled_at=snapshot["captured_at"], imported_at=now(), run_id=uuid4().hex,
                 method=checked["method"], tool_snapshot_sha256=snapshot_hash, snapshot_path=snapshot_path,
                 source_ids=list(snapshot["source_ids"]), identity_evidence=snapshot["identity_evidence"],
                 non_text_elements=checked["non_text_elements"])
    for row in records:
        sid = row["source_id"]
        previous = manifest.get(sid, {})
        if _keep(root, previous, row, entry):
            preserved.append(sid)
        else:
            updated.append(sid)
            manifest[sid] = dict(entry, landing_url=row["url"], source_sha256=row["sha256"],
                                 attempts=previous.get("attempts", []) + [dict(event)],
                                 previous_acquisition_error=previous.get("error", ""))
    event.update(updated_source_ids=updated, preserved_source_ids=preserved, preserved_existing=not updated)
    url_kinds = {}
    for row in rows:
        url = canonical_url(row["url"])
        kind = manifest.get(row["source_id"], {}).get("content_kind", "failed")
        if RANK[kind] >= RANK[url_kinds.get(url, "failed")]:
            url_kinds[url] = kind
    report.update(counts=dict(Counter(e["content_kind"] for e in manifest.values())), source_records=len(rows),
                  unique_source_urls=len(url_kinds), unique_url_counts=dict(Counter(url_kinds.values())),
                  remote_imported_at=event["imported_at"])
    report.setdefault("remote_imports", []).append(event)
    # Prepare every value before the first write; content-addressed paths protect aliases.
    atomic_write(root / snapshot_path, encoded)
    if updated:
        atomic_write(root / entry["path"], body)
    write_json(output / "manifest.json", dict(sorted(manifest.items())))
    journal = output / "attempts.jsonl"
    legacy = report.get("requests", []) if not journal.exists() else []
    with journal.open("ab+") as handle:
        if handle.tell():
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
        for record in [*legacy, event]:
            handle.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
    write_json(output / "report.json", report)
    return manifest

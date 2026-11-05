"""Single-writer, offline import of Fetcher cache originals. No alias inference.

import_cached_original(root, url, source_ids, identity_evidence, note='') returns
the merged manifest. read_cached_original(root, url) returns a verified Download
without writes. Cache misses, unsupported archives and validation errors raise
ValueError before writing. Existing extraction classifications are retained;
HTML body images downgrade fulltext to extracted, never upgrade metadata.

Shared identity schema (also used by remote_import):
  urls: [actual URL, each CSV landing URL], note: nonempty manual assessment,
  source_bindings: {source_id: {source_sha256, document_code, publish_date}},
  version_evidence: [{source_ids: [...], url, quote, kind: 'cache', cache_url,
                      original_sha256}] or [{source_ids: [...], url, quote,
                                             kind: 'response'}].
All three binding values must exactly match the current CSV. Cross-URL imports
require a verified quotation for each selected source, containing its document
code or publication date. Only whitespace/date notation is normalized. This
checks traceability, not legal applicability or the completeness of attachments.
Cache evidence is checked against original bytes; response evidence is supplied
by the validated remote parser. With root=None only declared bindings can be
checked, and cache evidence is unavailable; import always supplies the root.

all_pages means this PDF's pages were processed, not that separate appendices
were acquired. No OCR or archive extraction is performed. Cache originals are
never rewritten. Output files are individually atomic, not a multi-file
transaction; do not import concurrently with acquisition or another writer.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from bs4 import BeautifulSoup

from .acquire import RANK, _existing, extract_html, extract_pdf, load_sources
from .acquire_http import Fetcher, atomic_write, canonical_url, digest, now, write_json

PLACEHOLDER = "[原文包含图像/公式，见官方原文]"
BINDINGS = ("source_sha256", "document_code", "publish_date")
MAX_MEMBER_BYTES = 256 * 1024 * 1024


def _paths(root, url):
    root = Path(root).resolve()
    directory = root / ".cache/acquisition"
    key = digest(canonical_url(url).encode())
    paths = [directory / (key + suffix) for suffix in (".bin", ".json")]
    if (not directory.resolve().is_relative_to(root)
            or any(p.resolve().parent != directory.resolve() for p in paths)):
        raise ValueError("Cache paths escape the acquisition cache")
    return directory, key, paths


def read_cached_original(root: Path, url: str):
    """Read only the exact canonical URL's hashed .bin/.json cache pair."""
    url = canonical_url(url)
    directory, key, paths = _paths(root, url)
    reader = SimpleNamespace(cache_dir=directory, refresh=False, max_bytes=32 * 1024 * 1024)
    # Fetcher.__init__ writes .gitignore. _cached needs only these three fields.
    try:
        download = Fetcher._cached(reader, url, key)
        if download is None or not download.data or not all(p.is_file() for p in paths):
            raise ValueError("Cache pair is missing or its URL/raw hash does not verify")
        if not isinstance(download.content_type, str):
            raise ValueError("Invalid cached content type")
        if datetime.fromisoformat(download.crawled_at).utcoffset() is None:
            raise ValueError("Cached timestamp requires timezone")
    except (TypeError, AttributeError, OSError) as exc:
        raise ValueError("Malformed cache pair") from exc
    return download


def _clean_soup(data):
    soup = BeautifulSoup(data, "html.parser")
    for node in soup.select("script,style,noscript,nav,aside,header,footer,form,iframe,.share,.print,.bdsharebuttonbox"):
        node.decompose()
    for node in soup.select('[hidden],[aria-hidden="true"],[style]'):
        if node.attrs is not None and (node.has_attr("hidden") or node.get("aria-hidden") == "true"
                                       or re.search(r"display\s*:\s*none", node.get("style", ""), re.I)):
            node.decompose()
    return soup


def _is_pdf(download):
    return download.data.lstrip().startswith(b"%PDF-")


def _extract(download):
    if _is_pdf(download):
        result, count = extract_pdf(download.data), 0
        if result.content_kind == "failed":
            raise ValueError(result.note)
        result.note += " 已遍历页数仅针对本PDF；单独附录、附件未自动合并，不能据此称文件完整。"
    elif (download.content_type.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}
          and not urlsplit(download.url).path.lower().endswith(".pdf")):
        result = extract_html(download.data, download.url)
        if result.content_kind == "failed":
            raise ValueError(result.note)
        count = result.non_text_elements
    else:
        raise ValueError("Only cached raw PDF/HTML is supported; no archive or media fallback")
    return result, count


def _space(value):
    return " ".join(value.split())


def _version_matches(quote, binding):
    code = binding["document_code"]
    compact = re.sub(r"[-\s]", "", code).casefold()
    family = re.fullmatch(r"(ccar\d+)r\d+", compact)
    if family:
        mentioned = re.findall(r"CCAR[-\s]*\d+[-\s]*R\d+", quote, re.I)
        versions = [re.sub(r"[-\s]", "", value).casefold() for value in mentioned]
        if any(value.startswith(family[1] + "r") and value != compact for value in versions):
            return False
    if compact and re.search(r"(?<![A-Za-z0-9])" + r"[-\s]*".join(map(re.escape, compact))
                             + r"(?![A-Za-z0-9])", quote, re.I):
        return True
    dates = re.sub(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                   lambda m: f"{int(m[1]):04}-{int(m[2]):02}-{int(m[3]):02}", quote)
    return bool(binding["publish_date"] and binding["publish_date"] in dates)


def _member_text(root, download, proof):
    if not download.data.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        raise ValueError("Member evidence requires verified RAR magic")
    member = proof.get("member")
    if (not isinstance(member, str) or not member.lower().endswith(".pdf")
            or re.search(r"[\\/:\x00-\x1f]", member) or member in {".", ".."}):
        raise ValueError("Member must be an explicit PDF basename, never a path")
    directory, key, _ = _paths(root, proof.get("cache_url", proof["url"]))
    child = directory / "archive" / (key + ".pdf")
    if child.resolve().parent != (directory.resolve() / "archive"):
        raise ValueError("Archive member escapes the fixed cache directory")
    try:
        with child.open("rb") as handle:
            if child.stat().st_size >= MAX_MEMBER_BYTES:
                raise ValueError("Archive member must be smaller than 256 MiB")
            data = handle.read(MAX_MEMBER_BYTES)
    except OSError as exc:
        raise ValueError("Verified fixed archive member is unavailable") from exc
    if (len(data) >= MAX_MEMBER_BYTES or not data.startswith(b"%PDF-")
            or digest(data) != proof.get("member_sha256")):
        raise ValueError("Archive member PDF magic/size/SHA-256 mismatch")
    return extract_pdf(data).markdown


def _cache_evidence_text(root, download, proof):
    selectors = [key for key in ("member", "meta_name", "script_var") if key in proof]
    if len(selectors) > 1:
        raise ValueError("Use one evidence selector per proof")
    if "member" in proof:
        return _member_text(root, download, proof)
    if _is_pdf(download) and not selectors:
        return extract_pdf(download.data).markdown
    if "html" not in download.content_type.lower() or _is_pdf(download):
        raise ValueError("Version evidence is not raw PDF/HTML")
    soup = BeautifulSoup(download.data, "html.parser")
    if "meta_name" in proof:
        if not isinstance(proof["meta_name"], str) or not proof["meta_name"].strip():
            raise ValueError("meta_name must explicitly select an official named field")
        values = [tag.get("content", "") for tag in soup.find_all("meta", attrs={"name": proof["meta_name"]})]
    elif "script_var" in proof:
        host = urlsplit(download.url).hostname
        variable = proof["script_var"]
        if variable not in ("wenhao", "buhao") or not (host == "caac.gov.cn" or host.endswith(".caac.gov.cn")):
            raise ValueError("Only CAAC's static wenhao/buhao metadata is allowed")
        values = []
        for script in soup.head.find_all("script", src=False) if soup.head else []:
            text = script.get_text()
            # Deliberately narrow: no escapes, templates, comments or computed expressions.
            if "/*" in text or "`" in text:
                continue
            found = re.findall(r'''(?:^|\n)\s*var\s+''' + variable + r'''\s*=\s*(["'])([^"'\\\r\n]*)\1\s*;''', text)
            values.extend(value for _, value in found)
    else:
        return _clean_soup(download.data).get_text(" ", strip=True)
    if len(values) != 1 or not values[0].strip():
        raise ValueError("Metadata evidence requires one unambiguous static value")
    return values[0]


def validate_identity_evidence(root, actual_url, source_ids, evidence, *, response_text=None):
    """Shared read-only binding and quoted-version validation; return selected rows."""
    actual_url = canonical_url(actual_url)
    if (not isinstance(source_ids, list) or not source_ids
            or any(not isinstance(s, str) or not s.strip() for s in source_ids)
            or len(set(source_ids)) != len(source_ids)):
        raise ValueError("source_ids must be explicit distinct IDs")
    if (not isinstance(evidence, dict) or not isinstance(evidence.get("note"), str) or not evidence["note"].strip()
            or not isinstance(evidence.get("urls"), list) or not evidence["urls"]
            or not isinstance(evidence.get("source_bindings"), dict)):
        raise ValueError("Identity requires official URLs, note and explicit source_bindings")
    urls = {canonical_url(u) for u in evidence["urls"]}
    if actual_url not in urls:
        raise ValueError("Identity evidence omits the actual URL")
    by_id = {row["source_id"]: row for row in load_sources(Path(root))} if root is not None else None
    records = []
    for sid in source_ids:
        binding = evidence["source_bindings"].get(sid)
        if (not isinstance(binding, dict) or any(not isinstance(binding.get(k), str) for k in BINDINGS)
                or not re.fullmatch(r"[0-9a-fA-F]{64}", binding["source_sha256"])):
            raise ValueError(f"Missing explicit source_sha256/document_code/publish_date binding: {sid}")
        if by_id is not None:
            row = by_id.get(sid)
            if row is None or any(binding[k] != row.get("sha256" if k == "source_sha256" else k) for k in BINDINGS):
                raise ValueError(f"CSV binding mismatch or unknown source: {sid}")
            if canonical_url(row["url"]) not in urls:
                raise ValueError(f"Identity evidence omits CSV landing URL: {sid}")
        else:
            row = dict(binding, sha256=binding["source_sha256"], source_id=sid, url=actual_url)
        records.append(row)
    cross_ids = {row["source_id"] for row in records if canonical_url(row["url"]) != actual_url}
    if root is None and len(urls) > 1:
        cross_ids = set(source_ids)
    proofs = evidence.get("version_evidence", [])
    if not isinstance(proofs, list):
        raise ValueError("version_evidence must be a list")
    proven = set()
    for proof in proofs:
        if (not isinstance(proof, dict) or not isinstance(proof.get("quote"), str) or not proof["quote"].strip()
                or not isinstance(proof.get("source_ids"), list)
                or any(not isinstance(s, str) for s in proof["source_ids"])):
            raise ValueError("Invalid quoted version evidence")
        proof_url = canonical_url(proof.get("url"))
        if proof_url not in urls:
            raise ValueError("Version evidence URL is not among declared official URLs")
        if proof.get("kind") == "response":
            if proof_url != actual_url or response_text is None:
                raise ValueError("Version quote needs the actual validated response")
            text = response_text
        elif proof.get("kind") == "cache":
            if root is None:
                raise ValueError("root is required to verify cached version evidence")
            download = read_cached_original(root, proof.get("cache_url", proof_url))
            if download.url != proof_url or download.original_sha256 != proof.get("original_sha256"):
                raise ValueError("Version evidence URL/raw hash mismatch")
            text = _cache_evidence_text(root, download, proof)
        else:
            raise ValueError("Version evidence kind must be response or cache")
        if _space(proof["quote"]) not in _space(text):
            raise ValueError("Version quote not found in verified original content")
        for sid in set(proof["source_ids"]) & set(source_ids):
            if by_id is not None and proof_url not in {actual_url, canonical_url(by_id[sid]["url"])}:
                raise ValueError(f"Version evidence is unrelated to the actual/landing URL: {sid}")
            if not _version_matches(proof["quote"], evidence["source_bindings"][sid]):
                raise ValueError(f"Quote lacks the bound document code/publication date: {sid}")
            proven.add(sid)
    if not cross_ids <= proven:
        raise ValueError("Cross-URL import needs traceable version evidence for every source")
    return records


def _raw_pdf(entry):
    return (entry.get("content_kind") == "extracted" and entry.get("method") == "pymupdf-page-text"
            and bool(re.fullmatch(r"[0-9a-fA-F]{64}", entry.get("original_sha256", "")))
            and entry.get("page_count", 0) > 0 and entry.get("all_pages", True))


def _keep(root, previous, row, new):
    if (previous.get("source_sha256") != row["sha256"] or previous.get("landing_url") != row["url"]
            or not _existing(root, previous)):
        return False
    if RANK[previous["content_kind"]] != RANK[new["content_kind"]]:
        return RANK[previous["content_kind"]] > RANK[new["content_kind"]]
    if _raw_pdf(previous) != _raw_pdf(new):
        return _raw_pdf(previous)
    # An unexplained change in image count is not evidence of improved content.
    if previous.get("non_text_elements", 0) != new["non_text_elements"]:
        return True
    before = previous.get("text_chars", 0), previous.get("page_count", 0)
    after = new["text_chars"], new["page_count"]
    return not (all(a >= b for a, b in zip(after, before)) and after != before)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def import_cached_original(root, url, source_ids, identity_evidence, note=""):
    """Import exact cached bytes; return merged manifest, preserving better entries."""
    root, url = Path(root).resolve(), canonical_url(url)
    if not isinstance(note, str):
        raise ValueError("note must be text")
    download = read_cached_original(root, url)
    records = validate_identity_evidence(root, download.url, source_ids, identity_evidence)
    extraction, non_text = _extract(download)
    _, _, (raw, meta) = _paths(root, url)
    full_note = extraction.note + " 同文件同版本由调用方核对，身份依据待人工复核。" + (" " + note if note else "")
    body = (f"# {extraction.title or '官方PDF逐页提取'}\n\n> {full_note}\n\n"
            f"- 官方原文：{download.url}\n- 内容类型：{extraction.content_kind}\n"
            f"- 原文 SHA-256：{download.original_sha256}\n\n## 正文\n\n{extraction.markdown}\n").encode("utf-8")
    entry = dict(content_kind=extraction.content_kind, path=f"data/acquired/documents/cached-{digest(body)}.md",
                 sha256=digest(body), original_sha256=download.original_sha256, request_url=url,
                 url=download.url, actual_url=download.url, redirects=download.redirects, crawled_at=download.crawled_at,
                 method=extraction.method, acquisition_method="cached-original", page_count=extraction.page_count,
                 all_pages=extraction.method == "pymupdf-page-text", review_status="pending", note=full_note, error="",
                 raw_path=raw.relative_to(root).as_posix(), cache_metadata_path=meta.relative_to(root).as_posix(),
                 cache_metadata_sha256=digest(meta.read_bytes()), identity_evidence=identity_evidence,
                 text_chars=len(extraction.markdown.replace(PLACEHOLDER, "")), non_text_elements=non_text)
    output = root / "data/acquired"
    manifest, report = _load(output / "manifest.json"), _load(output / "report.json")
    event = dict(request_url=url, url=download.url, actual_url=download.url, status="cache-imported",
                 original_sha256=download.original_sha256, raw_path=entry["raw_path"], method=extraction.method,
                 content_kind=extraction.content_kind, source_ids=list(source_ids), identity_evidence=identity_evidence,
                 crawled_at=download.crawled_at, imported_at=now(), run_id=uuid4().hex)
    updated, preserved = [], []
    for row in records:
        sid = row["source_id"]
        old = manifest.get(sid, {})
        if _keep(root, old, row, entry):
            preserved.append(sid)
        else:
            updated.append(sid)
            manifest[sid] = dict(entry, landing_url=row["url"], source_sha256=row["sha256"],
                                 attempts=old.get("attempts", []) + [dict(event)], previous_acquisition_error=old.get("error", ""))
    event.update(updated_source_ids=updated, preserved_source_ids=preserved)
    rows, url_kinds = load_sources(root), {}
    for row in rows:
        landing = canonical_url(row["url"])
        kind = manifest.get(row["source_id"], {}).get("content_kind", "failed")
        if RANK[kind] >= RANK[url_kinds.get(landing, "failed")]:
            url_kinds[landing] = kind
    report.update(counts=dict(Counter(e["content_kind"] for e in manifest.values())), source_records=len(rows),
                  unique_source_urls=len(url_kinds), unique_url_counts=dict(Counter(url_kinds.values())),
                  cached_imported_at=event["imported_at"])
    report.setdefault("cached_imports", []).append(event)
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

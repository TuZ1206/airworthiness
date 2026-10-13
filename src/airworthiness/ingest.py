"""Read immutable chapter inputs and optional independently acquired originals."""
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from .reading import clean_extracted_text

SOURCE_FIELDS = "source_id,title,document_code,document_status,publish_date,url,sha256,crawled_at,review_status".split(",")
KINDS = {"fulltext", "extracted", "excerpt", "metadata"}


def official_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme in {"http", "https"} and (host == "gov.cn" or host.endswith(".gov.cn")) and not parsed.username


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classify_original(text):
    if "## 正文" in text and ("机械提取" in text or "原PDF SHA-256" in text):
        return "extracted"
    if any(x in text for x in ("std.samr.gov.cn", "状态页审查摘录", "状态信息", "仅登记", "状态记录", "不足以逐条", "未取得政府渠道受控全文")):
        return "metadata"
    return "excerpt"


def body_only(text):
    match = re.search(r"^## 正文\s*$", text, re.M) or re.search(r"^## .+", text, re.M)
    if match:
        return text[match.start():]
    lines = text.splitlines()
    start = 0
    while start < len(lines) and (not lines[start].strip() or lines[start].startswith(("# ", "- ", "> "))):
        start += 1
    return "\n".join(lines[start:])


def acquisition_reason(entry):
    """Keep raw diagnostics in the manifest, but explain reading limits plainly."""
    error = entry.get("error", "")
    if "SSL" in error or "Connection" in error or "timeout" in error.lower():
        return "官网连接未成功，本次未获取全文；可稍后重新采集。"
    if "403" in error or "429" in error:
        return "官网限制自动访问，本次未获取全文。"
    if "404" in error:
        return "官方链接当前未返回文档，需核对链接。"
    return entry.get("note") or ("自动采集未取得可确认的正文，需人工核对。" if error else "")


def source_binding_matches(row, entry):
    return entry.get("source_sha256") == row["sha256"] and entry.get("landing_url") == row["url"]


def uploaded_provenance(original, row):
    pdf_hash = re.search(r"原PDF\s*SHA-256[：:]\s*([0-9a-fA-F]{64})", original)
    pdf_url = re.search(r"https?://[^\s)<>]+\.pdf", original, re.I)
    return {"source_id": row["source_id"], "markdown_sha256": row["sha256"], "pdf_sha256": pdf_hash[1].lower() if pdf_hash else "", "pdf_url": pdf_url[0] if pdf_url else "", "crawled_at": row["crawled_at"], "method": "uploaded-source"}


def share_originals(documents):
    """Reuse only exact official-URL matches; never merge merely similar titles."""
    groups = defaultdict(list)
    for doc in documents:
        groups[doc["url"]].append(doc)
    for group in groups.values():
        originals = [x for x in group if x["content_kind"] in {"fulltext", "extracted"}]
        if not originals:
            continue
        donor = max(originals, key=lambda x: len(x["body"]))
        for doc in group:
            if doc["content_kind"] in {"excerpt", "metadata"}:
                doc.update(body=donor["body"], content_kind=donor["content_kind"], reused_from=donor["source_id"])
                doc["extraction_note"] = f"与 {donor['source_id']} 的官方链接完全一致，复用其已保存正文。" + donor["extraction_note"]
                doc["body_provenance"] = donor.get("body_provenance", {"source_id": donor["source_id"], "sha256": donor.get("sha256", ""), "acquisition": donor["acquisition"]})


def load_inputs(root):
    root = Path(root).resolve()
    chapter_root = root / "data/chapters"
    chapters = json.loads((chapter_root / "catalog.json").read_text(encoding="utf-8"))
    manifest_path = root / "data/acquired/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if "sources" in manifest:
        manifest = manifest["sources"]
    documents, terms, errors, issues = [], [], [], []
    ids = set()
    for chapter in chapters:
        folder = chapter_root / chapter["id"]
        rows = read_csv(folder / "sources.csv")
        for row in rows:
            sid = row.get("source_id", "")
            if list(row) != SOURCE_FIELDS or not re.fullmatch(chapter["id"].upper() + r"-S\d{3}", sid):
                errors.append(f"{chapter['id']}: invalid source schema/ID {sid}")
                continue
            if sid in ids:
                errors.append(f"duplicate source_id: {sid}")
                continue
            ids.add(sid)
            path = folder / "documents" / f"{sid}.md"
            if not path.is_file():
                errors.append(f"{sid}: document missing")
                continue
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                errors.append(f"{sid}: SHA-256 mismatch (check LF line endings)")
            if not official_url(row["url"]):
                errors.append(f"{sid}: source host not allowed")
            if row["document_status"] not in {"effective", "abolished", "unknown"} or row["review_status"] not in {"pending", "approved", "rejected", "update_required"}:
                errors.append(f"{sid}: invalid status")
            original = raw.decode("utf-8-sig")
            kind = classify_original(original)
            body = body_only(original)
            entry = manifest.get(sid, {})
            provenance = uploaded_provenance(original, row)
            body_provenance = provenance
            note = {"excerpt": "当前为整理摘录，不替代官方原文。", "metadata": "当前仅有文件状态或登记信息，未取得受控全文。", "extracted": "由已上传的官方附件机械提取，版式、表格与完整性仍需校对。"}[kind]
            usable = bool(entry.get("path") and entry.get("content_kind") in {"fulltext", "extracted"})
            if usable and not source_binding_matches(row, entry):
                usable = False
                note += " 来源记录已更新，旧采集正文暂不采用，需重新获取并核对。"
                entry = dict(entry, applied=False, skip_reason="source_binding_changed")
                issues.append({"source_id": sid, "kind": "stale_acquisition", "message": "采集记录与当前来源哈希或链接不一致，已回退到上传文档。"})
            if usable:
                acquired = (root / entry["path"]).resolve()
                allowed_root = (root / "data/acquired").resolve()
                if not acquired.is_relative_to(allowed_root) or not acquired.is_file():
                    errors.append(f"{sid}: acquired document path invalid")
                elif not official_url(entry.get("url", "")):
                    errors.append(f"{sid}: acquired URL is not official")
                else:
                    content = acquired.read_bytes()
                    if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
                        errors.append(f"{sid}: acquired document SHA-256 mismatch")
                    else:
                        body = body_only(content.decode("utf-8-sig"))
                        kind = entry["content_kind"]
                        note = entry.get("note") or "已获取官方正文；自动提取的版式、表格与完整性待人工校对。"
                        entry = dict(entry, applied=True)
                        body_provenance = {"source_id": sid, "method": entry.get("method"), "markdown_sha256": entry["sha256"], "original_sha256": entry.get("original_sha256", ""), "url": entry["url"], "crawled_at": entry.get("crawled_at"), "tool_snapshot_sha256": entry.get("tool_snapshot_sha256", "")}
            elif not entry.get("skip_reason") and (entry.get("error") or entry.get("note")):
                note += " 本次获取：" + acquisition_reason(entry)
            if not row["publish_date"]:
                issues.append({"source_id": sid, "kind": "missing_date", "message": "来源台账未提供发布日期，需复核。"})
            documents.append({**row, "chapter_id": chapter["id"], "chapter_title": chapter["title"], "body": clean_extracted_text(body), "content_kind": kind, "extraction_note": note, "acquisition": entry, "uploaded_provenance": provenance, "body_provenance": body_provenance})
        source_ids = {x["source_id"] for x in rows}
        for term in read_csv(folder / "glossary.csv"):
            if term["source_id"] not in source_ids:
                errors.append(f"{term['term_id']}: glossary source missing")
            terms.append({**term, "chapter_id": chapter["id"], "original_anchor_or_url": term["anchor_or_url"], "original_has_page": term["has_page"], "has_page": "false", "anchor_or_url": f"/chapters/{chapter['id']}?source={term['source_id']}", "locator_status": "source_only"})
    by_url = defaultdict(list)
    for row in documents:
        by_url[row["url"]].append(row)
    for group in by_url.values():
        if len({x["document_code"].strip() for x in group}) > 1:
            for row in group:
                issues.append({"source_id": row["source_id"], "kind": "code_conflict", "message": "同一官方链接在不同章节登记的文号不一致，需复核。"})
    by_code = defaultdict(list)
    for row in documents:
        code = re.sub(r"\s+", "", row["document_code"]).upper()
        if code and not any(word in code for word in ("官网", "未列", "未标", "不适用")):
            by_code[code].append(row)
    for group in by_code.values():
        for field, kind, label in (("publish_date", "date_variation", "发布日期"), ("title", "title_variation", "题名"), ("document_status", "status_variation", "有效状态")):
            values = sorted({row[field].strip() for row in group if row[field].strip()})
            if len(values) > 1:
                for row in group:
                    issues.append({"source_id": row["source_id"], "kind": kind, "message": f"同一文号跨章登记的{label}存在差异（{'；'.join(values)}），可能涉及修订、发布通知或记录错误，需核对官方来源。"})
    share_originals(documents)
    return chapters, documents, terms, errors, issues

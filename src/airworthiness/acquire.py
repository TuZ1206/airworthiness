"""Bounded, official-only source acquisition; never edits the chapter corpus.

Run: python -m airworthiness.acquire --root .
Only mechanical extraction is performed. ``fulltext`` means the recognized HTML
article body, NOT professional approval or a guarantee of legal completeness.
PDF text is always ``extracted`` and pending verification. Raw downloads and their
provenance are cached under .cache/acquisition (self-ignored by Git).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pymupdf
from bs4 import BeautifulSoup, NavigableString, Tag

if __package__:
    from .acquire_http import (AcquisitionError, Download, Fetcher, atomic_write, canonical_url, digest, now, write_json)
else:  # Also support python src/airworthiness/acquire.py.
    from acquire_http import (AcquisitionError, Download, Fetcher, atomic_write, canonical_url, digest, now, write_json)


NOTICE = "机械采集结果，待核验；抓取成功不等于专业审核或批准。"
BODY_SELECTORS = (".TRS_Editor", ".TRS_PreAppend", ".article-content", "#UCAP-CONTENT",
                  "#zoom", "#Zoom", ".article_content", "#article-content",
                  ".Article_Content", ".viewTRSContent", ".TRS_UEDITOR", '[data-role="n_content"]')
RANK = {"failed": 0, "metadata": 1, "extracted": 2, "fulltext": 3}
PDF_LOCK = threading.Lock()  # PyMuPDF document operations are not thread-safe.


@dataclass
class Extraction:
    content_kind: str
    markdown: str = ""
    method: str = ""
    page_count: int = 0
    note: str = ""
    title: str = ""
    attachments: list[str] = field(default_factory=list)
    non_text_elements: int = 0


def _markdown(node, base_url):
    if isinstance(node, NavigableString):
        return re.sub(r"[\t\r\n ]+", " ", str(node))
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name == "br":
        return "\n"
    if name == "img":
        return " [原文包含图像/公式，见官方原文] "
    if name == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = tr.find_all(["td", "th"], recursive=False)
            if cells:
                rows.append([re.sub(r"\s+", " ", _markdown(cell, base_url)).strip().replace("|", "\\|") for cell in cells])
        if not rows:
            return ""
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(row) + " |" for row in rows]
        lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
        return "\n\n" + "\n".join(lines) + "\n\n"
    text = "".join(_markdown(child, base_url) for child in node.children)
    if re.fullmatch(r"h[1-6]", name):
        return "\n\n" + "#" * int(name[1]) + " " + text.strip() + "\n\n"
    if name == "a" and node.get("href"):
        try:
            target = canonical_url(urljoin(base_url, node["href"]))
            return f"[{text.strip()}]({target})" if text.strip() else ""
        except ValueError:
            return text
    if name == "li":
        return "\n- " + text.strip() + "\n"
    if name in {"p", "div", "section", "article", "blockquote", "ul", "ol"}:
        return "\n\n" + text.strip() + "\n\n"
    return text


def extract_html(data: bytes, url: str) -> Extraction:
    canonical_url(url)
    soup = BeautifulSoup(data, "html.parser")
    title_tag = soup.find("meta", attrs={"name": re.compile(r"^ArticleTitle$", re.I)})
    title = title_tag.get("content", "") if title_tag else (soup.title.get_text(" ", strip=True) if soup.title else "")
    for unwanted in soup.select("script, style, noscript, nav, aside, header, footer, form, iframe, .share, .print, .bdsharebuttonbox"):
        unwanted.decompose()
    for hidden in soup.select('[hidden], [aria-hidden="true"], [style]'):
        if hidden.attrs is None:  # A hidden ancestor already decomposed this node.
            continue
        if hidden.has_attr("hidden") or hidden.get("aria-hidden") == "true" or re.search(r"display\s*:\s*none", hidden.get("style", ""), re.I):
            hidden.decompose()
    visible = soup.get_text(" ", strip=True)
    if (re.search(r"access denied|request blocked|403 forbidden|404 not found|页面不存在|访问被拒绝|安全验证|验证码", title + " " + visible[:350], re.I)
            and len(visible) < 4000):
        return Extraction("failed", method="html-error-page", title=title, note="官网返回错误页或验证页，未取得正文。")
    attachments = []
    for anchor in soup.select("a[href]"):
        try:
            target = canonical_url(urljoin(url, anchor["href"]))
            if urlsplit(target).path.lower().endswith(".pdf") and target not in attachments:
                attachments.append(target)
        except ValueError:
            continue
    containers = [(selector, soup.select_one(selector)) for selector in BODY_SELECTORS]
    containers = [(s, n) for s, n in containers if n and n.get_text(strip=True)]
    selector, container = max(containers, key=lambda item: len(item[1].get_text()), default=("", None))
    is_standard = urlsplit(url).hostname == "std.samr.gov.cn"
    if is_standard:
        container = soup.select_one(".detail, .standard-detail, .std-detail, .main-content, .container") or container
    if container:
        body = re.sub(r"\n[ \t]+", "\n", _markdown(container, url))
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
    else:
        # Only actual fetched title/metadata; never promote arbitrary page chrome.
        body = "\n\n".join(filter(None, [title] + [m.get("content", "") for m in soup.select('meta[name="description"]')]))
    legal_lines = re.findall(r"(?m)^\s*(?:#+\s*)?(?:第[一二三四五六七八九十百零〇\d]+[条章节]|\d+\.\d+\s)", body)
    substantive = len(body) >= 350 and len(legal_lines) >= 2
    kind = "fulltext" if substantive and not is_standard else "metadata"
    images = len(container.select('img')) if container else 0
    amendment = (container is not None and not is_standard and len(body) >= 350
                 and re.search(r'关于修改.*决定', title)
                 and len(re.findall(r'(?m)^\s*[一二三四五六七八九十]+、将', body)) >= 2
                 and '本决定自' in body)
    if amendment or (images and kind == 'fulltext'):
        kind = 'extracted'
    note = NOTICE
    if is_standard:
        note += " 国家标准平台状态页，仅为标准元数据，不是标准正文。"
    elif kind == "metadata":
        note += " 未识别足够的法规正文；仅保存官网页面元数据或通知内容。"
    else:
        note += " 保存所识别的HTML正文；附件、图像、表格合并单元格及分页完整性仍须核验。"
    if amendment:
        note += " 本页为修改决定，不是修订后的合并全文；独立附件未合并。"
    if images:
        note += f" 原文包含图像/公式占位 {images} 项，未提取其内容。"
    return Extraction(kind, body, "html:" + (selector or "metadata"), note=note, title=title, attachments=attachments, non_text_elements=images)


def extract_pdf(data: bytes) -> Extraction:
    try:
        with PDF_LOCK, pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass or doc.page_count > 1500:
                return Extraction("metadata", method="pymupdf", page_count=doc.page_count,
                                  note=NOTICE + " PDF加密或超过1500页提取上限。")
            pages, empty = [], []
            for number, page in enumerate(doc, 1):
                text = page.get_text("text", sort=True).replace("\r\n", "\n").replace("\r", "\n").strip()
                if not text.strip():
                    empty.append(number)
                pages.append(f"## 第 {number} 页\n\n" + (text or "> 本页未提取到文字，可能为空白页或扫描图像，待核验。"))
            note = NOTICE + " PDF按页机械提取，待核验；图像、公式、表格和阅读顺序可能不完整。"
            if empty:
                note += " 未提取到文字的页：" + ", ".join(map(str, empty)) + "。"
            kind = "extracted" if len(empty) < doc.page_count else "metadata"
            return Extraction(kind, "\n\n".join(pages), "pymupdf-page-text", doc.page_count, note)
    except Exception as exc:
        return Extraction("failed", method="pymupdf", note=f"PDF解析失败：{type(exc).__name__}: {exc}")


def load_sources(root: Path):
    rows = []
    for csv_path in sorted((root / "data/chapters").glob("ch[0-9][0-9]/sources.csv")):
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                hints = []
                document = csv_path.parent / "documents" / (row["source_id"] + ".md")
                if document.is_file():
                    for line in document.read_text(encoding="utf-8-sig").splitlines():
                        if "官方附件" not in line:
                            continue
                        for candidate in re.findall(r"https?://[^\s<>\[\]（）)]+", line):
                            try:
                                candidate = canonical_url(candidate.rstrip("。，;；"))
                                if urlsplit(candidate).path.lower().endswith(".pdf"):
                                    hints.append(candidate)
                            except ValueError:
                                pass
                rows.append(dict(row, hints=hints))
    if not rows:
        raise ValueError("No chapter sources.csv records found")
    ids = [row["source_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source_id in input")
    return rows


def _acquire_group(url, rows, fetcher):
    errors, attempts = [], []
    candidates = list(dict.fromkeys(h for row in rows for h in row["hints"]))
    chosen = None
    # Fetch every unique source landing URL, even when a known attachment works.
    try:
        download = fetcher.fetch(url)
        attempts.append(dict(url=url, actual_url=download.url, status="retrieved"))
        if download.data.lstrip().startswith(b"%PDF-"):
            extraction = extract_pdf(download.data)
        elif "html" in download.content_type.lower() or download.data.lstrip().startswith(b"<"):
            extraction = extract_html(download.data, download.url)
        else:
            extraction = Extraction("metadata", method="unsupported-media", note=NOTICE + " 不支持的文件格式，未提取正文。")
        if extraction.content_kind != "failed":
            chosen = (download, extraction)
        else:
            errors.append(extraction.note)
        candidates.extend(u for u in extraction.attachments if u not in candidates)
    except AcquisitionError as exc:
        errors.append(f"落地页 {url}: {exc}")
        attempts.append(dict(url=url, status="failed", error=str(exc)))
    # State pages are metadata even if their chrome links to an unrelated PDF.
    if urlsplit(url).hostname != "std.samr.gov.cn":
        for candidate in candidates[:8]:
            try:
                attachment = fetcher.fetch(candidate)
                attempts.append(dict(url=candidate, actual_url=attachment.url, status="retrieved"))
                if not attachment.data.lstrip().startswith(b"%PDF-"):
                    raise AcquisitionError("PDF attachment returned non-PDF bytes")
                extracted = extract_pdf(attachment.data)
                if extracted.content_kind == "failed":
                    raise AcquisitionError(extracted.note)
                if chosen is None or RANK[extracted.content_kind] > RANK[chosen[1].content_kind]:
                    chosen = (attachment, extracted)
                if extracted.content_kind == "extracted":
                    if len(candidates) > 1:
                        extracted.note += " 页面有多个PDF候选；本条保存首个可提取附件，其余附件尚未合并。"
                    break
            except AcquisitionError as exc:
                errors.append(f"附件 {candidate}: {exc}")
                attempts.append(dict(url=candidate, status="failed", error=str(exc)))
    if len(candidates) > 8:
        errors.append("PDF候选超过单来源8项上限，余项未请求。")
    if chosen is None:
        entry = dict(content_kind="failed", path="", url=url, landing_url=url, sha256="",
                     original_sha256="", crawled_at=now(), method="requests", page_count=0,
                     note="未取得官方正文；未以原有摘录或模拟内容代替。", error="; ".join(errors),
                     review_status="pending", attempts=attempts)
        return entry, b""
    download, extraction = chosen
    key = digest(canonical_url(download.url).encode())
    title = extraction.title or ("官方PDF逐页提取" if extraction.method.startswith("pymupdf") else "官方来源记录")
    # Generic PDF title avoids imposing a potentially wrong title from the CSV.
    body = (f"# {title}\n\n> {extraction.note}\n\n"
            f"- 官方原文：{download.url}\n"
            f"- 内容类型：{extraction.content_kind}\n"
            f"- 原文 SHA-256：{download.original_sha256}\n\n"
            f"{extraction.markdown}\n").encode("utf-8")
    entry = dict(content_kind=extraction.content_kind, path=f"data/acquired/documents/{key}.md",
                 url=download.url, request_url=download.redirects[0] if download.redirects else download.url,
                 landing_url=url, sha256=digest(body), crawled_at=download.crawled_at,
                 method=extraction.method, page_count=extraction.page_count, note=extraction.note,
                 error="; ".join(errors), original_sha256=download.original_sha256,
                 review_status="pending", attempts=attempts, text_chars=len(extraction.markdown),
                 non_text_elements=extraction.non_text_elements)
    return entry, body


def _existing(root, entry):
    """Only trust existing acquired files whose location and digest verify."""
    if not entry or not entry.get("path") or entry.get("content_kind") not in RANK:
        return None
    path = (root / entry["path"]).resolve()
    if path.parent != (root / "data/acquired/documents").resolve() or path.suffix != ".md":
        return None
    if not path.is_file() or digest(path.read_bytes()) != entry.get("sha256"):
        return None
    return entry


def _prefer_existing(old, new):
    return old and (RANK[old["content_kind"]] > RANK[new["content_kind"]] or
                    (RANK[old["content_kind"]] == RANK[new["content_kind"]] and
                     (new.get("text_chars", 0) < old.get("text_chars", 0) * 0.85 or
                      new["page_count"] < old.get("page_count", 0))))


def run_acquisition(root: Path, *, fetcher=None, workers=4, progress=False):
    root = Path(root).resolve()
    output = root / "data/acquired"
    output.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or Fetcher(root / ".cache/acquisition")
    prior_report_path = output / "report.json"
    prior_report = json.loads(prior_report_path.read_text(encoding="utf-8")) if prior_report_path.exists() else {}
    fetcher.begin_run(output / "attempts.jsonl", prior_report.get("requests", []))
    rows = load_sources(root)
    groups = defaultdict(list)
    for row in rows:
        groups[canonical_url(row["url"])].append(row)
    manifest_path = output / "manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest, run_results, bodies = {}, {}, {}
    verified = {sid: entry for sid, old in previous.items() if (entry := _existing(root, old))}
    for entry in verified.values():
        bodies.setdefault(entry["path"], (entry, (root / entry["path"]).read_bytes()))
    shared_fields = ("content_kind", "sha256", "original_sha256", "crawled_at", "method", "page_count", "text_chars")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_acquire_group, url, records, fetcher): url for url, records in groups.items()}
        for future in as_completed(futures):
            url = futures[future]
            entry, body = future.result()
            run_results[url] = entry
            old_entries = [verified.get(r["source_id"]) for r in groups[url]]
            old_entries = [e for e in old_entries if e]
            old = max(old_entries, key=lambda e: (RANK[e["content_kind"]], e.get("text_chars", 0)), default=None)
            preserve = _prefer_existing(old, entry)
            if preserve:
                entry = dict(old, note=old["note"] + " 本次采集未改善内容，保留已验证哈希的较好文本。",
                             last_attempt_at=now(), last_attempt_error=entry["error"],
                             last_attempt_kind=entry["content_kind"], last_attempts=entry["attempts"])
                body = bodies[entry["path"]][1]
            if body:
                # Two distinct landings may resolve to the same official attachment.
                # Keep one body for that canonical URL and synchronize every reference.
                path = entry["path"]
                shared = bodies.get(path)
                if shared and (_prefer_existing(shared[0], entry) or shared[0]["sha256"] == entry["sha256"]):
                    shared_entry, shared_body = shared
                    entry = dict(entry, **{k: shared_entry[k] for k in shared_fields},
                                 note=(entry["note"] if preserve else shared_entry["note"]) + " 保留并共享同一官方URL的已保存正文。")
                    body = shared_body
                else:
                    bodies[path] = (entry, body)
                    for prior in manifest.values():
                        if prior["path"] == path:
                            prior.update({k: entry[k] for k in shared_fields})
                atomic_write(root / path, body)
            for row in groups[url]:
                manifest[row["source_id"]] = dict(entry, landing_url=row["url"], source_sha256=row.get("sha256", ""))
            # Checkpoint completed records while preserving unprocessed previous data.
            write_json(manifest_path, dict(sorted({**previous, **manifest}.items())))
            if progress:
                print(f"[{len(run_results)}/{len(groups)}] {entry['content_kind']} {url}", flush=True)
    manifest = dict(sorted(manifest.items()))
    write_json(manifest_path, manifest)
    report = dict(completed_at=now(), run_id=fetcher.run_id, source_records=len(rows), unique_source_urls=len(groups),
                  counts=dict(Counter(e["content_kind"] for e in manifest.values())),
                  unique_url_counts=dict(Counter(e["content_kind"] for e in run_results.values())),
                  requests=fetcher.events, results=run_results,
                  note="采集状态与专业审核分开；原始章节CSV及文档不修改。")
    write_json(output / "report.json", report)
    return manifest


def import_web_snapshots(root: Path, snapshots):
    """Deprecated compatibility API for exact-landing HTML snapshots, never PDF.

    This legacy format lacks explicit identity bindings. New callers and the CLI
    must use remote_import.import_remote_snapshot with its strict evidence schema.

    Raw tool responses remain in ignored cache. They are not original HTTP bytes:
    original_sha256 stays empty and all usable body text is marked extracted.
    Explicit inclusive line bounds and continuous coverage prevent truncation from
    silently masquerading as a complete source. This performs no new network I/O.
    """
    root = Path(root).resolve()
    output = root / "data/acquired"
    manifest_path, report_path = output / "manifest.json", output / "report.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    sources = load_sources(root)
    fetcher = Fetcher(root / ".cache/acquisition")
    fetcher.begin_run(output / "attempts.jsonl", report.get("requests", []))
    for snapshot in snapshots:
        url = canonical_url(snapshot["url"])
        records = [r for r in sources if canonical_url(r["url"]) == url]
        if not records or urlsplit(url).path.lower().endswith(".pdf"):
            raise ValueError("Remote import must match a catalog HTML landing URL")
        start, end = snapshot["line_start"], snapshot["line_end"]
        lines, title = {}, ""
        for raw in snapshot["responses"]:
            header = re.match(r"^(.*?) \((https?://[^\n]+)\)\n", raw)
            if not header or canonical_url(header[2]) != url or "Content type: text/html;" not in raw:
                raise ValueError("Missing matching official HTML provenance")
            title = header[1]
            # Only physical line starts delimit records; embedded labels are text
            # and cannot supply a missing line or conflict with its real record.
            for match in re.finditer(r"^L(\d+): ?(.*?)(?=^L\d+:|\Z)", raw, re.M | re.S):
                number, value = int(match[1]), match[2].rstrip("\r\n")
                if number in lines and lines[number] != value:
                    raise ValueError("Conflicting remote snapshot lines")
                lines[number] = value
        if start < 0 or end < start or any(i not in lines for i in range(start, end + 1)):
            raise ValueError("Remote text has missing lines; cannot import truncated body")
        text = "\n".join(lines[i] for i in range(start, end + 1)).strip()
        if not text or "cite" in text or "[Input]" in text:
            raise ValueError("Selected body contains navigation/tool markers or is empty")
        kind = "metadata" if urlsplit(url).hostname == "std.samr.gov.cn" else "extracted"
        note = (NOTICE + " 来自远端web工具的HTML文字，按返回行号原样拼接；"
                "未取得原始HTML字节，original_sha256留空；重定向链、图表及页面完整性待核验。")
        if kind == "metadata":
            note += " 标准状态页面仅为元数据，不是标准正文。"
        evidence = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode()
        key = digest(url.encode())
        atomic_write(fetcher.cache_dir / (key + ".web.json"), evidence)
        body = f"# {title}\n\n> {note}\n\n- 官方原文：{url}\n- 内容类型：{kind}\n\n{text}\n".encode()
        entry = dict(content_kind=kind, path=f"data/acquired/documents/{key}.md", url=url,
                     landing_url=url, sha256=digest(body), original_sha256="",
                     crawled_at=snapshot["captured_at"], method="web-tool-html-text", page_count=0,
                     note=note, error="", review_status="pending", text_chars=len(text),
                     tool_snapshot_sha256=digest(evidence), source_lines=[start, end])
        old = [_existing(root, manifest.get(r["source_id"])) for r in records]
        keep = any(e and (RANK[e["content_kind"]] > RANK[kind] or
                         (RANK[e["content_kind"]] == RANK[kind] and e.get("text_chars", 0) > len(text))) for e in old)
        if not keep:
            atomic_write(root / entry["path"], body)
            for row in records:
                previous = manifest.get(row["source_id"], {})
                manifest[row["source_id"]] = dict(entry, landing_url=row["url"], source_sha256=row.get("sha256", ""),
                    attempts=previous.get("attempts", []) + [dict(url=url, status="remote-text-retrieved")],
                    previous_acquisition_error=previous.get("error", ""))
        fetcher._record(dict(url=url, status="remote-text-retrieved", crawled_at=snapshot["captured_at"],
                             method="web-tool-html-text", tool_snapshot_sha256=digest(evidence), preserved_existing=keep))
    manifest = dict(sorted(manifest.items()))
    write_json(manifest_path, manifest)
    report["counts"] = dict(Counter(e["content_kind"] for e in manifest.values()))
    report["remote_imported_at"] = now()
    report.setdefault("remote_imports", []).extend(fetcher.events)
    write_json(report_path, report)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--per-host", type=int, default=2, choices=[1, 2])
    parser.add_argument("--refresh", action="store_true", help="Re-fetch; keep better verified existing text")
    parser.add_argument("--proxy", help="Explicit HTTP proxy URL without credentials (optional)")
    parser.add_argument("--import-web-json", action="store_true", help="Import an explicit array of identity-bound remote snapshots from UTF-8 JSON on stdin; no network requests")
    args = parser.parse_args(argv)
    if args.import_web_json:
        if not __package__:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from airworthiness.remote_import import import_remote_snapshot, validate_remote_snapshot
        try:
            snapshots = json.load(sys.stdin)
            if not isinstance(snapshots, list) or not snapshots:
                raise ValueError("Expected a nonempty explicit snapshot array")
            # Reject an invalid later item before an earlier item can write files.
            for snapshot in snapshots:
                validate_remote_snapshot(snapshot, root=args.root)
            for snapshot in snapshots:
                manifest = import_remote_snapshot(args.root, snapshot)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(Counter(e["content_kind"] for e in manifest.values()), ensure_ascii=False))
        return 0
    if args.proxy:
        proxy = urlsplit(args.proxy)
        if proxy.scheme not in {"http", "https"} or not proxy.hostname or proxy.username or proxy.password:
            parser.error("--proxy must be an http(s) URL without credentials")
    fetcher = Fetcher(args.root / ".cache/acquisition", per_host=args.per_host, refresh=args.refresh, proxy=args.proxy)
    manifest = run_acquisition(args.root, fetcher=fetcher, workers=args.workers, progress=True)
    print(json.dumps(Counter(e["content_kind"] for e in manifest.values()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

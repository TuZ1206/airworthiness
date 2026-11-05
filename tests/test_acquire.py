"""Acquisition tests: real parsers/files, with only HTTP transport substituted."""
import csv
import hashlib
import importlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
SPEC = importlib.util.find_spec("airworthiness.acquire")
acquire = importlib.import_module("airworthiness.acquire") if SPEC else None

URL = "https://www.caac.gov.cn/law.html"
PDF_URL = "https://www.caac.gov.cn/law.pdf"
HTML = ("<html><head><meta charset='utf-8'><title>官方法律</title></head>"
        "<body><nav>导航广告</nav><div class='TRS_Editor'>"
        "<h2>第一章 总则</h2><p>第一条 保证航空安全。</p>"
        "<p>第二条 适用范围与责任。" + "依法开展审定并保存原始记录。" * 35 + "</p>"
        "<table><tr><th>项目</th><th>要求</th></tr>"
        "<tr><td>飞机</td><td>适航证</td></tr></table>"
        "<script>恶意脚本</script><nav>正文内导航</nav></div></body></html>").encode()


def pdf_bytes(blank=False):
    with pymupdf.open() as doc:
        page = doc.new_page()
        if not blank:
            page.insert_text((40, 60), "Official regulation: Article 1. Keep original text.")
        doc.new_page()  # Explicitly test a missing text layer, not just happy paths.
        return doc.tobytes()


def response(url, data=HTML, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.headers.update(headers or {"Content-Type": "text/html; charset=utf-8"})
    result.raw = io.BytesIO(data)
    return result


class Transport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        value = self.routes[url]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return response(url, **value)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(acquire, "Missing official acquisition implementation")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fetcher(self, routes, **kwargs):
        transport = Transport(routes)
        fetcher = acquire.Fetcher(self.root / ".cache" / "acquisition",
                                  transport=transport, interval=0, **kwargs)
        return fetcher, transport

    def sources(self, urls):
        chapter = self.root / "data" / "chapters" / "ch01"
        (chapter / "documents").mkdir(parents=True)
        with (chapter / "sources.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["source_id", "title", "url", "sha256"])
            writer.writeheader()
            for i, url in enumerate(urls, 1):
                sid = f"CH01-S{i:03}"
                original = "# 原有记录\n\n不能改写。\n"
                (chapter / "documents" / f"{sid}.md").write_text(original, encoding="utf-8")
                writer.writerow(dict(source_id=sid, title="台账名称", url=url,
                                     sha256=hashlib.sha256(original.encode()).hexdigest()))
        return chapter

    def test_only_official_http_urls_and_safe_ports(self):
        for url in [URL, "http://gov.cn/a", "https://STD.SAMR.GOV.CN:443/a"]:
            self.assertTrue(acquire.canonical_url(url))
        for url in ["https://gov.cn.evil.org/a", "https://fakegov.cn/a", "file:///a",
                    "https://user:password@www.caac.gov.cn/a", "https://gov.cn:22/a",
                    "https://gov.cn\\@evil.com/a", "https://127.0.0.1/a"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                acquire.canonical_url(url)
        self.assertEqual(acquire.canonical_url(URL + "#fragment"), URL)

    def test_html_preserves_original_body_structure_and_excludes_navigation(self):
        result = acquire.extract_html(HTML, URL)
        self.assertEqual(result.content_kind, "fulltext")
        self.assertIn("## 第一章 总则", result.markdown)
        self.assertIn("第一条 保证航空安全。", result.markdown)
        self.assertIn("| 飞机 | 适航证 |", result.markdown)
        for excluded in ["导航广告", "恶意脚本", "正文内导航"]:
            self.assertNotIn(excluded, result.markdown)

    def test_samr_status_is_always_metadata(self):
        result = acquire.extract_html(HTML, "https://std.samr.gov.cn/hb/search/detail?id=1")
        self.assertEqual(result.content_kind, "metadata")
        self.assertIn("标准", result.note)

    def test_unknown_layout_is_not_fulltext(self):
        result = acquire.extract_html(b"<html><title>Information</title><body>Navigation</body></html>", URL)
        self.assertEqual(result.content_kind, "metadata")

    def test_html_block_page_is_failed_even_with_status_200(self):
        result = acquire.extract_html(b"<html><title>Access Denied</title><p>Request blocked</p></html>", URL)
        self.assertEqual(result.content_kind, "failed")

    def test_relative_official_attachments_and_external_rejection(self):
        data = b'<div class="TRS_Editor"><a href="./rule.PDF?a=1">PDF</a><a href="https://evil.com/x.pdf">bad</a></div>'
        result = acquire.extract_html(data, URL)
        self.assertEqual(result.attachments, ["https://www.caac.gov.cn/rule.PDF?a=1"])

    def test_pdf_pages_are_extracted_and_empty_pages_flagged(self):
        result = acquire.extract_pdf(pdf_bytes())
        self.assertEqual(result.content_kind, "extracted")
        self.assertEqual(result.page_count, 2)
        self.assertIn("## 第 1 页", result.markdown)
        self.assertIn("## 第 2 页", result.markdown)
        self.assertIn("Article 1. Keep original text.", result.markdown)
        self.assertIn("待核验", result.note)
        self.assertIn("2", result.note)

    def test_scanned_pdf_and_corrupt_pdf_never_claim_text(self):
        self.assertEqual(acquire.extract_pdf(pdf_bytes(blank=True)).content_kind, "metadata")
        self.assertEqual(acquire.extract_pdf(b"%PDF-broken").content_kind, "failed")

    def test_redirect_is_validated_before_target_request(self):
        fetcher, transport = self.fetcher({URL: dict(status=302, data=b"", headers={"Location": "https://evil.org/file.pdf"})})
        with self.assertRaises(acquire.AcquisitionError):
            fetcher.fetch(URL)
        self.assertEqual(len(transport.calls), 1)
        self.assertFalse(transport.calls[0][1]["allow_redirects"])
        self.assertTrue(transport.calls[0][1]["verify"])

    def test_official_redirect_records_actual_url_and_raw_digest(self):
        fetcher, transport = self.fetcher({URL: dict(status=302, data=b"", headers={"Location": "/actual.html"}),
                                          "https://www.caac.gov.cn/actual.html": dict(data=HTML)})
        fetched = fetcher.fetch(URL)
        self.assertEqual(fetched.url, "https://www.caac.gov.cn/actual.html")
        self.assertEqual(fetched.original_sha256, hashlib.sha256(HTML).hexdigest())

    def test_download_limit_covers_header_and_stream(self):
        for headers in [{"Content-Length": "9999"}, {}]:
            with self.subTest(headers=headers):
                fetcher, _ = self.fetcher({URL: dict(data=b"x" * 100, headers=headers)}, max_bytes=50)
                with self.assertRaises(acquire.AcquisitionError):
                    fetcher.fetch(URL)

    def test_retries_are_bounded_and_tls_failure_not_bypassed(self):
        fetcher, transport = self.fetcher({URL: [requests.Timeout("slow"), requests.Timeout("slow")]}, retries=1)
        with self.assertRaises(acquire.AcquisitionError):
            fetcher.fetch(URL)
        self.assertEqual(len(transport.calls), 2)
        other = URL + "?tls"
        fetcher, transport = self.fetcher({other: requests.exceptions.SSLError("certificate error")}, retries=1)
        with self.assertRaises(acquire.AcquisitionError):
            fetcher.fetch(other)
        self.assertTrue(all(call[1]["verify"] for call in transport.calls))

    def test_cache_is_ignored_and_cannot_import_external_redirect(self):
        fetcher, transport = self.fetcher({URL: dict(data=HTML)})
        first = fetcher.fetch(URL)
        self.assertEqual(fetcher.fetch(URL).data, first.data)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual((fetcher.cache_dir / ".gitignore").read_text().strip(), "*")

    def test_disk_cache_revalidates_provenance_and_integrity(self):
        fetcher, _ = self.fetcher({URL: dict(data=HTML)})
        fetcher.fetch(URL)
        meta_path = next(fetcher.cache_dir.glob("*.json"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["url"] = "https://evil.org/copied.pdf"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        fetcher, transport = self.fetcher({URL: dict(data=HTML)})
        self.assertEqual(fetcher.fetch(URL).url, URL)
        self.assertEqual(len(transport.calls), 1)

    def test_unrelated_official_pdf_in_sidebar_is_not_a_document_candidate(self):
        data = HTML.replace(b"</body>", b'<aside><a href="/other/year/P.pdf">Other law</a></aside></body>')
        self.assertEqual(acquire.extract_html(data, URL).attachments, [])

    def test_notice_quoting_one_article_is_not_claimed_as_fulltext(self):
        data = ("<title>通知</title><div class='TRS_Editor'><p>根据第一条，现发布本文件，详见附件。"
                + "这是对文件的介绍和说明。" * 40
                + "</p><a href='law.pdf'>附件</a></div>").encode()
        self.assertEqual(acquire.extract_html(data, URL).content_kind, "metadata")

    def test_gbk_html_preserves_chinese(self):
        data = "<meta charset='gb2312'><title>官方文件</title><div class='TRS_Editor'>标题原文</div>".encode("gb18030")
        self.assertIn("标题原文", acquire.extract_html(data, URL).markdown)

    def test_run_deduplicates_urls_preserves_originals_and_writes_hashed_manifest(self):
        chapter = self.sources([URL, URL + "#fragment"])
        before = {p: p.read_bytes() for p in chapter.rglob("*") if p.is_file()}
        fetcher, transport = self.fetcher({URL: dict(data=HTML)})
        manifest = acquire.run_acquisition(self.root, fetcher=fetcher, workers=2)
        self.assertEqual(set(manifest), {"CH01-S001", "CH01-S002"})
        a, b = manifest.values()
        self.assertEqual(a["path"], b["path"])
        self.assertEqual(len(transport.calls), 1)
        content = (self.root / a["path"]).read_bytes()
        self.assertEqual(a["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(a["original_sha256"], hashlib.sha256(HTML).hexdigest())
        for key in ["url", "landing_url", "crawled_at", "method", "page_count", "note", "error"]:
            self.assertIn(key, a)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        saved = json.loads((self.root / "data/acquired/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, manifest)

    def test_known_pdf_hint_is_used_even_when_landing_unavailable(self):
        chapter = self.sources([URL])
        (chapter / "documents/CH01-S001.md").write_text(f"# 记录\n- 官方附件：{PDF_URL}\n", encoding="utf-8")
        fetcher, transport = self.fetcher({URL: dict(status=503, data=b""), PDF_URL: dict(data=pdf_bytes(), headers={"Content-Type": "application/pdf"})}, retries=0)
        item = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(item["content_kind"], "extracted")
        self.assertEqual(item["url"], PDF_URL)
        self.assertIn("待核验", item["note"])
        self.assertEqual({u for u, _ in transport.calls}, {URL, PDF_URL})

    def test_failed_refresh_keeps_good_existing_text(self):
        self.sources([URL])
        fetcher, _ = self.fetcher({URL: dict(data=HTML)})
        good = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        old_bytes = (self.root / good["path"]).read_bytes()
        fetcher, _ = self.fetcher({URL: dict(status=404, data=b"")}, refresh=True)
        new = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(new["sha256"], good["sha256"])
        self.assertEqual(new["content_kind"], "fulltext")
        self.assertEqual(old_bytes, (self.root / good["path"]).read_bytes())
        self.assertIn("保留", new["note"])

    def test_distinct_landings_with_shared_attachment_have_consistent_shared_body(self):
        second = URL.replace("law.html", "other.html")
        self.sources([URL, second])
        a = b'<div class="TRS_Editor"><a href="law.pdf">law</a><a href="other.pdf">another</a></div>'
        b = b'<div class="TRS_Editor"><a href="law.pdf">law</a></div>'
        fetcher, _ = self.fetcher({URL: dict(data=a), second: dict(data=b),
                                  PDF_URL: dict(data=pdf_bytes(), headers={"Content-Type": "application/pdf"})})
        manifest = acquire.run_acquisition(self.root, fetcher=fetcher, workers=1)
        self.assertEqual(manifest["CH01-S001"]["path"], manifest["CH01-S002"]["path"])
        for item in manifest.values():
            self.assertEqual(item["sha256"], hashlib.sha256((self.root / item["path"]).read_bytes()).hexdigest())

    def test_shorter_successful_refresh_does_not_replace_better_text(self):
        self.sources([URL])
        fetcher, _ = self.fetcher({URL: dict(data=HTML * 1)})
        old = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        fetcher, _ = self.fetcher({URL: dict(data=b'<div class="TRS_Editor">Short notice</div>')}, refresh=True)
        new = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(new["sha256"], old["sha256"])

    def test_new_alias_cannot_overwrite_retained_shared_pdf(self):
        second = URL.replace("law.html", "other.html")
        self.sources([URL, second])
        notice = b'<div class="TRS_Editor"><a href="law.pdf">law</a></div>'
        routes = {URL: dict(data=notice), second: dict(data=notice),
                  PDF_URL: dict(data=pdf_bytes(), headers={"Content-Type": "application/pdf"})}
        fetcher, _ = self.fetcher(routes)
        original = acquire.run_acquisition(self.root, fetcher=fetcher, workers=1)
        saved = dict(original)
        del saved["CH01-S002"]  # An alias not present in the previous acquisition.
        (self.root / "data/acquired/manifest.json").write_text(json.dumps(saved), encoding="utf-8")
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40, 60), "Short")
            routes[PDF_URL] = dict(data=doc.tobytes(), headers={"Content-Type": "application/pdf"})
        fetcher, _ = self.fetcher(routes, refresh=True)
        updated = acquire.run_acquisition(self.root, fetcher=fetcher, workers=1)
        for entry in updated.values():
            self.assertEqual(entry["sha256"], original["CH01-S001"]["sha256"])
            self.assertEqual(entry["sha256"], hashlib.sha256((self.root / entry["path"]).read_bytes()).hexdigest())

    def test_no_fake_fallback_when_all_requests_fail(self):
        self.sources([URL])
        fetcher, _ = self.fetcher({URL: dict(status=404, data=b"")})
        item = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(item["content_kind"], "failed")
        self.assertEqual(item["path"], "")
        self.assertEqual(item["sha256"], "")
        self.assertIn("404", item["error"])

    def test_attempt_journal_survives_failed_and_partial_runs(self):
        self.sources([URL])
        fetcher, _ = self.fetcher({URL: dict(status=404, data=b"")}, retries=0)
        acquire.run_acquisition(self.root, fetcher=fetcher)
        notice = b'<div class="TRS_Editor"><p>See attachment.</p><a href="law.pdf">law</a></div>'
        fetcher, _ = self.fetcher({URL: dict(data=notice), PDF_URL: dict(status=503, data=b"")}, retries=0, refresh=True)
        item = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(item["content_kind"], "metadata")
        self.assertTrue(item["path"])
        self.assertIn("503", item["error"])
        journal = self.root / "data/acquired/attempts.jsonl"
        self.assertTrue(journal.is_file(), "Every network attempt must remain available across reruns")
        events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(e["status"] == 404 for e in events))
        self.assertTrue(any(e["status"] == 200 for e in events))
        self.assertTrue(any(e["status"] == 503 for e in events))
        self.assertGreaterEqual(len({e["run_id"] for e in events}), 2)

    def test_pdf_attachment_html_response_keeps_landing_and_explains_failure(self):
        self.sources([URL])
        notice = b'<div class="TRS_Editor"><p>See attachment.</p><a href="law.pdf">law</a></div>'
        fetcher, _ = self.fetcher({URL: dict(data=notice), PDF_URL: dict(data=b"<title>Error</title>")})
        item = acquire.run_acquisition(self.root, fetcher=fetcher)["CH01-S001"]
        self.assertEqual(item["content_kind"], "metadata")
        self.assertEqual(item["url"], URL)
        self.assertIn("non-PDF", item["error"])

    def test_redirect_loop_is_bounded(self):
        other = "https://www.caac.gov.cn/other.html"
        fetcher, transport = self.fetcher({URL: dict(status=302, data=b"", headers={"Location": other}),
                                          other: dict(status=302, data=b"", headers={"Location": URL})})
        with self.assertRaises(acquire.AcquisitionError):
            fetcher.fetch(URL)
        self.assertEqual(len(transport.calls), 2)

    def test_remote_official_html_import_is_verbatim_and_explicitly_unverified(self):
        self.sources([URL, URL])
        payload = (f"Official law ({URL})\nContent type: text/html; Total lines: 5\n"
                   "L0: Navigation\nL1: 第一条 原始规定。\nL2: \nL3: 第二条 不得改写。\nL4: Footer")
        snapshot = dict(url=URL, responses=[payload], line_start=1, line_end=3, captured_at="2026-10-13T01:00:00+00:00")
        self.assertTrue(hasattr(acquire, "import_web_snapshots"), "Missing honest remote text import")
        manifest = acquire.import_web_snapshots(self.root, [snapshot])
        item = manifest["CH01-S001"]
        self.assertEqual(item["content_kind"], "extracted")
        self.assertEqual(item["original_sha256"], "", "Processed tool text is not original HTML bytes")
        self.assertIn("待核验", item["note"])
        text = (self.root / item["path"]).read_text(encoding="utf-8")
        self.assertIn("第一条 原始规定。\n\n第二条 不得改写。", text)
        self.assertNotIn("Navigation", text)
        self.assertEqual(item["path"], manifest["CH01-S002"]["path"])

    def test_remote_import_rejects_missing_lines_and_nonofficial_or_pdf_payload(self):
        self.sources([URL])
        self.assertTrue(hasattr(acquire, "import_web_snapshots"), "Missing remote provenance validation")
        variants = [f"Law ({URL})\nContent type: text/html; Total lines: 3\nL1: Text",
                    "Law (https://evil.org/a)\nContent type: text/html; Total lines: 3\nL1: Text\nL2: Text",
                    f"Law ({URL})\nContent type: application/pdf; Total lines: 3\nL1: Text\nL2: Text"]
        for raw in variants:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                acquire.import_web_snapshots(self.root, [dict(url=URL, responses=[raw], line_start=1, line_end=2, captured_at="2026-10-13T01:00:00+00:00")])


if __name__ == "__main__":
    unittest.main()

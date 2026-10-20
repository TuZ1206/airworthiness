"""Real cache pairs, raw PDFs and HTML; all writes stay in temporary roots."""
import copy
import csv
import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from airworthiness.acquire_http import Fetcher

SPEC = importlib.util.find_spec("airworthiness.cached_import")
cached = importlib.import_module("airworthiness.cached_import") if SPEC else None
PDF_URL = "https://www.caac.gov.cn/official.pdf"
HTML_URL = "https://xxgk.mot.gov.cn/rule.html"
LANDING = "https://www.caac.gov.cn/notice.html"
SID = "CH01-S001"
STAMP = "2026-10-13T08:30:23+00:00"
CODE, DATE = "CCAR-21-R5", "2024-02-18"
VERSION = "CCAR-21-R5 revision 2024-02-18"
PROOF = ("<title>Official version</title><div class='TRS_Editor'>" + VERSION + "</div>").encode()
PLACEHOLDER = "[原文包含图像/公式，见官方原文]"
HTML = ("<html><head><meta charset='utf-8'><title>官方规定</title></head><body>"
        "<nav><img src='logo.png'>导航</nav><div class='TRS_Editor'>"
        "<h2>第一章 总则</h2><p>第一条 保持原文。</p><p>第二条 适用范围。"
        + "依法开展审定并保存原始记录。" * 35 + "</p><p>公式位置</p>"
        "<a href='./attachment.pdf'>官方附件</a></div></body></html>").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pdf_bytes(texts=("Article 1. Official rule.", "Article 2. Original text."), encrypted=False):
    with pymupdf.open() as document:
        for text in texts:
            page = document.new_page()
            if text:
                page.insert_text((40, 60), text)
        return document.tobytes(**(dict(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                        owner_pw="owner", user_pw="reader") if encrypted else {}))


class CachedImportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(cached, "Missing cached_import implementation")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        chapter = self.root / "data/chapters/ch01"
        (chapter / "documents").mkdir(parents=True)
        self.original = chapter / "documents" / f"{SID}.md"
        self.original.write_bytes(b"Original uploaded source, unchanged.")
        self.source_hash = sha(self.original.read_bytes())
        self.csv = chapter / "sources.csv"
        with self.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_id", "title", "url", "sha256", "document_code", "publish_date"])
            writer.writeheader()
            for n in range(1, 190):
                writer.writerow(dict(source_id=f"CH01-S{n:03}", title="登记标题",
                                     url=LANDING if n <= 3 else f"https://www.caac.gov.cn/{n}.html",
                                     sha256=self.source_hash if n == 1 else f"{n:064x}", document_code=CODE, publish_date=DATE))
        self.output = self.root / "data/acquired"
        self.output.mkdir(parents=True)
        self.old = {f"CH01-S{n:03}": dict(content_kind="failed", path="", error="SSL failure", custom=n)
                    for n in range(1, 190)}
        self.save("manifest.json", self.old)
        self.save("report.json", dict(counts={"failed": 189}, requests=[{"status": 403}],
                                      results={LANDING: {"content_kind": "failed"}}, custom="retain"))
        (self.output / "attempts.jsonl").write_bytes(b'{"status":403}\n')
        self.cache_dir = self.root / ".cache/acquisition"
        self.cache_dir.mkdir(parents=True)
        (self.cache_dir / ".gitignore").write_bytes(b"keep original cache ignore\n")
        self.cache(PROOF, url=LANDING, media="text/html")
        # Fail at the network boundary, even if an accidental new path bypasses Fetcher.fetch.
        self.enterContext(patch("requests.sessions.Session.request", side_effect=AssertionError("No network")))
        self.enterContext(patch.object(Fetcher, "fetch", side_effect=AssertionError("No fetching")))
        self.enterContext(patch.object(Fetcher, "__init__", side_effect=AssertionError("Cache must be read-only")))

    def save(self, name, value):
        (self.output / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def tree(self, base=None):
        base = base or self.root
        return {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}

    def cache(self, data=None, url=PDF_URL, actual=None, media="application/pdf", **changes):
        data = pdf_bytes() if data is None else data
        key = sha(url.encode())
        raw = self.cache_dir / (key + ".bin")
        meta = self.cache_dir / (key + ".json")
        raw.write_bytes(data)
        metadata = dict(request_url=url, url=actual or url, content_type=media, crawled_at=STAMP,
                        redirects=[url] if actual and actual != url else [], original_sha256=sha(data), size=len(data))
        metadata.update(changes)
        meta.write_text(json.dumps(metadata), encoding="utf-8")
        return raw, meta

    def evidence(self, actual=PDF_URL):
        return dict(urls=[LANDING, actual], note="人工核对：通知与附件为同一文件同一修订版本。",
                    source_bindings={f"CH01-S{n:03}": dict(source_sha256=self.source_hash if n == 1 else f"{n:064x}",
                                                        document_code=CODE, publish_date=DATE) for n in range(1, 4)},
                    version_evidence=[dict(kind="cache", url=LANDING, cache_url=LANDING,
                                           original_sha256=sha(PROOF), quote=VERSION,
                                           source_ids=[SID, "CH01-S002", "CH01-S003"])])

    def run_import(self, url=PDF_URL, ids=None, evidence=None, note=""):
        return cached.import_cached_original(self.root, url, ids or [SID],
                                             evidence if evidence is not None else self.evidence(url), note=note)

    def existing(self, sid=SID, kind="extracted", chars=5000, pages=0, method="web-tool-html-text", **extra):
        path = "data/acquired/documents/shared-old.md"
        document = self.root / path
        document.parent.mkdir(exist_ok=True)
        document.write_bytes(b"Old verified document")
        item = dict(content_kind=kind, path=path, sha256=sha(document.read_bytes()), text_chars=chars,
                    page_count=pages, method=method, original_sha256="", landing_url=LANDING,
                    source_sha256=self.source_hash if sid == SID else f"{int(sid[-3:]):064x}", url=LANDING)
        item.update(extra)
        self.old[sid] = item
        self.save("manifest.json", self.old)
        return copy.deepcopy(item)

    def test_pdf_import_uses_raw_hash_all_pages_and_keeps_cache_csv_and_189_records(self):
        raw, meta = self.cache()
        before_cache, before_csv, original = self.tree(self.cache_dir), self.csv.read_bytes(), self.original.read_bytes()
        manifest = self.run_import(ids=[SID, "CH01-S002"], note="主调用层已核对版本。")
        self.assertEqual(len(manifest), 189)
        for sid in set(manifest) - {SID, "CH01-S002"}:
            self.assertEqual(manifest[sid], self.old[sid])
        item = manifest[SID]
        self.assertEqual(item["original_sha256"], sha(raw.read_bytes()))
        self.assertEqual(item["raw_path"], raw.relative_to(self.root).as_posix())
        self.assertEqual(item["cache_metadata_path"], meta.relative_to(self.root).as_posix())
        self.assertEqual(item["cache_metadata_sha256"], sha(meta.read_bytes()))
        self.assertEqual(item["source_sha256"], self.source_hash)
        self.assertEqual(item["landing_url"], LANDING)
        self.assertEqual(item["url"], PDF_URL)
        self.assertEqual(item["actual_url"], PDF_URL)
        self.assertEqual(item["request_url"], PDF_URL)
        self.assertEqual(item["method"], "pymupdf-page-text")
        self.assertEqual(item["acquisition_method"], "cached-original")
        self.assertEqual(item["content_kind"], "extracted")
        self.assertEqual(item["review_status"], "pending")
        self.assertEqual(item["crawled_at"], STAMP)
        self.assertEqual(item["page_count"], 2)
        self.assertTrue(item["all_pages"])
        self.assertEqual(item["identity_evidence"], self.evidence())
        self.assertIn("主调用层已核对版本。", item["note"])
        body = (self.root / item["path"]).read_bytes()
        self.assertEqual(item["sha256"], sha(body))
        self.assertEqual(Path(item["path"]).stem, "cached-" + sha(body))
        self.assertIn("## 第 1 页", body.decode())
        self.assertIn("## 第 2 页", body.decode())
        self.assertIn("Article 2. Original text.", body.decode())
        self.assertEqual(manifest["CH01-S002"]["path"], item["path"])
        self.assertEqual(manifest["CH01-S002"]["source_sha256"], f"{2:064x}")
        self.assertEqual(self.read("manifest.json"), manifest)
        self.assertEqual(self.tree(self.cache_dir), before_cache)
        self.assertEqual(self.csv.read_bytes(), before_csv)
        self.assertEqual(self.original.read_bytes(), original)

    def test_read_api_and_redirect_provenance_require_actual_url_evidence(self):
        self.cache(actual=HTML_URL)
        before = self.tree()
        download = cached.read_cached_original(self.root, PDF_URL)
        self.assertEqual(download.url, HTML_URL)
        self.assertEqual(self.tree(), before)
        with self.assertRaises(ValueError):
            self.run_import(evidence=self.evidence(PDF_URL))
        self.assertEqual(self.tree(), before)
        item = self.run_import(evidence=self.evidence(HTML_URL))[SID]
        self.assertEqual(item["request_url"], PDF_URL)
        self.assertEqual(item["actual_url"], HTML_URL)
        self.assertEqual(item["redirects"], [PDF_URL])

    def test_cache_misses_and_invalid_pairs_never_fetch_or_write(self):
        for changes in [{"original_sha256": "0" * 64}, {"url": "https://evil.org/a"},
                        {"redirects": ["https://gov.cn.evil.org/a"]}, {"request_url": LANDING},
                        {"redirects": None}, {"content_type": None}, {"crawled_at": "unknown"}]:
            with self.subTest(changes=changes):
                self.cache(**changes) if "url" not in changes else self.cache(actual=changes["url"])
                before = self.tree()
                with self.assertRaises(ValueError):
                    self.run_import()
                self.assertEqual(self.tree(), before)
        raw, meta = self.cache()
        raw.write_bytes(b"tampered raw bytes")
        before = self.tree()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.tree(), before)
        raw.unlink()
        before = self.tree()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.tree(), before)
        meta.write_text("broken json", encoding="utf-8")
        with self.assertRaises(ValueError):
            cached.read_cached_original(self.root, PDF_URL)

    def test_official_urls_identity_and_source_ids_validated_before_writes(self):
        self.cache()
        cases = [("https://gov.cn.evil.org/a", [SID], self.evidence()),
                 ("https://user@gov.cn/a", [SID], self.evidence()), ("file:///a", [SID], self.evidence()),
                 (PDF_URL, [SID, "UNKNOWN"], self.evidence()), (PDF_URL, [SID, SID], self.evidence()),
                 (PDF_URL, [], self.evidence()), (PDF_URL, SID, self.evidence()),
                 (PDF_URL, [SID], dict(urls=[PDF_URL], note="缺落地页")),
                 (PDF_URL, [SID], dict(urls=[LANDING], note="缺原文URL")),
                 (PDF_URL, [SID], dict(urls=[PDF_URL, LANDING], note=" ")),
                 (PDF_URL, [SID], dict(urls=[PDF_URL, LANDING, "https://evil.org/a"], note="证据"))]
        before = self.tree()
        for url, ids, evidence in cases:
            with self.subTest(url=url, ids=ids, evidence=evidence), self.assertRaises(ValueError):
                cached.import_cached_original(self.root, url, ids, evidence)
            self.assertEqual(self.tree(), before)

    def test_notice_scanned_pdf_and_standard_pages_stay_metadata(self):
        for data, url, media in [(b"<title>Notice</title><div class='TRS_Editor'>See attachment.</div>", HTML_URL, "text/html"),
                                 (pdf_bytes(("", "")), PDF_URL, "application/pdf"),
                                 (pdf_bytes(encrypted=True), PDF_URL, "application/pdf"),
                                 (HTML, "https://std.samr.gov.cn/detail?id=1", "text/html")]:
            with self.subTest(url=url, media=media):
                self.save("manifest.json", self.old)
                self.cache(data, url=url, media=media)
                item = self.run_import(url)[SID]
                self.assertEqual(item["content_kind"], "metadata")
                self.assertEqual(item["review_status"], "pending")

    def test_explicit_csv_binding_and_real_version_quote_are_required(self):
        self.cache()
        variants = []
        for field, value in [("source_sha256", "0" * 64), ("document_code", "CCAR-21-R4"), ("publish_date", "2017-01-01")]:
            evidence = self.evidence()
            evidence["source_bindings"][SID][field] = value
            variants.append(evidence)
        for field in ["source_bindings", "version_evidence"]:
            evidence = self.evidence()
            evidence.pop(field)
            variants.append(evidence)
        for field, value in [("quote", "x"), ("quote", "CCAR-21-R4 revision 2017-01-01"),
                             ("original_sha256", "f" * 64), ("url", PDF_URL)]:
            evidence = self.evidence()
            evidence["version_evidence"][0][field] = value
            variants.append(evidence)
        before = self.tree()
        for evidence in variants:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                self.run_import(evidence=evidence)
            self.assertEqual(self.tree(), before)

    def test_missing_csv_hash_never_creates_an_implicit_new_binding(self):
        self.cache()
        self.csv.write_text(self.csv.read_text(encoding="utf-8").replace(self.source_hash, ""), encoding="utf-8")
        before = self.tree()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.tree(), before)

    def test_wrong_revision_is_not_saved_by_a_matching_publication_date(self):
        self.cache()
        for version in ["CCAR-21-R50 revision 2024-02-18", "CCAR-21-R4 revision 2024-02-18"]:
            proof = ("<div class='TRS_Editor'>" + version + "</div>").encode()
            self.cache(proof, url=LANDING, media="text/html")
            evidence = self.evidence()
            evidence["version_evidence"][0].update(quote=version, original_sha256=sha(proof))
            before = self.tree()
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.run_import(evidence=evidence)
            self.assertEqual(self.tree(), before)

    def test_unrelated_official_page_is_not_version_evidence_for_selected_source(self):
        self.cache()
        unrelated = "https://www.gov.cn/unrelated.html"
        self.cache(PROOF, url=unrelated, media="text/html")
        evidence = self.evidence()
        evidence["urls"].append(unrelated)
        evidence["version_evidence"][0].update(url=unrelated, cache_url=unrelated)
        before = self.tree()
        with self.assertRaises(ValueError):
            self.run_import(evidence=evidence)
        self.assertEqual(self.tree(), before)

    def test_archive_member_evidence_reads_only_fixed_verified_pdf_without_importing_rar(self):
        url, archive = "https://www.caac.gov.cn/archive.rar", b"Rar!\x1a\x07\x00verified archive fixture"
        self.cache(archive, url=url, media="application/x-rar-compressed")
        member = self.cache_dir / "archive" / (sha(url.encode()) + ".pdf")
        member.parent.mkdir()
        data = pdf_bytes((VERSION, "Official cover"))
        member.write_bytes(data)
        evidence = self.evidence(url)
        proof = dict(kind="cache", url=url, cache_url=url, original_sha256=sha(archive),
                     member="型号合格审定程序.pdf", member_sha256=sha(data), quote=VERSION, source_ids=[SID])
        evidence["version_evidence"] = [proof]
        before = self.tree()
        try:
            rows = cached.validate_identity_evidence(self.root, url, [SID], evidence)
        except ValueError as exc:
            self.fail(f"Verified archive member evidence rejected: {exc}")
        self.assertEqual(rows[0]["source_id"], SID)
        self.assertEqual(self.tree(), before)
        for changes in [{"member_sha256": "f" * 64}, {"original_sha256": "f" * 64},
                        {"member": "../outside.pdf"}, {"quote": "CCAR-21-R4"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cached.validate_identity_evidence(self.root, url, [SID], dict(evidence, version_evidence=[dict(proof, **changes)]))
        with patch.object(cached, "MAX_MEMBER_BYTES", len(data)), self.assertRaises(ValueError):
            cached.validate_identity_evidence(self.root, url, [SID], evidence)
        with self.assertRaises(ValueError):
            self.run_import(url, evidence=evidence)  # Evidence support is not an archive importer.
        member.write_bytes(b"not PDF")
        with self.assertRaises(ValueError):
            cached.validate_identity_evidence(self.root, url, [SID], evidence)
        member.unlink()
        proof["path"] = str(self.original)  # Arbitrary paths cannot substitute the fixed member file.
        with self.assertRaises(ValueError):
            cached.validate_identity_evidence(self.root, url, [SID], evidence)

    def test_named_meta_is_evidence_only_scripts_and_navigation_never_become_body(self):
        raw = (f'<meta name="document_code" content="{CODE}"><title>Notice</title>'
               f'<script>var code="{CODE}";</script><nav>{VERSION}</nav>'
               '<div class="TRS_Editor">See attachment.</div>').encode()
        self.cache(raw, url=LANDING, media="text/html")
        evidence = self.evidence(LANDING)
        evidence["version_evidence"][0].update(meta_name="document_code", quote=CODE, original_sha256=sha(raw))
        try:
            item = self.run_import(LANDING, evidence=evidence)[SID]
        except ValueError as exc:
            self.fail(f"Official named meta evidence rejected: {exc}")
        self.assertEqual(item["content_kind"], "metadata")
        self.assertNotIn(CODE, (self.root / item["path"]).read_text(encoding="utf-8"))
        evidence["version_evidence"][0].pop("meta_name")
        with self.assertRaises(ValueError):
            cached.validate_identity_evidence(self.root, LANDING, [SID], evidence)

    def test_only_caac_static_wenhao_is_allowed_as_script_metadata(self):
        for url, expression, valid in [(LANDING, f'"{CODE}";', True),
                                       (LANDING, f'"{CODE}" + dynamic;', False), (HTML_URL, f'"{CODE}";', False)]:
            raw = f'<html><head><script>var wenhao={expression}</script></head><body>Notice</body></html>'.encode()
            self.cache(raw, url=url, media="text/html")
            evidence = self.evidence(url)
            evidence["version_evidence"][0].update(url=url, cache_url=url, script_var="wenhao", quote=CODE, original_sha256=sha(raw))
            if valid:
                try:
                    self.assertEqual(cached.validate_identity_evidence(self.root, url, [SID], evidence)[0]["source_id"], SID)
                except ValueError as exc:
                    self.fail(f"Static CAAC wenhao rejected: {exc}")
            else:
                with self.assertRaises(ValueError):
                    cached.validate_identity_evidence(self.root, url, [SID], evidence)

    def test_buhao_selected_exactly_and_chinese_date_whitespace(self):
        raw = f'<head><script>var wenhao="";\nvar buhao="{CODE}";\nvar fwrq="{DATE}";</script></head>'.encode()
        self.cache(raw, url=LANDING, media="text/html")
        evidence = self.evidence(LANDING)
        evidence["version_evidence"][0].update(script_var="buhao", quote=CODE, original_sha256=sha(raw))
        self.assertEqual(cached.validate_identity_evidence(self.root, LANDING, [SID], evidence)[0]["source_id"], SID)
        evidence["version_evidence"][0]["script_var"] = "wenhao"
        with self.assertRaises(ValueError):
            cached.validate_identity_evidence(self.root, LANDING, [SID], evidence)
        self.assertTrue(cached._version_matches("2016 年3 月17 日", dict(document_code="", publish_date="2016-03-17")))

    def test_html_text_uses_existing_extractor_and_keeps_real_links(self):
        raw, _ = self.cache(HTML, url=HTML_URL, media="text/html")
        item = self.run_import(HTML_URL)[SID]
        self.assertEqual(item["content_kind"], "fulltext")
        self.assertEqual(item["original_sha256"], sha(raw.read_bytes()))
        self.assertEqual(item["method"], "html:.TRS_Editor")
        self.assertEqual(item["non_text_elements"], 0)
        body = (self.root / item["path"]).read_text(encoding="utf-8")
        self.assertIn("[官方附件](https://xxgk.mot.gov.cn/attachment.pdf)", body)
        self.assertNotIn("导航", body)

    def test_html_images_use_current_extractor_placeholders_and_original_hash(self):
        images = b"<p>formula<img src='eq.png'><img src='diagram.png'><img src='formula2.png'></p>"
        raw_html = HTML.replace(b"</div>", images + b"</div>")
        self.cache(raw_html, url=HTML_URL, media="text/html")
        item = self.run_import(HTML_URL)[SID]
        self.assertEqual(item["content_kind"], "extracted")
        self.assertEqual(item["non_text_elements"], 3)
        self.assertEqual(item["original_sha256"], sha(raw_html))
        body = (self.root / item["path"]).read_text(encoding="utf-8")
        self.assertEqual(body.count(PLACEHOLDER), 3)
        self.assertIn("图像/公式", item["note"])
        self.assertIn("3", item["note"])
        self.assertEqual(item["note"].count("图像/公式占位"), 1)

    def test_caac_body_selector_and_appendix_note_are_preserved(self):
        raw = HTML.replace(b"class='TRS_Editor'", b"data-role='n_content'")
        self.cache(raw, url=HTML_URL, media="text/html")
        item = self.run_import(HTML_URL, note="附录未合并。")[SID]
        self.assertEqual(item["method"], 'html:[data-role="n_content"]')
        self.assertIn("附录未合并", item["note"])

    def test_images_cannot_promote_notices_or_switch_the_selected_body(self):
        notice = b"<title>Notice</title><div class='TRS_Editor'><p>See attachment</p><img src='notice.png'></div>"
        self.cache(notice, url=HTML_URL, media="text/html")
        item = self.run_import(HTML_URL)[SID]
        self.assertEqual(item["content_kind"], "metadata")
        self.assertEqual(item["non_text_elements"], 1)
        self.assertIn(PLACEHOLDER, (self.root / item["path"]).read_text(encoding="utf-8"))
        self.save("manifest.json", self.old)
        other = b"<div class='article-content'>Other" + b"<img src='x.png'>" * 60 + b"</div>"
        raw_html = HTML.replace(b"</body>", other + b"<div hidden><img src='hidden.png'></div></body>")
        self.cache(raw_html, url=HTML_URL, media="text/html")
        item = self.run_import(HTML_URL)[SID]
        self.assertEqual(item["content_kind"], "fulltext")
        self.assertEqual(item["non_text_elements"], 0)
        self.assertNotIn("Other", (self.root / item["path"]).read_text(encoding="utf-8"))

    def test_invalid_pdf_error_html_and_archives_are_rejected_without_writes(self):
        for raw, media in [(b"%PDF-broken", "application/pdf"), (b"<title>Access Denied</title>", "text/html"),
                           (b"Rar!\x1a\x07\x00raw", "application/x-rar-compressed"),
                           (b"<title>not a PDF</title>", "application/pdf"), (b"PK\x03\x04zip", "application/zip")]:
            with self.subTest(media=media):
                self.cache(raw, media=media)
                before = self.tree()
                with self.assertRaises(ValueError):
                    self.run_import()
                self.assertEqual(self.tree(), before)

    def test_equal_rank_prefers_all_page_raw_pdf_over_longer_web_html(self):
        self.cache()
        self.existing(chars=10000)
        item = self.run_import()[SID]
        self.assertEqual(item["method"], "pymupdf-page-text")
        self.assertEqual(item["page_count"], 2)

    def test_higher_rank_and_equal_rank_better_pdf_survive_independently(self):
        self.cache()
        old = self.existing(kind="fulltext")
        other = self.existing(sid="CH01-S002", pages=3, method="pymupdf-page-text", original_sha256="a" * 64)
        manifest = self.run_import(ids=[SID, "CH01-S002", "CH01-S003"])
        self.assertEqual(manifest[SID], old)
        self.assertEqual(manifest["CH01-S002"], other)
        self.assertEqual(manifest["CH01-S003"]["content_kind"], "extracted")
        self.assertEqual((self.root / old["path"]).read_bytes(), b"Old verified document")

    def test_raw_pdf_is_not_replaced_by_longer_equal_rank_html_with_images(self):
        raw = HTML.replace(b"</div>", b"<img src='formula.png'></div>")
        self.cache(raw, url=HTML_URL, media="text/html")
        old = self.existing(chars=5, pages=2, method="pymupdf-page-text", original_sha256="a" * 64)
        self.assertEqual(self.run_import(HTML_URL)[SID], old)

    def test_stale_or_corrupt_old_entry_does_not_block_new_binding(self):
        self.cache()
        for changes in [{"source_sha256": "0" * 64}, {"landing_url": HTML_URL}, {"sha256": "bad"},
                        {"path": "../outside.md"}]:
            with self.subTest(changes=changes):
                self.existing(kind="fulltext", **changes)
                item = self.run_import()[SID]
                self.assertEqual(item["source_sha256"], self.source_hash)
                self.assertEqual(item["method"], "pymupdf-page-text")

    def test_repeat_import_retains_content_appends_journal_and_updates_counts(self):
        self.cache()
        first = self.run_import()[SID]
        journal = (self.output / "attempts.jsonl").read_bytes()
        second = self.run_import()[SID]
        self.assertEqual(first, second)
        new_journal = (self.output / "attempts.jsonl").read_bytes()
        self.assertTrue(new_journal.startswith(journal))
        self.assertEqual(len(new_journal.splitlines()), 3)
        event = json.loads(new_journal.splitlines()[-1])
        self.assertEqual(event["updated_source_ids"], [])
        self.assertEqual(event["preserved_source_ids"], [SID])
        self.assertEqual(event["original_sha256"], first["original_sha256"])
        report = self.read("report.json")
        self.assertEqual(report["counts"], {"extracted": 1, "failed": 188})
        self.assertEqual(report["unique_url_counts"], {"extracted": 1, "failed": 186})
        self.assertEqual(report["source_records"], 189)
        self.assertEqual(report["requests"], [{"status": 403}])
        self.assertEqual(report["results"], {LANDING: {"content_kind": "failed"}})
        self.assertEqual(report["custom"], "retain")
        self.assertEqual(len(report["cached_imports"]), 2)

    def test_new_raw_original_never_overwrites_shared_old_markdown(self):
        self.cache()
        old = self.run_import(ids=[SID, "CH01-S002"])[SID]
        body = (self.root / old["path"]).read_bytes()
        self.cache(pdf_bytes(("Article 1. This is additional detailed original text.", "Article 2. Original text.")))
        new = self.run_import()[SID]
        self.assertNotEqual(new["path"], old["path"])
        self.assertEqual((self.root / old["path"]).read_bytes(), body)
        self.assertEqual(self.read("manifest.json")["CH01-S002"], dict(old, source_sha256=f"{2:064x}"))


if __name__ == "__main__":
    unittest.main()

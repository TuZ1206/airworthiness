"""Behavioral acceptance tests for the offline, nine-chapter resource library."""
import importlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("airworthiness.catalog"), "Library catalog is not implemented")
        self.catalog = importlib.import_module("airworthiness.catalog")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "library.sqlite3"
        self.report = self.catalog.build_catalog(ROOT, self.db)

    def test_all_nine_chapters_and_189_sources_are_loaded(self):
        overview = self.catalog.overview(self.db)
        self.assertEqual(overview["totals"]["sources"], 189)
        self.assertEqual(len(overview["chapters"]), 9)
        self.assertEqual(self.report["errors"], [])

    def test_chinese_substrings_two_characters_and_document_codes(self):
        for query in ("复合材料", "适航", "CCAR-25"):
            result = self.catalog.resources(self.db, q=query)
            self.assertGreater(result["total"], 0, query)
            self.assertTrue(any(query.lower() in item["snippet"].lower() or query.lower() in item["title"].lower() or query.lower() in item["document_code"].lower() for item in result["items"]))

    def test_filters_pagination_and_arbitrary_queries_are_safe(self):
        result = self.catalog.resources(self.db, chapter="ch03", page_size=3)
        self.assertEqual(result["total"], 7)
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(all(x["chapter_id"] == "ch03" for x in result["items"]))
        second = self.catalog.resources(self.db, chapter="ch03", page=2, page_size=3)
        self.assertFalse(set(x["source_id"] for x in result["items"]) & set(x["source_id"] for x in second["items"]))
        for query in ('" OR 1=1 --', '<script>'):
            self.assertEqual(self.catalog.resources(self.db, q=query)["total"], 0)
        for query in ('*', '%'):
            result = self.catalog.resources(self.db, q=query)
            self.assertTrue(all(query in x["snippet"] for x in result["items"]))
        self.assertEqual(self.catalog.resources(self.db, status="abolished")["total"], 10)

    def test_document_has_body_traceability_and_real_heading_targets(self):
        doc = self.catalog.document(self.db, "CH03-S001")
        self.assertEqual(doc["source_id"], "CH03-S001")
        self.assertEqual(doc["review_status"], "pending")
        self.assertIn("gov.cn", doc["url"])
        self.assertGreater(len(doc["html"]), 100)
        for heading in doc["toc"]:
            self.assertIn('id="' + heading["id"] + '"', doc["html"])
        self.assertIsNone(self.catalog.document(self.db, "../../README"))

    def test_uploaded_pdf_provenance_and_glossary_targets_are_retained(self):
        doc = self.catalog.document(self.db, 'CH02-S001')
        self.assertIn('uploaded_provenance', doc)
        self.assertEqual(doc['uploaded_provenance']['pdf_sha256'], 'f1a0a74794b485cbdb6baf818d027a4d11be6e7431968e472ed6ff583924477a')
        self.assertTrue(doc['uploaded_provenance']['pdf_url'].endswith('.pdf'))
        for term in self.catalog.chapter(self.db, 'ch01')['glossary']:
            self.assertEqual(term['anchor_or_url'], f"/chapters/ch01?source={term['source_id']}")
            self.assertIn('original_anchor_or_url', term)

    def test_original_excerpt_is_never_implicitly_labelled_fulltext(self):
        loader = importlib.import_module("airworthiness.ingest")
        text = (ROOT / "data/chapters/ch03/documents/CH03-S001.md").read_text(encoding="utf-8")
        self.assertEqual(loader.classify_original(text), "excerpt")
        text = (ROOT / "data/chapters/ch04/documents/CH04-S007.md").read_text(encoding="utf-8")
        self.assertEqual(loader.classify_original(text), "metadata")

    def test_rebuild_is_idempotent_and_quality_report_exposes_gaps(self):
        self.catalog.build_catalog(ROOT, self.db)
        self.assertEqual(self.catalog.overview(self.db)["totals"]["sources"], 189)
        report = self.catalog.quality(self.db)
        self.assertEqual(len(report["chapters"]), 9)
        self.assertTrue(report["generated_at"])
        self.assertTrue(all(x["reason"] for x in report["gaps"]))
        self.assertTrue(any(x['source_id'] == 'CH03-S001' and x['kind'] == 'date_variation' for x in report['issues']))


class RenderingTests(unittest.TestCase):
    def test_pdf_text_preserves_lines_and_does_not_treat_formulas_as_markdown(self):
        reading = importlib.import_module('airworthiness.reading')
        self.assertIn('extracted', __import__('inspect').signature(reading.render_document).parameters)
        html, toc = reading.render_document('## 正文\n\n第一行\n第二行\n\na_b_c < 3\n---\n\n### 1.1 适用范围\n\n内容', extracted=True)
        self.assertIn('第一行\n第二行', html)
        self.assertIn('a_b_c &lt; 3', html)
        self.assertNotIn('<em>', html)
        self.assertTrue(any(x['text'] == '1.1 适用范围' for x in toc))

    def test_numeric_quantities_are_not_invented_section_headings(self):
        reading = importlib.import_module('airworthiness.reading')
        html, toc = reading.render_document('## 正文\n\n0.2 V\n\n25.6 公斤/立方米\n\n' + ('原文段落。' * 1700), extracted=True)
        self.assertFalse(any(x['text'] in ['0.2 V', '25.6 公斤/立方米'] for x in toc))
        self.assertGreater(len(toc), 1, 'Long raw text must get clearly marked reading segments')

    def test_untrusted_markdown_cannot_execute_scripts(self):
        self.assertIsNotNone(importlib.util.find_spec("airworthiness.reading"))
        reading = importlib.import_module("airworthiness.reading")
        html, toc = reading.render_document('# 标题\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n## 同名\n\n## 同名')
        self.assertNotIn('<script', html)
        self.assertNotIn('href="javascript:', html)
        self.assertEqual(len({x["id"] for x in toc}), len(toc))


class SharedOriginalTests(unittest.TestCase):
    def test_stale_acquisition_is_not_bound_to_changed_source(self):
        ingest = importlib.import_module('airworthiness.ingest')
        self.assertTrue(hasattr(ingest, 'source_binding_matches'))
        row = dict(sha256='current', url='https://www.gov.cn/current')
        good = dict(source_sha256='current', landing_url=row['url'])
        self.assertTrue(ingest.source_binding_matches(row, good))
        self.assertFalse(ingest.source_binding_matches(row, dict(good, source_sha256='old')))
        self.assertFalse(ingest.source_binding_matches(row, dict(good, landing_url='https://www.gov.cn/old')))

    def test_reader_body_excludes_source_metadata_but_keeps_excerpt(self):
        ingest = importlib.import_module('airworthiness.ingest')
        raw = '# 标题\n\n- 来源编号：CH01-S001\n- 官方页面：https://www.gov.cn/a\n\n## 本章核验摘录\n\n正文内容。'
        body = ingest.body_only(raw)
        self.assertNotIn('来源编号', body)
        self.assertIn('正文内容', body)
        raw = '# 标题\n\n- review_status: pending\n\n官方页面仅确认状态。'
        self.assertNotIn('review_status', ingest.body_only(raw))

    def test_same_official_url_can_reuse_uploaded_original_across_chapters(self):
        ingest = importlib.import_module('airworthiness.ingest')
        self.assertTrue(hasattr(ingest, 'share_originals'))
        donor = dict(source_id='CH02-S001', url='https://www.caac.gov.cn/a.html', body='真实原文', content_kind='extracted', sha256='testhash', extraction_note='机械提取', acquisition={})
        target = dict(source_id='CH06-S001', url=donor['url'], body='摘要', content_kind='excerpt', sha256='other', extraction_note='摘要', acquisition={})
        unrelated = dict(target, source_id='CH05-S001', url='https://www.caac.gov.cn/b.html')
        ingest.share_originals([donor, target, unrelated])
        self.assertEqual(target['body'], '真实原文')
        self.assertEqual(target['content_kind'], 'extracted')
        self.assertEqual(target['reused_from'], 'CH02-S001')
        self.assertIn('CH02-S001', target['extraction_note'])
        self.assertEqual(unrelated['body'], '摘要')


if __name__ == "__main__":
    unittest.main()

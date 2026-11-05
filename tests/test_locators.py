"""Evidence-only navigation, including fragments from the uploaded originals."""
import importlib
import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup

from airworthiness.reading import clean_extracted_text, render_document

ROOT = Path(__file__).resolve().parents[1]
REGULATION = ROOT / "data/acquired/documents/6cdcc6ef5d939d4a1f2540673b2f997d988ae7cf634561f11bf32de2acd8cfd4.md"


class ClauseRenderingTests(unittest.TestCase):
    def render(self, text, extracted=True):
        html, toc = render_document(text, extracted=extracted)
        return BeautifulSoup(html, "html.parser"), toc

    def test_explicit_chinese_decimal_and_chapter_anchors(self):
        body = "第十二章 总则\n\n第一百零二条 应当保存记录。\n\n第25.601条 总则\n材料必须满足要求。"
        for extracted in (True, False):
            with self.subTest(extracted=extracted):
                soup, toc = self.render(body, extracted)
                for anchor in ("chapter-12", "clause-102", "clause-25-601"):
                    self.assertIsNotNone(soup.find(id=anchor), anchor)
                    self.assertIn(anchor, [x["id"] for x in toc])

    def test_real_directory_and_attached_chapter_title_are_disambiguated(self):
        body = "目录\n第 1 章 说明和修订 .......... 4\n\n第 1 章说明和修订\n1.1 一般说明\n飞行标准管理手册共分为八卷。"
        soup, toc = self.render(body)
        self.assertIsNotNone(soup.find(id="chapter-1"))
        self.assertEqual(soup.find(id="chapter-1").get_text(), "第 1 章说明和修订")
        self.assertNotIn("1.1 一般说明", [x["text"] for x in toc])
        self.assertEqual(len([x["id"] for x in toc]), len({x["id"] for x in toc}))

    def test_duplicate_clauses_and_pdf_pages_have_stable_unique_ids(self):
        body = "##第1页\n\n第25.601条 总则\n\n正文。\n\n## 第 2 页\n\n第25.601条 总则\n\n重印正文。"
        soup, toc = self.render(body)
        expected = {"page-1", "page-2", "clause-25-601", "clause-25-601--2"}
        self.assertTrue(expected.issubset({x["id"] for x in toc}))
        prefixed, _ = self.render("# 新增说明\n\n其他内容。\n\n" + body)
        for anchor in expected:
            self.assertEqual(soup.find(id=anchor).get_text(), prefixed.find(id=anchor).get_text())

    def test_quantities_prose_references_and_table_cells_are_not_clauses(self):
        # CH02-S030 contains a vertical table headed 条款号, then 第25.181条/操稳/6.
        body = "0.2V\n25.6公斤\n1.1 适用范围\n\n第25.603条要求材料符合标准。\n\n第29.1309条(a)款的要求\n\n条款号\n专业\n符合性验证方法\n9\n第25.181条\n操稳\n6\n\n第三章规定相关要求。"
        _, toc = self.render(body)
        self.assertEqual(toc, [])

    def test_formulas_and_original_words_are_literal_and_safe(self):
        body = '第一条 材料要求\n\na_b_c < 3\n0.2V\n---\n<img src=x onerror="alert(1)">\n设计 保证 系统'
        soup, _ = self.render(body)
        self.assertIn('a_b_c < 3\n0.2V\n---\n<img src=x onerror="alert(1)">\n设计 保证 系统', soup.get_text())
        self.assertIsNone(soup.find("img"))
        self.assertIsNone(soup.find("em"))

    def test_markdown_code_does_not_produce_legal_headings(self):
        soup, toc = self.render("```text\n第一条 代码示例\n```\n\n<script>x()</script>\n\n[坏链接](javascript:alert(1))\n\n第25.601条 总则\n\n真实正文。", False)
        self.assertIsNone(soup.find(id="clause-1"))
        self.assertIsNotNone(soup.find(id="clause-25-601"))
        self.assertIsNone(soup.find("script"))
        self.assertFalse(any(x.get("href", "").startswith("javascript:") for x in soup.find_all("a")))

    def test_malformed_numbers_and_formula_titles_fail_closed(self):
        for text in ("第25..601条 标题", "第25.条 标题", "第25 . . 601条 标题"):
            with self.subTest(text=text):
                # Public rendering must not crash on malformed OCR.
                try:
                    soup, toc = self.render(text)
                except Exception as exc:
                    self.fail(f"Malformed source raised {type(exc).__name__}")
                self.assertEqual(toc, [])
                self.assertIn(text, soup.get_text())

    def test_chinese_digit_strings_and_fullwidth_decimal_labels(self):
        soup, _ = self.render("第二百三十五条 应保存记录。\n\n第一〇二条 内容。\n\n第 ２５．６０１ 条 总则\n\n正文。")
        for anchor in ("clause-235", "clause-102", "clause-25-601"):
            self.assertIsNotNone(soup.find(id=anchor))

    def test_decimal_numbers_cannot_collide_with_occurrence_suffixes(self):
        body = "第25.601条 总则\n\n第25.601条 重印\n\n第25.601.2条 明示条号\n\n第25.0601条 明示条号"
        soup, toc = self.render(body)
        ids = [x["id"] for x in toc]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNotNone(soup.find(id="clause-25-601--2"))
        self.assertIsNotNone(soup.find(id="clause-25-0601"))

    def test_cleaning_preserves_the_explicit_article_boundary_and_words(self):
        body = "第25.601条 总则\n\n设计 保证 系统和公式 a_b_c < 3"
        cleaned = clean_extracted_text(body)
        self.assertEqual(cleaned, body)
        soup, _ = self.render(cleaned)
        self.assertIsNotNone(soup.find(id="clause-25-601"))

    def test_all_29_real_regulation_articles_are_addressable(self):
        body = REGULATION.read_text(encoding="utf-8")
        soup, _ = self.render(body)
        for number in range(1, 30):
            self.assertIsNotNone(soup.find(id=f"clause-{number}"), f"article {number}")

    def test_real_ocr_reference_does_not_become_article(self):
        body = (ROOT / "data/chapters/ch02/documents/CH02-S008.md").read_text(encoding="utf-8")
        soup, _ = self.render(body)
        self.assertIsNone(soup.find(id="clause-92-327"))

    def test_real_long_leaders_stay_directory(self):
        body = (ROOT / "data/chapters/ch02/documents/CH02-S019.md").read_text(encoding="utf-8")
        soup, _ = self.render(body)
        self.assertIsNotNone(soup.find(id="toc-chapter-1"))
        self.assertIsNotNone(soup.find(id="chapter-1"))
        self.assertNotIn("...", soup.find(id="chapter-1").get_text())

    def test_invalid_chinese_number_cannot_generate_a_different_number(self):
        for label in ("第一百百条 标题", "第十百条 标题", "第一二十条 标题"):
            self.assertEqual(self.render(label)[1], [])


class TermLocatorTests(unittest.TestCase):
    def resolve(self, terms, body, extracted=True):
        self.assertIsNotNone(importlib.util.find_spec("airworthiness.locators"), "Evidence resolver is not implemented")
        return importlib.import_module("airworthiness.locators").resolve_terms(terms, body, extracted=extracted)

    def term(self, **kwargs):
        return dict(term="TC", aliases="型号合格证", definition="编辑编写的概括，不是引文。", chapter_id="ch01", source_id="CH01-S005", anchor_or_url="#old-unverified", **kwargs)

    def assert_target(self, result, body, extracted=True):
        fragment = result["anchor_or_url"].split("#", 1)[1]
        soup = BeautifulSoup(render_document(body, extracted=extracted)[0], "html.parser")
        self.assertIsNotNone(soup.find(id=fragment), fragment)
        self.assertIn(result["locator_evidence"], body)
        self.assertTrue(result["locator_evidence"])
        self.assertLessEqual(len(result["locator_evidence"]), 240)
        self.assertFalse(result["definition_verified"])

    def test_keyword_is_text_match_even_inside_real_clause(self):
        body = "第六条 型号合格证\n\n申请人应当向民航局申请型号合格证。"
        terms = [self.term()]
        before = deepcopy(terms)
        result = self.resolve(terms, body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertEqual(result["anchor_or_url"], "/chapters/ch01?source=CH01-S005#clause-6")
        self.assertEqual(result["definition"], terms[0]["definition"])
        self.assertEqual(terms, before)
        self.assert_target(result, body)

    def test_exact_quote_in_clause_is_verified_as_location_only(self):
        quote = "申请人应当向民航局申请型号合格证。"
        body = "第六条 型号合格证\n\n" + quote
        result = self.resolve([self.term(quote=quote)], body)[0]
        self.assertEqual(result["locator_status"], "verified_clause")
        self.assertEqual(result["locator_evidence"], quote)
        self.assert_target(result, body)

    def test_uncertain_article_prefix_clears_previous_clause_without_inventing_one(self):
        quote = "申请人应当向民航局申请型号合格证。"
        for label in ("第七条 （一）申请要求", "第七条申请条件", "第25..601条 申请要求",
                      "第 十 七 条 申请要求", "第七条 （一）申请要求 ........ 7"):
            for extracted in (False, True):
                for gap in ("\n", "\n\n"):
                    with self.subTest(label=label, extracted=extracted, gap=repr(gap)):
                        body = "第六条 总则\n上一条的正文尚未留空行。\n" + label + gap + quote
                        result = self.resolve([self.term(quote=quote)], body, extracted)[0]
                        self.assertEqual(result["locator_status"], "text_match")
                        self.assertTrue(result["locator_anchor"].startswith("paragraph-"))
                        self.assert_target(result, body, extracted)
                        html, toc = render_document(body, extracted=extracted)
                        self.assertIn(label, BeautifulSoup(html, "html.parser").get_text())
                        self.assertEqual([item["id"] for item in toc if item["kind"] == "clause"], ["clause-6"])

    def test_explicit_article_restores_scope_after_an_uncertain_boundary(self):
        quote = "申请人应当向民航局申请型号合格证。"
        for extracted in (False, True):
            body = "第六条 总则\n\n第七条申请条件\n相关要求。\n\n第八条 明确编号\n\n" + quote
            result = self.resolve([self.term(quote=quote)], body, extracted)[0]
            self.assertEqual(result["locator_status"], "verified_clause")
            self.assertEqual(result["locator_anchor"], "clause-8")
            self.assert_target(result, body, extracted)

    def test_definition_and_inexact_or_unrelated_quotes_cannot_verify(self):
        body = "第六条 型号合格证\n\n申请人应当向民航局申请型号合格证。\n\n申请人还应保存其他相关记录。"
        for quote in ("", "型号合格证", "申请人可以向民航局申请型号合格证。", "申请人还应保存其他相关记录。"):
            with self.subTest(quote=quote):
                term = self.term(quote=quote)
                term["definition"] = "申请人应当向民航局申请型号合格证。"
                self.assertEqual(self.resolve([term], body)[0]["locator_status"], "text_match")

    def test_paragraph_match_does_not_invent_numeric_subsection(self):
        body = "1.1 适用范围\n\n本程序说明型号合格证的申请流程。"
        result = self.resolve([self.term(quote="本程序说明型号合格证的申请流程。")], body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertIn("#paragraph-", result["anchor_or_url"])
        self.assert_target(result, body)

    def test_absent_and_ascii_substring_terms_fall_back_to_source(self):
        for body in ("", "仅有 STC 与 CAAC 资料。", "与此术语无关。"):
            result = self.resolve([self.term()], body)[0]
            self.assertEqual(result["locator_status"], "source_only")
            self.assertEqual(result["anchor_or_url"], "/chapters/ch01?source=CH01-S005")
            self.assertEqual(result["locator_evidence"], "")
            self.assertEqual(result["original_anchor_or_url"], "#old-unverified")

    def test_directory_only_matches_do_not_count_as_body_evidence(self):
        for body in ("目录\n第六条 型号合格证 ........ 6", "## 目录\n\n第六条 型号合格证\n第七条 生产许可证"):
            self.assertEqual(self.resolve([self.term()], body)[0]["locator_status"], "source_only")

    def test_quote_prefers_body_over_repeated_directory_number(self):
        quote = "申请人应当向民航局申请型号合格证。"
        for leader in (" ........ 6", ""):
            body = f"目录\n第六条 型号合格证{leader}\n第七条 生产许可证\n\n第六条 型号合格证\n\n{quote}"
            result = self.resolve([self.term(quote=quote)], body)[0]
            self.assertEqual(result["locator_status"], "verified_clause")
            self.assertTrue(result["anchor_or_url"].endswith("#clause-6"))
            self.assert_target(result, body)

    def test_duplicate_quote_is_not_verified_and_missing_quote_falls_back_to_keyword(self):
        quote = "申请人应当向民航局申请型号合格证。"
        body = f"第六条 申请\n\n{quote}\n\n第七条 其他\n\n{quote}"
        result = self.resolve([self.term(quote=quote)], body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assert_target(result, body)

    def test_page_continuation_keeps_clause_but_chapter_stops_it(self):
        quote = "申请人应当向民航局申请型号合格证。"
        body = f"## 第 1 页\n\n第六条 申请\n\n##第2页\n\n{quote}"
        result = self.resolve([self.term(quote=quote)], body)[0]
        self.assertEqual(result["locator_status"], "verified_clause")
        self.assertTrue(result["anchor_or_url"].endswith("#clause-6"))
        changed = body.replace("##第2页", "第二章 附则")
        result = self.resolve([self.term(quote=quote)], changed)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertIn("#paragraph-", result["anchor_or_url"])

    def test_real_uploaded_and_acquired_documents(self):
        acquired = REGULATION.read_text(encoding="utf-8")
        quote = "民用航空器必须具有民航局颁发的适航证，方可飞行。"
        term = dict(term="适航证", source_id="CH01-S002", chapter_id="ch01", quote=quote)
        result = self.resolve([term], acquired)[0]
        self.assertEqual(result["locator_status"], "verified_clause")
        self.assertTrue(result["anchor_or_url"].endswith("#clause-9"))
        self.assert_target(result, acquired)
        uploaded = (ROOT / "data/chapters/ch02/documents/CH02-S064.md").read_text(encoding="utf-8")
        result = self.resolve([self.term()], uploaded)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assert_target(result, uploaded)

    def test_evidence_near_end_of_long_paragraph_and_alias_separators(self):
        body = "普通段落。" * 1400 + "持续适航文件应当随产品交付。"
        term = dict(term="ICA", aliases="不存在；持续适航文件|另一别名", source_id="CH02-S023")
        result = self.resolve([term], body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertIn("持续适航文件", result["locator_evidence"])
        self.assert_target(result, body)

    def test_markdown_match_links_to_real_paragraph_and_preserves_quote_rules(self):
        body = "## 正文\n\n**型号合格证**应按规定申请。\n\n第六条 申请\n\n申请人应当向民航局申请型号合格证。"
        result = self.resolve([self.term(quote="申请人应当向民航局申请型号合格证。")], body, False)[0]
        self.assertEqual(result["locator_status"], "verified_clause")
        self.assert_target(result, body, False)

    def test_quote_in_markdown_code_or_a_title_cannot_verify(self):
        quote = "申请人应当向民航局申请型号合格证。"
        for body in (f"第六条 申请\n\n```\n{quote}\n```", f"### 第六条 {quote}"):
            result = self.resolve([self.term(quote=quote)], body, False)[0]
            self.assertNotEqual(result["locator_status"], "verified_clause")

    def test_untrusted_or_malformed_fallback_url_is_not_returned(self):
        for url in ("javascript:alert(1)", "//untrusted.example/a", "http://[invalid"):
            try:
                result = self.resolve([dict(term="未命中", anchor_or_url=url)], "正文")[0]
            except Exception as exc:
                self.fail(f"Invalid fallback URL raised {type(exc).__name__}")
            self.assertEqual(result["anchor_or_url"], "")

    def test_numeric_directory_ends_at_observable_body_prose(self):
        body = "目录\n1 总则 ....... 1\n2 型号合格证 ...... 2\n\n1 总则\n本程序针对型号合格证的申请过程作出说明，申请人应当遵守相关要求。"
        result = self.resolve([self.term()], body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertNotIn("......", result["locator_evidence"])
        self.assert_target(result, body)

    def test_long_paragraph_chunk_boundary_does_not_split_a_term_or_formula(self):
        body = "前" * 7998 + "型号合格证应当按规定申请。a_b_c < 3"
        result = self.resolve([self.term()], body)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assert_target(result, body)
        soup = BeautifulSoup(render_document(body, extracted=True)[0], "html.parser")
        self.assertIn(body, soup.get_text())


if __name__ == "__main__":
    unittest.main()

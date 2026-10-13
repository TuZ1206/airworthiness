import csv
import hashlib
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CHAPTER = ROOT / "ch03"
APP = ROOT / "src" / "airworthiness" / "app.py"
PAGE = ROOT / "src" / "airworthiness" / "web" / "templates" / "chapter" / "3" / "detail.html"
GRAPH = ROOT / "src" / "airworthiness" / "graph" / "neo4j_setup.py"


def rows(name):
    with (CHAPTER / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ChapterThreeDataTests(unittest.TestCase):
    def test_expected_counts_and_pending_state(self):
        self.assertEqual(len(rows("sources.csv")), 7)
        self.assertEqual(len(rows("nodes.csv")), 29)
        self.assertEqual(len(rows("relations.csv")), 25)
        self.assertEqual(len(rows("glossary.csv")), 14)
        for filename in ("sources.csv", "nodes.csv", "relations.csv", "glossary.csv"):
            self.assertTrue(all(row["review_status"] == "pending" for row in rows(filename)))

    def test_official_sources_and_matching_hashes(self):
        for source in rows("sources.csv"):
            host = (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            self.assertTrue(host == "gov.cn" or host.endswith(".gov.cn"), source["url"])
            document = CHAPTER / "documents" / f'{source["source_id"]}.md'
            self.assertTrue(document.is_file())
            self.assertEqual(hashlib.sha256(document.read_bytes()).hexdigest(), source["sha256"])

    def test_no_foreign_formal_sources_or_unsupported_claims(self):
        formal = "\n".join((CHAPTER / name).read_text(encoding="utf-8") for name in (
            "sources.csv", "nodes.csv", "relations.csv", "glossary.csv"
        ))
        page = PAGE.read_text(encoding="utf-8")
        for forbidden in (
            "AC 20-107B", "SAE AMS 3700", "ASTM D3039", "CMH-17",
            "A基准值试验样本数", "B基准值试验样本数", "1500MPa",
            "1000MPa", "250MPa", "1000小时", "退役后5年",
        ):
            self.assertNotIn(forbidden, formal)
            self.assertNotIn(forbidden, page)
        review = (CHAPTER / "review.md").read_text(encoding="utf-8")
        self.assertIn("AC 20-107B", review)
        self.assertIn("SAE AMS 3700", review)

    def test_current_title_program_and_clause_are_consistent(self):
        app = APP.read_text(encoding="utf-8")
        page = PAGE.read_text(encoding="utf-8")
        graph = GRAPH.read_text(encoding="utf-8")
        chapter_block = re.search(r"\n    3: \{.*?\n    4: \{", app, re.S)
        self.assertIsNotNone(chapter_block)
        combined = chapter_block.group(0) + page
        self.assertIn("材料性能与材料级验证", combined)
        self.assertIn("AP-21-11R2", combined)
        self.assertNotIn("复合材料的材料性能及验证", combined)
        self.assertNotIn("25.303", combined)
        self.assertNotRegex(combined, r"AP-21-AA-2023(?!-11R1)")
        self.assertNotIn('{"chapter": 3, "concept": "B基准值"}', graph)
        self.assertIn('{"chapter": 3, "concept": "A基准设计值"}', graph)
        self.assertIn('{"chapter": 3, "concept": "B基准设计值"}', graph)

    def test_glossary_anchors_exist_in_page(self):
        page = PAGE.read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', page))
        for term in rows("glossary.csv"):
            anchor = term["anchor_or_url"]
            if anchor.startswith("#"):
                self.assertIn(anchor[1:], ids, term["term_id"])

    def test_abolished_and_status_only_sources_are_bounded(self):
        nodes = rows("nodes.csv")
        relations = rows("relations.csv")
        self.assertFalse(any(row["source_id"] == "CH03-S007" for row in nodes + relations))
        for node in nodes:
            if node["source_id"] == "CH03-S006":
                self.assertIn("官方标准状态页", node["source_locator"])
                self.assertTrue("公开范围" in node["source_locator"] or "状态" in node["summary"])

    def test_basis_values_keep_regulatory_conditions(self):
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn("99%概率、95%置信度", page)
        self.assertIn("90%概率、95%置信度", page)
        self.assertNotIn("复合材料一律采用B基准", page)
        self.assertNotIn("民用飞机复合材料强制采用B基准", page)


if __name__ == "__main__":
    unittest.main()

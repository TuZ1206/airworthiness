import csv
import hashlib
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CHAPTER = ROOT / "ch09"
APP = ROOT / "src" / "airworthiness" / "app.py"
PAGE = ROOT / "src" / "airworthiness" / "web" / "templates" / "chapter" / "9" / "detail.html"
GRAPH = ROOT / "src" / "airworthiness" / "graph" / "neo4j_setup.py"


def rows(name):
    with (CHAPTER / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ChapterNineDataTests(unittest.TestCase):
    def test_expected_counts_and_pending_state(self):
        self.assertEqual(len(rows("sources.csv")), 15)
        self.assertEqual(len(rows("nodes.csv")), 30)
        self.assertEqual(len(rows("relations.csv")), 28)
        self.assertEqual(len(rows("glossary.csv")), 18)
        for filename in ("sources.csv", "nodes.csv", "relations.csv", "glossary.csv"):
            self.assertTrue(all(row["review_status"] == "pending" for row in rows(filename)))

    def test_official_sources_and_matching_hashes(self):
        for source in rows("sources.csv"):
            host = (urlparse(source["url"]).hostname or "").lower().rstrip(".")
            self.assertTrue(host == "gov.cn" or host.endswith(".gov.cn"), source["url"])
            document = CHAPTER / "documents" / f'{source["source_id"]}.md'
            self.assertTrue(document.is_file())
            self.assertEqual(hashlib.sha256(document.read_bytes()).hexdigest(), source["sha256"])

    def test_no_foreign_formal_sources_or_unsupported_absolute_claims(self):
        formal = "\n".join((CHAPTER / name).read_text(encoding="utf-8") for name in (
            "sources.csv", "nodes.csv", "relations.csv", "glossary.csv"
        ))
        for forbidden in ("ASTM", "ISO 527", "ISO 14129", "MIL-HDBK", "CMH-17", "SAE", "五批每批六件", "统一要求5件", "统一要求6件"):
            self.assertNotIn(forbidden, formal)
        review = (CHAPTER / "review.md").read_text(encoding="utf-8")
        self.assertIn("ASTM", review)
        self.assertIn("CMH-17", review)

    def test_current_program_and_title_are_consistent(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (APP, PAGE, GRAPH))
        self.assertIn("试验与统计方法", combined)
        self.assertNotIn("结构设计审查与适航符合性分析", combined)
        self.assertNotRegex(combined, r"AP-21-AA-2023(?!-)" )
        self.assertIn("AP-21-11R2", combined)

    def test_glossary_anchors_exist_in_page(self):
        page = PAGE.read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', page))
        for term in rows("glossary.csv"):
            anchor = term["anchor_or_url"]
            if anchor.startswith("#"):
                self.assertIn(anchor[1:], ids, term["term_id"])

    def test_status_only_sources_do_not_claim_hidden_clauses(self):
        status_only = {"CH09-S006", "CH09-S007", "CH09-S008", "CH09-S009", "CH09-S010", "CH09-S011", "CH09-S012", "CH09-S013", "CH09-S014", "CH09-S015"}
        for node in rows("nodes.csv"):
            if node["source_id"] in status_only:
                self.assertTrue("状态页" in node["source_locator"] or "公开范围" in node["source_locator"], node["node_id"])


if __name__ == "__main__":
    unittest.main()

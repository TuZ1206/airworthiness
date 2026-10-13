import csv
import hashlib
import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CHAPTER_ROOT = ROOT / "data" / "chapters"
CHAPTERS = ("ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09")
HEADERS = {
    "sources.csv": ["source_id", "title", "document_code", "document_status", "publish_date", "url", "sha256", "crawled_at", "review_status"],
    "nodes.csv": ["node_id", "chapter_id", "label", "name", "code", "summary", "display_type", "source_id", "source_locator", "priority", "review_status"],
    "relations.csv": ["relation_id", "from_node_id", "type", "to_node_id", "source_id", "evidence", "review_status"],
    "glossary.csv": ["term_id", "term", "aliases", "definition", "group", "has_page", "anchor_or_url", "related_node_id", "source_id", "review_status"],
}


def rows(chapter: Path, name: str):
    with (chapter / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class UnifiedChapterDataTests(unittest.TestCase):
    def test_required_files_and_headers(self):
        for chapter_name in CHAPTERS:
            chapter = CHAPTER_ROOT / chapter_name
            for name, expected in HEADERS.items():
                with (chapter / name).open(encoding="utf-8", newline="") as handle:
                    self.assertEqual(next(csv.reader(handle)), expected, f"{chapter_name}/{name}")
            for name in ("README.md", "review.md", "crawler_config.json"):
                self.assertTrue((chapter / name).is_file(), f"{chapter_name}/{name}")

    def test_sources_are_official_pending_and_hashed(self):
        for chapter_name in CHAPTERS:
            chapter = CHAPTER_ROOT / chapter_name
            for row in rows(chapter, "sources.csv"):
                host = (urlparse(row["url"]).hostname or "").lower().rstrip(".")
                self.assertTrue(host == "gov.cn" or host.endswith(".gov.cn"), row["url"])
                self.assertIn(row["document_status"], {"effective", "abolished", "unknown"})
                self.assertEqual(row["review_status"], "pending")
                document = chapter / "documents" / f'{row["source_id"]}.md'
                self.assertTrue(document.is_file(), document)
                self.assertEqual(hashlib.sha256(document.read_bytes()).hexdigest(), row["sha256"], row["source_id"])

    def test_ids_relations_and_source_references(self):
        all_ids = {kind: [] for kind in ("source_id", "node_id", "relation_id", "term_id")}
        for chapter_name in CHAPTERS:
            chapter = CHAPTER_ROOT / chapter_name
            sources = rows(chapter, "sources.csv")
            nodes = rows(chapter, "nodes.csv")
            relations = rows(chapter, "relations.csv")
            terms = rows(chapter, "glossary.csv")
            source_ids = {row["source_id"] for row in sources}
            node_ids = {row["node_id"] for row in nodes}
            effective = {row["source_id"] for row in sources if row["document_status"] == "effective"}
            for collection, key in ((sources, "source_id"), (nodes, "node_id"), (relations, "relation_id"), (terms, "term_id")):
                values = [row[key] for row in collection]
                self.assertEqual(len(values), len(set(values)), f"{chapter_name}/{key}")
                all_ids[key].extend(values)
                self.assertTrue(all(row["review_status"] == "pending" for row in collection))
            for node in nodes:
                self.assertIn(node["source_id"], effective, node["node_id"])
                self.assertTrue(node["source_locator"].strip(), node["node_id"])
            for relation in relations:
                self.assertIn(relation["from_node_id"], node_ids)
                self.assertIn(relation["to_node_id"], node_ids)
                self.assertIn(relation["source_id"], effective)
                self.assertTrue(relation["evidence"].strip())
            for term in terms:
                self.assertIn(term["source_id"], source_ids)
                self.assertIn(term["related_node_id"], node_ids)
        for key, values in all_ids.items():
            self.assertEqual(len(values), len(set(values)), f"全仓库重复编号：{key}")

    def test_crawler_configs_and_no_large_binaries(self):
        for chapter_name in CHAPTERS:
            chapter = CHAPTER_ROOT / chapter_name
            config = json.loads((chapter / "crawler_config.json").read_text(encoding="utf-8"))
            for url in config["seeds"]:
                host = (urlparse(url).hostname or "").lower().rstrip(".")
                self.assertTrue(host == "gov.cn" or host.endswith(".gov.cn"), url)
            for path in chapter.rglob("*"):
                if path.is_file():
                    self.assertNotIn(path.suffix.lower(), {".pdf", ".docx", ".zip"}, path)

    def test_ch02_crawl_result_count(self):
        self.assertEqual(len(rows(CHAPTER_ROOT / "ch02", "sources.csv")), 86)

    def test_ch01_normalized_counts(self):
        chapter = CHAPTER_ROOT / "ch01"
        self.assertEqual(len(rows(chapter, "sources.csv")), 21)
        self.assertEqual(len(rows(chapter, "nodes.csv")), 26)
        self.assertEqual(len(rows(chapter, "relations.csv")), 26)
        self.assertEqual(len(rows(chapter, "glossary.csv")), 20)


if __name__ == "__main__":
    unittest.main()

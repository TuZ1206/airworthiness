"""The chapter-end graph must remain a traceable, pending-review preview."""
import unittest
from pathlib import Path

from airworthiness.chapter_graph import build_chapter_graph
from airworthiness.ingest import load_inputs


ROOT = Path(__file__).resolve().parents[1]


class ChapterGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chapters, cls.documents, _, cls.errors, _ = load_inputs(ROOT)

    def test_all_nine_chapters_have_traceable_nodes_and_relations(self):
        self.assertFalse(self.errors)
        self.assertEqual(len(self.chapters), 9)
        for chapter in self.chapters:
            with self.subTest(chapter=chapter["id"]):
                graph = build_chapter_graph(ROOT, chapter, self.documents)
                self.assertTrue(graph["nodes"])
                self.assertTrue(graph["relations"])
                ids = {node["node_id"] for node in graph["nodes"]}
                self.assertEqual(sum(len(section["node_ids"]) for section in graph["sections"]), len(ids))
                self.assertEqual(graph["review_status"], "pending")
                for node in graph["nodes"]:
                    self.assertTrue(node["source_locator"])
                    self.assertEqual(node["review_status"], "pending")
                    self.assertIn(node["source_kind"], {"fulltext", "extracted"})
                    self.assertEqual(node["source_status"], "effective")
                for relation in graph["relations"]:
                    self.assertIn(relation["from_node_id"], ids)
                    self.assertIn(relation["to_node_id"], ids)
                    self.assertTrue(relation["evidence"])
                    self.assertEqual(relation["review_status"], "pending")
                    self.assertIn(relation["source_kind"], {"fulltext", "extracted"})
                    self.assertEqual(relation["source_status"], "effective")

    def test_guide_branch_is_not_invented_as_a_relation(self):
        chapter = self.chapters[0]
        graph = build_chapter_graph(ROOT, chapter, self.documents)
        raw_relations = (ROOT / "data" / "chapters" / chapter["id"] / "relations.csv").read_text(encoding="utf-8-sig")
        self.assertTrue(all(edge["relation_id"] in raw_relations for edge in graph["relations"]))
        self.assertTrue(all(section["id"] not in {edge["type"] for edge in graph["relations"]}
                            for section in graph["sections"]))


if __name__ == "__main__":
    unittest.main()

"""The learning map is deliberately separate from pending source-relation indexing."""
import tempfile
import unittest
from pathlib import Path

from airworthiness import catalog
from airworthiness.graph_export import approved_graph_payload
from airworthiness.identity import build_document_identity
from airworthiness.ingest import load_inputs
from airworthiness.knowledge_maps import load_knowledge_maps, load_review_ledger, public_map


ROOT = Path(__file__).resolve().parents[1]


class KnowledgeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chapters, cls.documents, _, cls.errors, _ = load_inputs(ROOT)
        _, cls.ledger, cls.ledger_errors = load_review_ledger(ROOT)
        cls.maps, _, cls.map_errors = load_knowledge_maps(ROOT, cls.chapters, cls.documents, cls.ledger)

    def test_nine_manual_drafts_validate_without_changing_chapter_csvs(self):
        self.assertFalse(self.errors)
        self.assertFalse(self.ledger_errors)
        self.assertFalse(self.map_errors)
        self.assertEqual(set(self.maps), {f"ch{number:02}" for number in range(1, 10)})
        for chapter_id, item in self.maps.items():
            self.assertEqual(item["review_status"], "pending", chapter_id)
            self.assertTrue(item["nodes"], chapter_id)
            self.assertTrue(item["relations"], chapter_id)
            self.assertTrue(all(node["review_status"] == "pending" for node in item["nodes"]))
            self.assertTrue(all(relation["review_status"] == "pending" for relation in item["relations"]))

    def test_pending_drafts_are_not_public_or_ai_context(self):
        docs = {item["source_id"]: item for item in self.documents}
        for chapter_id, item in self.maps.items():
            with self.subTest(chapter=chapter_id):
                view = public_map(item, self.ledger, docs)
                self.assertFalse(view["available"])
                self.assertNotIn("nodes", view)

    def test_strict_identity_requires_url_code_and_markdown_hash(self):
        docs = [
            {"source_id": "CH01-S001", "chapter_id": "ch01", "url": "https://www.caac.gov.cn/a", "document_code": "AP- 21-R1", "sha256": "a" * 64, "title": "甲", "document_status": "effective", "review_status": "pending"},
            {"source_id": "CH02-S001", "chapter_id": "ch02", "url": "https://www.caac.gov.cn/a", "document_code": "ap-21-r1", "sha256": "a" * 64, "title": "乙", "document_status": "effective", "review_status": "pending"},
            {"source_id": "CH03-S001", "chapter_id": "ch03", "url": "https://www.caac.gov.cn/a", "document_code": "AP-21-R1", "sha256": "b" * 64, "title": "丙", "document_status": "effective", "review_status": "pending"},
        ]
        result = build_document_identity(docs)
        self.assertEqual(len(result["canonical_documents"]), 2)
        self.assertEqual(docs[0]["canonical_id"], docs[1]["canonical_id"])
        self.assertNotEqual(docs[0]["canonical_id"], docs[2]["canonical_id"])
        self.assertTrue(any(item["conflict_type"] == "same_url_different_identity" for item in result["conflicts"]))

    def test_catalog_persists_normalized_layers_and_hides_pending_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "library.sqlite3"
            catalog.build_catalog(ROOT, database)
            with catalog.connect(database) as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({"canonical_documents", "chapter_sources", "document_aliases", "identity_conflicts",
                                 "knowledge_maps", "knowledge_nodes", "knowledge_relations", "knowledge_source_refs",
                                 "review_ledger"} <= tables)
                self.assertEqual(db.execute("SELECT count(*) FROM chapter_sources").fetchone()[0], 189)
                self.assertGreater(db.execute("SELECT count(*) FROM knowledge_nodes").fetchone()[0], 0)
            self.assertFalse(catalog.knowledge_map(database, "ch01")["available"])
            self.assertIsNone(catalog.knowledge_node(database, "KM-CH01-N001"))
            exported = approved_graph_payload(database)
            self.assertEqual(exported["knowledge_nodes"], [])
            self.assertEqual(exported["knowledge_relations"], [])


if __name__ == "__main__":
    unittest.main()

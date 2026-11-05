"""Nine-chapter reading guides are navigation, never a substitute for source text."""
import tempfile
import unittest
from pathlib import Path

from airworthiness import catalog, ingest


ROOT = Path(__file__).resolve().parents[1]


class ChapterGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chapters, cls.documents, _, cls.errors, _ = ingest.load_inputs(ROOT)
        cls.documents_by_id = {doc["source_id"]: doc for doc in cls.documents}

    def test_all_nine_chapters_have_distinct_editorial_paths(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.chapters), 9)
        paths = set()
        for chapter in self.chapters:
            with self.subTest(chapter=chapter["id"]):
                guide = chapter["guide"]
                self.assertTrue(guide["positioning"])
                self.assertGreaterEqual(len(guide["sections"]), 4)
                titles = tuple(section["title"] for section in guide["sections"])
                self.assertEqual(len(titles), len(set(titles)))
                self.assertNotIn(titles, paths)
                paths.add(titles)

    def test_guide_references_are_effective_but_not_presented_as_approved(self):
        for chapter in self.chapters:
            for section in chapter["guide"]["sections"]:
                for ref in section["sources"]:
                    source_id = ref if isinstance(ref, str) else ref["source_id"]
                    with self.subTest(chapter=chapter["id"], source=source_id):
                        doc = self.documents_by_id[source_id]
                        self.assertEqual(doc["chapter_id"], chapter["id"])
                        self.assertEqual(doc["document_status"], "effective")
                        self.assertEqual(doc["review_status"], "pending")
                        if isinstance(ref, dict) and ref.get("locator"):
                            self.assertIn(doc["content_kind"], {"fulltext", "extracted"})
                            self.assertIn("".join(ref["locator"].split()), "".join(doc["body"].split()))

    def test_guide_html_and_original_body_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "catalog.sqlite3"
            catalog.build_catalog(ROOT, database)
            for entry in self.chapters:
                with self.subTest(chapter=entry["id"]):
                    page = catalog.chapter(database, entry["id"])
                    self.assertEqual(page["guide"], entry["guide"])
                    self.assertIn("本章定位", page["guide_html"])
                    self.assertIn("专题路径", page["guide_html"])
                    self.assertIn("跨章衔接", page["guide_html"])
            source_id = "CH06-S003"
            stored = catalog.document(database, source_id)
            self.assertEqual(stored["html"], catalog.render_document(self.documents_by_id[source_id]["body"],
                                                                           extracted=self.documents_by_id[source_id]["content_kind"] == "extracted")[0])


if __name__ == "__main__":
    unittest.main()

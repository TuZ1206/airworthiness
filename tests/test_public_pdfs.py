"""Only explicitly verified official administrative PDFs enter a Pages build."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from airworthiness.acquire_http import Download
from airworthiness.public_pdfs import prefetch, publication_candidates


URL = "https://www.caac.gov.cn/a.pdf"
PDF = b"%PDF-1.7\nfixture\n%%EOF"
DIGEST = hashlib.sha256(PDF).hexdigest()
FIELDS = "source_id,title,document_code,document_status,publish_date,url,sha256,crawled_at,review_status".split(",")


class FakeFetcher:
    def __init__(self, data=PDF, url=URL):
        self.data = data
        self.url = url
        self.calls = []

    def fetch(self, request):
        self.calls.append(request)
        return Download(self.data, self.url, "2026-10-15T00:00:00Z", "application/pdf")


class PublicPDFTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "data/acquired").mkdir(parents=True)
        (self.root / "data/chapters/ch01").mkdir(parents=True)

    def write(self, rows, manifest):
        with (self.root / "data/chapters/ch01/sources.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        (self.root / "data/acquired/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def row(self, sid="CH01-S001", code="CCAR-25-R4", status="effective", url="https://www.caac.gov.cn/a.html"):
        return dict(source_id=sid, title="资料", document_code=code, document_status=status,
                    publish_date="2026-01-01", url=url, sha256="0" * 64,
                    crawled_at="2026-10-15", review_status="pending")

    def acquired(self, digest=DIGEST, url=URL, kind="extracted"):
        return dict(content_kind=kind, originals=[dict(url=url, original_sha256=digest)])

    def test_policy_excludes_standards_obsolete_unknown_and_metadata(self):
        rows = [self.row(), self.row("CH01-S002", "GB/T 1447-2005"),
                self.row("CH01-S003", "AP-21-11R1", "repealed"),
                self.row("CH01-S004", "AC-25-01", "unknown"),
                self.row("CH01-S005", "CCAR-21-R5", url="https://example.com/a.html"),
                self.row("CH01-S006", "CCAR-25-R4")]
        manifest = {row["source_id"]: self.acquired(kind="metadata" if row["source_id"] == "CH01-S006" else "extracted") for row in rows}
        self.write(rows, manifest)
        candidates, conflicts = publication_candidates(self.root)
        self.assertEqual(conflicts, [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][3], ("CH01-S001",))

    def test_shared_pdf_is_downloaded_once_and_hash_checked(self):
        self.write([self.row(), self.row("CH01-S002", "AP-21-31R3")],
                   {"CH01-S001": self.acquired(), "CH01-S002": self.acquired()})
        fetcher = FakeFetcher()
        report = prefetch(self.root, fetcher=fetcher)
        self.assertEqual(fetcher.calls, [URL])
        self.assertEqual(len(report["verified"]), 1)
        self.assertEqual(report["verified"][0]["sources"], ("CH01-S001", "CH01-S002"))
        self.assertEqual(report["verified_bytes"], len(PDF))
        bad = prefetch(self.root, fetcher=FakeFetcher(PDF + b"changed"))
        self.assertEqual(bad["verified"], [])
        self.assertIn("SHA-256 mismatch", bad["skipped"][0]["reason"])

    def test_same_url_with_conflicting_hash_is_skipped(self):
        self.write([self.row(), self.row("CH01-S002", "AP-21-31R3")],
                   {"CH01-S001": self.acquired(), "CH01-S002": self.acquired("f" * 64)})
        candidates, conflicts = publication_candidates(self.root)
        self.assertEqual(candidates, [])
        self.assertEqual(conflicts, [URL])


if __name__ == "__main__":
    unittest.main()

"""Static publication contracts against small, real source/catalog fixtures."""
import csv
import gzip
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from airworthiness import catalog, ingest
from airworthiness.app import create_app


REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "src/airworthiness/web/static"
GLOSSARY_FIELDS = "term_id,term,aliases,definition,group,has_page,anchor_or_url,related_node_id,source_id,review_status,quote".split(",")
PDF_URL = "https://www.caac.gov.cn/fixture.pdf"
PDF = b"%PDF-1.7\nverified fixture bytes\n%%EOF\n"


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_inputs(root, count=3):
    """Two chapters, a cached-body candidate, an excerpt and a metadata gap."""
    chapters = [dict(id=f"ch{n:02}", title=f"测试章{n}", description="阅读说明", topics=["适航"])
                for n in (1, 2)]
    chapter_root = root / "data/chapters"
    chapter_root.mkdir(parents=True)
    (chapter_root / "catalog.json").write_text(json.dumps(chapters), encoding="utf-8")
    rows_by_chapter = {chapter["id"]: [] for chapter in chapters}
    for index in range(1, count + 1):
        cid = "ch02" if index == count else "ch01"
        sid = f"{cid.upper()}-S{index:03}"
        folder = chapter_root / cid / "documents"
        folder.mkdir(parents=True, exist_ok=True)
        body = "# 来源\n\n## " + ("仅登记" if cid == "ch02" else "摘录") + "\n\nAbC 适航\t材料，Case 保留。"
        path = folder / (sid + ".md")
        path.write_text(body, encoding="utf-8")
        rows_by_chapter[cid].append(dict(
            source_id=sid, title=f"MixedCase 适航材料 {index}", document_code=f"CCAR-{index}",
            document_status="effective", publish_date="2026-01-01",
            url=f"https://www.caac.gov.cn/source-{index}.html",
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), crawled_at="2026-01-02",
            review_status="pending"))
    for chapter in chapters:
        cid = chapter["id"]
        folder = chapter_root / cid
        write_csv(folder / "sources.csv", ingest.SOURCE_FIELDS, rows_by_chapter[cid])
        terms = []
        if cid == "ch01":
            terms.append(dict(term_id="CH01-T001", term="适航材料", aliases="", definition="编辑释义",
                              group="测试", has_page="true", anchor_or_url="#original-anchor",
                              related_node_id="", source_id="CH01-S001", review_status="pending", quote=""))
        write_csv(folder / "glossary.csv", GLOSSARY_FIELDS, terms)
    acquired = root / "data/acquired/documents"
    acquired.mkdir(parents=True)
    source = acquired / "fixture.md"
    source.write_text("## 正文\n\n## 第 1 页\n\n第九条 适航材料\n\nAbC 适航材料须核验。\n\nCase 保留 < 3。", encoding="utf-8")
    first = rows_by_chapter["ch01"][0]
    entry = dict(path="data/acquired/documents/fixture.md", content_kind="extracted",
                 note="机械提取，待复核。", source_sha256=first["sha256"], landing_url=first["url"],
                 url=PDF_URL, sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 original_sha256=hashlib.sha256(PDF).hexdigest(), method="fixture")
    (root / "data/acquired/manifest.json").write_text(json.dumps({first["source_id"]: entry}), encoding="utf-8")


def cache_pdf(root, url=PDF_URL, data=PDF):
    folder = root / ".cache/acquisition"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = folder / (key + ".bin")
    path.write_bytes(data)
    (folder / (key + ".json")).write_text(json.dumps(dict(
        request_url=url, url=url, original_sha256=hashlib.sha256(data).hexdigest(),
        size=len(data), redirects=[], content_type="application/pdf")), encoding="utf-8")
    return path


class StaticExportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("airworthiness.static_export"),
                             "Bounded static exporter is not implemented")
        self.module = importlib.import_module("airworthiness.static_export")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.root = self.work / "source"
        self.output = self.work / "published"
        make_inputs(self.root)

    def export(self, **kwargs):
        return self.module.export_site(self.root, self.output, **kwargs)

    def read_json(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def edit_manifest(self, **fields):
        path = self.root / "data/acquired/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["CH01-S001"].update(fields)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_exports_complete_api_shapes_and_byte_identical_gzip(self):
        report = self.export()
        required = {"index.html", "404.html", ".nojekyll", "quality/index.html", "manifest.json",
                    "data/overview.json", "data/quality.json", "data/resources.json"}
        for chapter in ("ch01", "ch02"):
            required.update({f"chapters/{chapter}/index.html", f"data/chapters/{chapter}.json",
                             f"data/search/{chapter}.json"})
        for sid in ("CH01-S001", "CH01-S002", "CH02-S003"):
            required.add(f"data/documents/{sid}.json")
        self.assertTrue(all((self.output / name).is_file() for name in required))
        files = {p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()}
        for name in required:
            if name.endswith(".json"):
                self.assertIn(name + ".gz", files)
                self.assertEqual(gzip.decompress((self.output / (name + ".gz")).read_bytes()),
                                 (self.output / name).read_bytes())
        self.assertEqual(self.read_json("data/overview.json")["totals"]["sources"], 3)
        self.assertEqual(set(self.read_json("data/resources.json")), {"items"})
        self.assertEqual(len(self.read_json("data/resources.json")["items"]), 3)
        manifest = self.read_json("manifest.json")
        self.assertEqual(report, manifest)
        self.assertEqual((manifest["source_count"], manifest["document_count"], manifest["chapter_count"],
                          manifest["original_count"]), (3, 3, 2, 0))
        self.assertTrue(manifest["generated_at"])
        self.assertIsNone(manifest["source_revision"])
        for asset in STATIC.iterdir():
            if re.fullmatch(r"hall(?:-[a-z]+)*\.(?:js|css)", asset.name):
                self.assertEqual((self.output / "static" / asset.name).read_bytes(), asset.read_bytes())

    def test_template_routes_mode_and_safe_404_work_under_nested_base(self):
        self.export(base_path="/team/airworthiness/")
        for name in ("index.html", "quality/index.html", "chapters/ch01/index.html", "chapters/ch02/index.html"):
            soup = BeautifulSoup((self.output / name).read_text(encoding="utf-8"), "html.parser")
            self.assertEqual(soup.find("meta", attrs={"name": "airworthiness-mode"})["content"], "static")
            self.assertEqual(soup.find("meta", attrs={"name": "airworthiness-base"})["content"], "/team/airworthiness")
            self.assertIsNotNone(soup.select_one("#chapter-rail"))
            self.assertEqual(soup.select_one("a.brand")["href"], "/team/airworthiness/")
            self.assertIsNone(soup.select_one('.main-nav'))
            self.assertIsNone(soup.select_one('a[href="/team/airworthiness/quality/"]'))
            for node in soup.select("[href], [src]"):
                value = node.get("href", node.get("src"))
                if value.startswith("/"):
                    self.assertTrue(value.startswith("/team/airworthiness/"), value)
        term = self.read_json("data/chapters/ch01.json")["glossary"][0]
        self.assertTrue(term["anchor_or_url"].startswith("/team/airworthiness/chapters/ch01/?source=CH01-S001#"))
        self.assertEqual(term["original_anchor_or_url"], "#original-anchor")
        missing = BeautifulSoup((self.output / "404.html").read_text(encoding="utf-8"), "html.parser")
        self.assertIsNone(missing.find("script"))
        self.assertIsNone(missing.find("meta", attrs={"http-equiv": "refresh"}))
        self.assertEqual(missing.find("a")["href"], "/team/airworthiness/")

    def test_root_base_has_no_double_slash(self):
        self.export(base_path="/")
        soup = BeautifulSoup((self.output / "index.html").read_text(encoding="utf-8"), "html.parser")
        self.assertEqual(soup.find("meta", attrs={"name": "airworthiness-base"})["content"], "")
        self.assertIsNone(soup.select_one('.main-nav'))
        self.assertEqual(soup.find("script")["src"], "/static/hall.js")

    def test_online_shell_labels_change_only_in_exported_html(self):
        template = REPO / "src/airworthiness/web/templates/hall.html"
        before = template.read_bytes()
        self.export()
        for name in ("index.html", "quality/index.html", "chapters/ch01/index.html"):
            html = (self.output / name).read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "html.parser")
            self.assertEqual(soup.title.string, "适航法规资源馆")
            self.assertEqual(soup.select_one("a.brand")["aria-label"], "适航法规资源馆首页")
            self.assertIn("适航法规资源馆", soup.select_one("#site-footer").get_text())
            self.assertEqual(soup.select_one(".edition-label").get_text(), "在线验收版")
            self.assertIn("在线资料", soup.noscript.get_text())
            self.assertNotIn("适航离线资源馆", html)
            self.assertNotIn("离线资料库", html)
        self.assertEqual(template.read_bytes(), before)

    def test_static_shell_csp_precedes_all_styles_and_scripts(self):
        self.export()
        expected = ("default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
        for name in ("index.html", "quality/index.html", "chapters/ch01/index.html", "chapters/ch02/index.html"):
            soup = BeautifulSoup((self.output / name).read_text(encoding="utf-8"), "html.parser")
            policies = soup.find_all("meta", attrs={"http-equiv": "Content-Security-Policy"})
            self.assertEqual(len(policies), 1)
            self.assertEqual(policies[0]["content"], expected)
            children = list(soup.head.children)
            for asset in soup.head.select("link, script"):
                self.assertLess(children.index(policies[0]), children.index(asset))

    def test_missing_required_assets_fail_before_creating_output(self):
        factory = self.module.create_app
        for missing in self.module.STATIC_ASSETS:
            with self.subTest(missing=missing):
                assets = self.work / ("assets-without-" + missing)
                assets.mkdir()
                for name in self.module.STATIC_ASSETS:
                    if name != missing:
                        (assets / name).write_bytes((STATIC / name).read_bytes())

                def app_with_fixture_assets(settings):
                    app = factory(settings)
                    app.static_folder = str(assets)
                    return app

                self.output = self.work / ("output-without-" + missing)
                # Redirect the asset location only; catalog, renderer and files are real.
                with patch.object(self.module, "create_app", side_effect=app_with_fixture_assets):
                    with self.assertRaisesRegex(ValueError, "Required static asset.*" + re.escape(missing)):
                        self.export()
                self.assertFalse(self.output.exists())

    def test_documents_search_and_review_evidence_match_real_catalog(self):
        database = self.work / "expected.sqlite3"
        client = create_app(dict(TESTING=True, DATA_ROOT=self.root, DATABASE=database)).test_client()
        self.export()
        self.assertEqual(self.read_json("data/overview.json"), client.get("/api/overview").json)
        actual_quality = self.read_json("data/quality.json")
        expected_quality = client.get("/api/quality").json
        actual_quality.pop("generated_at")
        expected_quality.pop("generated_at")
        self.assertEqual(actual_quality, expected_quality)
        with catalog.connect(database) as db:
            rows = db.execute("SELECT payload,search_text FROM documents ORDER BY chapter_id,source_id").fetchall()
        public = self.read_json("data/resources.json")["items"]
        self.assertEqual(public, [catalog._public(json.loads(row["payload"])) for row in rows])
        for row in rows:
            payload = json.loads(row["payload"])
            sid = payload["source_id"]
            actual = self.read_json(f"data/documents/{sid}.json")
            expected = client.get(f"/api/documents/{sid}").json
            for field in ("html", "toc", "sha256", "review_status", "body_provenance", "uploaded_provenance",
                          "source_id", "extraction_note", "related_sources", "resolved_issues"):
                self.assertEqual(actual[field], expected[field], field)
            self.assertEqual(actual["body"], payload["body"])
            self.assertEqual(actual["deployment_mode"], "static")
            self.assertEqual((actual["original_available"], actual["original_url"], actual["originals"]), (False, "", []))
            self.assertEqual(actual["static_originals"], [])
            entries = self.read_json(f'data/search/{payload["chapter_id"]}.json')
            entry = next(item for item in entries if item["source_id"] == sid)
            self.assertEqual(set(entry), {"source_id", "search_text", "plain"})
            self.assertEqual(entry["search_text"], row["search_text"])
            plain = re.sub(r"\s+", "", re.sub(r"(?m)^#{1,6}\s+", "", payload["body"]))
            self.assertEqual(entry["plain"], plain)
            self.assertIn("AbC", entry["plain"])

    def test_resources_include_rows_beyond_catalog_page_limit(self):
        bigger = self.work / "many-sources"
        make_inputs(bigger, count=102)
        self.module.export_site(bigger, self.output)
        items = self.read_json("data/resources.json")["items"]
        self.assertEqual(len(items), 102)
        self.assertEqual(items[-1]["source_id"], "CH02-S102")

    def test_original_data_is_immutable_and_private_files_and_paths_are_not_published(self):
        for name in (".env", ".git/private", ".cache/library.sqlite3", "private.txt"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PRIVATE-SENTINEL", encoding="utf-8")
        self.edit_manifest(cache_path=str(self.root / ".cache/private.bin"),
                           error="PRIVATE-SENTINEL: " + str(self.root / "private.txt"),
                           diagnostics=dict(local_path=str(self.root)))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.export()
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        for path in self.output.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.output)
            self.assertFalse(set(relative.parts) & {".env", ".git", ".cache"}, relative)
            self.assertNotEqual(path.suffix, ".sqlite3")
            if path.suffix in {".html", ".json", ".js", ".css"}:
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("PRIVATE-SENTINEL", content)
                self.assertNotIn(str(self.root), content)
                self.assertNotIn(str(self.root).replace("\\", "\\\\"), content)

    def test_unsafe_base_paths_are_rejected_before_writes(self):
        for base in ("relative", "//evil.example", "/../x", "/x/../y", "/./x", "/a//b", "/a?b", "/a#b",
                     "/%2e%2e", "/a\\b", "/a\n", '/a"b', "/a:b", "https://example.com"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                self.export(base_path=base)
            self.assertFalse(self.output.exists())

    def test_dotted_base_segments_are_rejected_to_match_browser_validation(self):
        for index, base in enumerate(("/v1.0", "/.hidden", "/team/site.name", "/site./")):
            with self.subTest(base=base):
                self.output = self.work / f"dotted-base-{index}"
                with self.assertRaises(ValueError):
                    self.export(base_path=base)
                self.assertFalse(self.output.exists())

    def test_protected_destinations_are_rejected_without_changes(self):
        targets = [self.root, self.root.parent, self.root / "data", self.root / "data/new-site",
                   self.root / ".git", self.root / ".git/new-site", Path.home(), *self.root.parents]
        for target in targets:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.module.export_site(self.root, target)
        self.assertFalse((self.root / "data/new-site").exists())
        self.assertFalse((self.root / ".git").exists())

    def test_only_new_or_empty_output_is_accepted_and_existing_files_survive(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual(marker.read_text(), "keep")
        alternate = self.work / "empty"
        alternate.mkdir()
        self.module.export_site(self.root, alternate)
        with self.assertRaises(ValueError):
            self.module.export_site(self.root, marker)
        with self.assertRaises(ValueError):
            self.module.export_site(self.root, alternate)
        self.assertTrue((alternate / "index.html").is_file())

    def test_output_symlink_and_symlink_ancestor_are_rejected(self):
        target = self.work / "untouched"
        target.mkdir()
        link = self.work / "linked"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"Symlink creation unavailable: {exc}")
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(os.rmdir, link)
        else:
            self.addCleanup(link.unlink)
        for output in (link, link / "nested"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.module.export_site(self.root, output)
        self.assertEqual(list(target.iterdir()), [])

    def test_missing_originals_are_not_downloaded_or_advertised(self):
        # A socket tripwire guarantees an optional cache miss stays offline.
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            self.export(include_originals=True)
        self.assertFalse((self.output / "originals").exists())
        doc = self.read_json("data/documents/CH01-S001.json")
        self.assertEqual(doc["static_originals"], [])
        self.assertEqual(doc["body_provenance"]["url"], PDF_URL)

    def test_verified_originals_are_opt_in_and_separate_from_server_urls(self):
        cache_pdf(self.root)
        self.export()
        self.assertFalse((self.output / "originals").exists())
        self.assertEqual(self.read_json("data/documents/CH01-S001.json")["static_originals"], [])
        self.output = self.work / "with-originals"
        self.export(include_originals=True)
        doc = self.read_json("data/documents/CH01-S001.json")
        self.assertEqual((doc["original_available"], doc["original_url"], doc["originals"]), (False, "", []))
        self.assertEqual(doc["static_originals"], [dict(label="本地 PDF 原件", url="/airworthiness/originals/CH01-S001/0.pdf")])
        self.assertEqual((self.output / "originals/CH01-S001/0.pdf").read_bytes(), PDF)
        self.assertEqual(self.read_json("manifest.json")["original_count"], 1)

    def test_tampered_cache_is_never_copied(self):
        path = cache_pdf(self.root)
        path.write_bytes(PDF + b"tampered")
        self.export(include_originals=True)
        self.assertFalse((self.output / "originals").exists())
        self.assertEqual(self.read_json("manifest.json")["original_count"], 0)

    def test_cached_copyright_restricted_standard_is_not_published(self):
        cache_pdf(self.root)
        sources = self.root / "data/chapters/ch01/sources.csv"
        with sources.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["document_code"] = "GB/T 1447-2005"
        write_csv(sources, ingest.SOURCE_FIELDS, rows)
        self.export(include_originals=True)
        self.assertEqual(self.read_json("manifest.json")["original_count"], 0)
        self.assertEqual(self.read_json("data/documents/CH01-S001.json")["static_originals"], [])

    def test_original_20_mib_boundary_is_enforced(self):
        for size in (20 * 1024 * 1024, 20 * 1024 * 1024 + 1):
            with self.subTest(size=size):
                data = PDF + b" " * (size - len(PDF))
                cache_pdf(self.root, data=data)
                self.edit_manifest(original_sha256=hashlib.sha256(data).hexdigest())
                self.output = self.work / str(size)
                self.export(include_originals=True)
                included = size <= 20 * 1024 * 1024
                self.assertEqual((self.output / "originals/CH01-S001/0.pdf").exists(), included)
                self.assertEqual(self.read_json("manifest.json")["original_count"], int(included))

    def test_total_original_budget_skips_excess_and_preserves_attachment_indexes(self):
        cache_pdf(self.root)
        second_url = "https://www.caac.gov.cn/appendix.pdf"
        cache_pdf(self.root, second_url)
        self.edit_manifest(originals=[
            dict(label="未缓存", url="https://www.caac.gov.cn/missing.pdf", original_sha256="0" * 64),
            dict(label="主文", url=PDF_URL, original_sha256=hashlib.sha256(PDF).hexdigest()),
            dict(label="附录", url=second_url, original_sha256=hashlib.sha256(PDF).hexdigest())])
        self.assertEqual(self.module.MAX_ORIGINALS_BYTES, 350 * 1024 * 1024)
        # Lower only the budget; real hash checking and file writes still run.
        with patch.object(self.module, "MAX_ORIGINALS_BYTES", len(PDF)):
            self.export(include_originals=True)
        doc = self.read_json("data/documents/CH01-S001.json")
        self.assertEqual(doc["static_originals"], [dict(label="主文", url="/airworthiness/originals/CH01-S001/1.pdf")])
        self.assertEqual(len(doc["body_provenance"]["originals"]), 3)
        self.assertFalse((self.output / "originals/CH01-S001/2.pdf").exists())

    def test_site_size_limit_stops_before_exceeding_pages_budget(self):
        self.assertLessEqual(self.module.MAX_SITE_BYTES, 1024 ** 3)
        with patch.object(self.module, "MAX_SITE_BYTES", 128), self.assertRaises(ValueError):
            self.export()
        self.assertLess(sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file()), 128)
        self.assertFalse((self.output / "manifest.json").exists())

    def test_cli_exports_without_starting_a_server_and_rejects_reuse(self):
        command = [sys.executable, "-m", "airworthiness.static_export", "--root", str(self.root),
                   "--output", str(self.output), "--base-path", "/cli", "--include-originals"]
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.read_json("manifest.json"))
        failed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertNotEqual(failed.returncode, 0)
        self.assertNotIn("Traceback", failed.stderr)
        self.assertTrue((self.output / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()

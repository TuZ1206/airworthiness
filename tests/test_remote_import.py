"""Offline contract tests; response fixtures model web.run strings, not HTTP bytes."""
import copy
import csv
import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
SPEC = importlib.util.find_spec("airworthiness.remote_import")
remote = importlib.import_module("airworthiness.remote_import") if SPEC else None
URL = "https://xxgk.mot.gov.cn/2020/gz/202403/rule.html"
LANDING = "https://www.caac.gov.cn/XXGK/CCAR21-R5.html"
PDF = "https://www.caac.gov.cn/rule.pdf"
STAMP = "2026-10-13T09:00:00+08:00"
SID = "CH01-S001"
CODE, DATE = "CCAR-21-R5", "2024-02-18"
VERSION = CODE + " " + DATE
TITLE = "民用航空产品和零部件合格审定规定 " + VERSION
BODY = {1: "第一章 总则", 2: "", 3: "第21.1条 保留  原文。", 4: "第二条 不得改写。"}


def response(lines, *, url=URL, total=6, pages=None, title=TITLE,
             ref="turn19view0", inline=False):
    media = "application/pdf" if pages is not None else "text/html"
    page_header = f"Number of pages: {pages}; " if pages is not None else ""
    header = (f"{title} ({url})\ncite{ref} [wordlim: 200] Crawled: today; "
              f"Content type: {media}; {page_header}"
              f'Source: open({{"ref_id":"{url}","lineno":null}}); Total lines: {total}\n')
    return header + (" " if inline else "\n").join(f"L{n}: {value}" for n, value in lines.items()) + "\n"


def identity(url=URL):
    return dict(urls=[LANDING, url], note="CAAC CCAR-21-R5通知与MOT正文均对应2024年第5号令、2024年2月18日修订。",
                source_bindings={f"CH01-S{n:03}": dict(source_sha256=f"{n:064x}", document_code=CODE,
                                                     publish_date=DATE) for n in range(1, 4)},
                version_evidence=[dict(kind="response", url=url, quote=VERSION,
                                       source_ids=[SID, "CH01-S002", "CH01-S003"])])


def snapshot(**changes):
    value = dict(url=URL, source_ids=[SID], responses=[response({0: "[Input]", **BODY, 5: "页脚"})],
                 line_start=1, line_end=4, captured_at=STAMP,
                 identity_evidence=identity())
    value.update(changes)
    return value


def pdf_snapshot():
    return snapshot(url=PDF, line_start=0, line_end=3,
                    responses=[response({"0@P0": "第一页", "1@P0": "条款一",
                                         "2@P1": "第二页", "3@P1": "条款二"},
                                        url=PDF, total=4, pages=2)],
                    identity_evidence=identity(PDF))


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(remote, "Missing remote_import implementation")

    def test_real_header_newline_overlap_and_exact_whitespace(self):
        first = response({0: "[Input]", 1: BODY[1], 2: ""})
        second = response({2: "", 3: BODY[3], 4: BODY[4] + "  ", 5: "页脚"}, ref="turn20view0")
        parsed = remote.parse_remote_responses(URL, [second, first])
        self.assertEqual(parsed["total_lines"], 6)
        self.assertEqual(parsed["lines"][4], (None, BODY[4] + "  "))
        checked = remote.validate_remote_snapshot(snapshot(responses=[second, first]))
        self.assertEqual(checked["text"], "第一章 总则\n\n第21.1条 保留  原文。\n第二条 不得改写。  ")
        self.assertEqual(checked["method"], "web-tool-html-text")

    def test_sparse_windows_can_fill_each_others_gaps(self):
        checked = remote.validate_remote_snapshot(snapshot(responses=[response({1: BODY[1], 3: BODY[3]}),
                                                                       response({2: "", 4: BODY[4]})]))
        self.assertEqual(checked["text"], "\n".join(BODY.values()))

    def test_embedded_line_notation_cannot_fill_a_missing_physical_line(self):
        for raw in [response({1: "original L2: embedded notation", 3: "text", 4: "end"}), response(BODY, inline=True)]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(responses=[raw]))
        raw = response({1: "original L2: embedded notation", 2: "real line two", 3: "text", 4: "end"})
        try:
            parsed = remote.parse_remote_responses(URL, [raw])
        except ValueError as exc:
            self.fail(f"Embedded literal text is not a line delimiter: {exc}")
        self.assertEqual(parsed["lines"][1][1], "original L2: embedded notation")

    def test_real_click_source_header_is_accepted_with_matching_destination(self):
        raw = response(BODY).replace(f'open({{"ref_id":"{URL}","lineno":null}})',
                                     'click({"ref_id":"turn53view1","id":3})')
        try:
            parsed = remote.parse_remote_responses(URL, [raw])
        except ValueError as exc:
            self.fail(f"Real click header rejected: {exc}")
        self.assertEqual(parsed["url"], URL)
        for bad in [raw.replace('"id":3', '"id":true'), raw.replace('"id":3', '"id":-1')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                remote.parse_remote_responses(URL, [bad])

    def test_crlf_and_repeated_windows_do_not_change_text(self):
        raw = response(BODY)
        checked = remote.validate_remote_snapshot(snapshot(responses=[raw, raw.replace("\n", "\r\n")]))
        self.assertEqual(checked["text"], "\n".join(BODY.values()))

    def test_known_link_markers_restore_visible_text_without_inventing_href(self):
        raw = response({1: "依照cite12†原始规定及【13†附件】。",
                        2: "[官网附件](https://www.caac.gov.cn/rule.pdf)", 3: "空白  保留", 4: "结束"})
        checked = remote.validate_remote_snapshot(snapshot(responses=[raw]))
        self.assertEqual(checked["text"], "依照原始规定及附件。\n[官网附件](https://www.caac.gov.cn/rule.pdf)\n空白  保留\n结束")

    def test_images_and_formulas_count_occurrences_not_repeated_windows(self):
        raw = response({1: "公式：cite12†Imagecite15†Image", 2: "【13†Image: 公式】", 3: "见【14†规定】", 4: "结束"})
        checked = remote.validate_remote_snapshot(snapshot(responses=[raw, raw]))
        self.assertEqual(checked["text"].count("[原文包含图像/公式，见官方原文]"), 3)
        self.assertEqual(checked["non_text_elements"], 3)
        self.assertIn("见规定", checked["text"])
        self.assertEqual(remote.validate_remote_snapshot(snapshot())["non_text_elements"], 0)

    def test_missing_lines_bounds_conflicts_and_inconsistent_totals_rejected(self):
        bad = [snapshot(responses=[response({1: "a", 3: "c", 4: "d"})]),
               snapshot(line_start=-1), snapshot(line_end=6), snapshot(line_start=4, line_end=1),
               snapshot(line_start=True), snapshot(line_end="4"),
               snapshot(responses=[response(BODY), response({4: "冲突"})]),
               snapshot(responses=[response(BODY), response({0: "前页冲突"}), response({0: "不同"})]),
               snapshot(responses=[response(BODY), response(BODY, total=7)]),
               snapshot(responses=[response({**BODY, 6: "越界"})]),
               snapshot(responses=[response({2: "", 1: "倒序", 3: "a", 4: "b"})])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(value)

    def test_response_provenance_must_be_official_matching_and_not_search(self):
        raw = response(BODY)
        variants = [raw.replace(URL, "https://evil.org/copied.html"),
                    raw.replace(URL, LANDING, 1), raw.replace("turn19view0", "turn19search0"),
                    raw.replace(f'"ref_id":"{URL}"', f'"ref_id":"{LANDING}"'),
                    raw.replace("text/html", "text/plain"), raw.replace("Total lines: 6", "Total lines: ?"),
                    raw.replace("Total lines: 6", "Total lines: 6; Total lines: 7"),
                    "搜索摘要：" + raw, "L1: 自编正文\nL2: 无来源", "Internal Error ()\nFailed to fetch"]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(responses=[value]))
        valid = raw.replace(f'"ref_id":"{URL}"', '"ref_id":"turn19view0"')
        self.assertTrue(remote.validate_remote_snapshot(snapshot(responses=[valid]))["text"])

    def test_bad_urls_and_missing_identity_rejected(self):
        bad_urls = ["https://gov.cn.evil.org/a", "https://fakegov.cn/a", "https://user@gov.cn/a",
                    "https://gov.cn:8443/a", "file:///a", "https://127.0.0.1/a"]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(url=url))
        for evidence in [None, {}, {"urls": [URL], "note": " "}, {"urls": [LANDING], "note": "同版"},
                         {"urls": [URL, "https://evil.org/a"], "note": "同版"}]:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(identity_evidence=evidence))

    def test_open_of_search_reference_is_a_body_not_a_search_summary(self):
        raw = response(BODY).replace(f'"ref_id":"{URL}"', '"ref_id":"turn18search2"')
        try:
            checked = remote.validate_remote_snapshot(snapshot(responses=[raw]))
        except ValueError as exc:
            self.fail(f"Valid open response rejected: {exc}")
        self.assertEqual(checked["text"], "\n".join(BODY.values()))

    def test_pdf_header_without_title_and_fragmented_windows(self):
        value = pdf_snapshot()
        value["responses"] = [response({"0@P0": "第一页", "2@P1": "第二页"}, url=PDF, pages=2, total=4),
                              response({"1@P0": "条款一", "3@P1": "条款二"}, url=PDF, pages=2, total=4)]
        value["responses"] = [raw.replace(TITLE + " ", "") for raw in value["responses"]]
        value["identity_evidence"].update(urls=[PDF], version_evidence=[])
        try:
            checked = remote.validate_remote_snapshot(value)
        except ValueError as exc:
            self.fail(f"Valid untitled PDF rejected: {exc}")
        self.assertEqual(checked["text"], remote.validate_remote_snapshot(pdf_snapshot())["text"])

    def test_duplicate_or_malformed_header_fields_are_not_ignored(self):
        raw = response(BODY)
        for original, replacement in [("Total lines: 6", "Total lines: 6; Total lines: ?"),
                                      ("Content type: text/html;", "Content type: text/html; Content type: ;"),
                                      ("Total lines: 6", 'Source: open({"ref_id":"turn19view0"}); Total lines: 6')]:
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(responses=[raw.replace(original, replacement)]))

    def test_invalid_shape_and_timestamp_are_validation_errors(self):
        variants = [snapshot(responses=[]), snapshot(responses="not a list"), snapshot(responses=[None]),
                    snapshot(source_ids=[]), snapshot(source_ids=[SID, SID]), snapshot(source_ids="S1"),
                    snapshot(captured_at="yesterday"), snapshot(captured_at="2026-10-13T09:00:00"),
                    snapshot(captured_at=None), None, {}]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(value)

    def test_empty_error_pages_and_unrecognized_tool_markers_rejected(self):
        for text in ["", "Access Denied", "404 Not Found", "页面不存在", "安全验证 验证码",
                     "Failed to fetch https://www.gov.cn/", "[Input: 搜索]", "[Button: next]",
                     "citeturn19view0", "【turn19search0】", "unknown",
                     "[truncated]", "... 300 tokens truncated ...", "Output truncated", "[Image: 条款扫描图]"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(snapshot(responses=[response({1: text, 2: "", 3: "", 4: ""})]))
        with self.assertRaises(ValueError):
            remote.validate_remote_snapshot(snapshot(responses=[response(BODY, title="403 Forbidden")]))

    def test_pdf_requires_all_lines_all_pages_and_preserves_page_markers(self):
        checked = remote.validate_remote_snapshot(pdf_snapshot())
        self.assertEqual(checked["page_count"], 2)
        self.assertEqual(checked["method"], "web-tool-pdf-text")
        self.assertEqual(checked["text"], "## 第 1 页\n\n第一页\n条款一\n\n## 第 2 页\n\n第二页\n条款二")
        self.assertEqual([page for page, _ in checked["lines"].values()], [0, 0, 1, 1])
        bad = [pdf_snapshot(), pdf_snapshot(), pdf_snapshot(), pdf_snapshot(), pdf_snapshot(), pdf_snapshot()]
        bad[0]["line_end"] = 2
        bad[1]["responses"][0] = bad[1]["responses"][0].replace("@P1", "@P0")
        bad[2]["responses"][0] = bad[2]["responses"][0].replace("L1@P0: 条款一\n", "")
        bad[3]["responses"][0] = bad[3]["responses"][0].replace("L2@P1", "L2@P2")
        bad[4]["responses"][0] = bad[4]["responses"][0].replace("L3@P1", "L3@P0")
        bad[5]["responses"][0] = bad[5]["responses"][0].replace("Number of pages: 2; ", "")
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(value)

    def test_mixed_pdf_metadata_and_pdf_disguised_as_html_rejected(self):
        good = pdf_snapshot()
        bad = [snapshot(url=PDF, responses=[response(BODY, url=PDF)]),
               snapshot(responses=[response({"1@P0": "not html", 2: "", 3: "", 4: ""})]),
               dict(good, responses=good["responses"] + [good["responses"][0].replace("pages: 2", "pages: 3")]),
               dict(good, responses=[good["responses"][0].replace("@P0", "")])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.validate_remote_snapshot(value)

    def test_standard_status_pages_cannot_be_promoted_to_extracted_body(self):
        url = "https://std.samr.gov.cn/detail?id=1"
        with self.assertRaises(ValueError):
            remote.validate_remote_snapshot(snapshot(url=url, responses=[response(BODY, url=url)],
                                                    identity_evidence=dict(urls=[url], note="状态页")))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(remote, "Missing remote_import implementation")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        chapter = self.root / "data/chapters/ch01"
        chapter.mkdir(parents=True)
        self.csv = chapter / "sources.csv"
        with self.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_id", "title", "url", "sha256", "document_code", "publish_date"])
            writer.writeheader()
            for n in range(1, 190):
                writer.writerow(dict(source_id=f"CH01-S{n:03}", title="来源登记",
                                     url=LANDING if n < 4 else f"https://www.caac.gov.cn/{n}.html", sha256=f"{n:064x}",
                                     document_code=CODE, publish_date=DATE))
        self.output = self.root / "data/acquired"
        self.output.mkdir(parents=True)
        self.old = {f"CH01-S{n:03}": dict(content_kind="failed", path="", error="SSL failure", custom=n)
                    for n in range(1, 190)}
        self.save("manifest.json", self.old)
        self.save("report.json", dict(counts={"failed": 189}, requests=[{"status": 403}],
                                      results={LANDING: {"content_kind": "failed"}}, custom="retain"))
        (self.output / "attempts.jsonl").write_bytes(b'{"status":403}\n')

    def save(self, name, value):
        (self.output / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def existing(self, sid=SID, kind="extracted", chars=999, pages=0, **extra):
        path = "data/acquired/documents/shared-old.md"
        document = self.root / path
        document.parent.mkdir(exist_ok=True)
        document.write_bytes(b"Original text that must survive")
        entry = dict(content_kind=kind, path=path, sha256=hashlib.sha256(document.read_bytes()).hexdigest(),
                     text_chars=chars, page_count=pages, source_sha256=f"{int(sid[-3:]):064x}",
                     landing_url=LANDING, url=LANDING, note="previous", **extra)
        self.old[sid] = entry
        self.save("manifest.json", self.old)
        return copy.deepcopy(entry)

    def test_import_binds_csv_keeps_189_entries_and_preserves_snapshot_bytes(self):
        original_csv = self.csv.read_bytes()
        value = snapshot(source_ids=[SID, "CH01-S002"])
        untouched_input = copy.deepcopy(value)
        manifest = remote.import_remote_snapshot(self.root, value)
        self.assertEqual(len(manifest), 189)
        for sid in set(self.old) - {SID, "CH01-S002"}:
            self.assertEqual(manifest[sid], self.old[sid])
        item = manifest[SID]
        self.assertEqual(item["content_kind"], "extracted")
        self.assertEqual(item["review_status"], "pending")
        self.assertEqual(item["source_sha256"], f"{1:064x}")
        self.assertEqual(item["landing_url"], LANDING)
        self.assertEqual(item["url"], URL)
        self.assertEqual(item["actual_url"], URL)
        self.assertEqual(item["identity_evidence"], value["identity_evidence"])
        self.assertEqual(item["source_lines"], [1, 4])
        self.assertEqual(item["total_lines"], 6)
        self.assertEqual(item["original_sha256"], "")
        self.assertEqual(item["method"], "web-tool-html-text")
        self.assertEqual(item["crawled_at"], STAMP)
        self.assertIn("待核验", item["note"])
        document = (self.root / item["path"]).read_bytes()
        cached = (self.root / item["snapshot_path"]).read_bytes()
        self.assertTrue(item["snapshot_path"].startswith(".cache/"))
        self.assertEqual(item["sha256"], hashlib.sha256(document).hexdigest())
        self.assertEqual(item["tool_snapshot_sha256"], hashlib.sha256(cached).hexdigest())
        self.assertEqual(json.loads(cached), value)
        self.assertIn("\n".join(BODY.values()), document.decode())
        self.assertNotIn("[Input]", document.decode())
        self.assertEqual(item["path"], manifest["CH01-S002"]["path"])
        self.assertEqual(manifest["CH01-S002"]["source_sha256"], f"{2:064x}")
        self.assertEqual(self.read("manifest.json"), manifest)
        self.assertEqual(self.csv.read_bytes(), original_csv)
        self.assertEqual(value, untouched_input)

    def test_journal_appends_report_counts_update_and_history_survives(self):
        remote.import_remote_snapshot(self.root, snapshot())
        first = (self.output / "attempts.jsonl").read_bytes()
        self.assertTrue(first.startswith(b'{"status":403}\n'))
        remote.import_remote_snapshot(self.root, snapshot())
        journal = (self.output / "attempts.jsonl").read_bytes()
        self.assertTrue(journal.startswith(first))
        events = [json.loads(line) for line in journal.splitlines()]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]["preserved_source_ids"], [SID])
        self.assertEqual(events[-1]["updated_source_ids"], [])
        self.assertEqual(events[-1]["actual_url"], URL)
        self.assertEqual(events[-1]["identity_evidence"], snapshot()["identity_evidence"])
        report = self.read("report.json")
        self.assertEqual(report["counts"], {"extracted": 1, "failed": 188})
        self.assertEqual(report["unique_url_counts"], {"extracted": 1, "failed": 186})
        self.assertEqual(report["source_records"], 189)
        self.assertEqual(report["unique_source_urls"], 187)
        self.assertEqual(report["custom"], "retain")
        self.assertEqual(report["requests"], [{"status": 403}])
        self.assertEqual(report["results"], {LANDING: {"content_kind": "failed"}})
        self.assertEqual(len(report["remote_imports"]), 2)

    def test_only_worse_verified_records_are_replaced_per_source(self):
        good = self.existing(kind="fulltext")
        manifest = remote.import_remote_snapshot(self.root, snapshot(source_ids=[SID, "CH01-S002"]))
        self.assertEqual(manifest[SID], good)
        self.assertEqual(manifest["CH01-S002"]["content_kind"], "extracted")
        self.assertNotEqual(manifest["CH01-S002"]["path"], good["path"])
        self.assertEqual((self.root / good["path"]).read_bytes(), b"Original text that must survive")

    def test_equal_or_longer_existing_extracted_text_and_more_pages_are_kept(self):
        for chars, pages in [(999, 0), (len("\n".join(BODY.values())), 0), (1, 2)]:
            with self.subTest(chars=chars, pages=pages):
                old = self.existing(chars=chars, pages=pages)
                self.assertEqual(remote.import_remote_snapshot(self.root, snapshot())[SID], old)

    def test_strict_improvement_replaces_metadata_or_shorter_equal_rank(self):
        for kind in ["metadata", "extracted"]:
            with self.subTest(kind=kind):
                self.existing(kind=kind, chars=1)
                self.assertEqual(remote.import_remote_snapshot(self.root, snapshot())[SID]["url"], URL)

    def test_whitespace_growth_cannot_discard_existing_original_evidence(self):
        import pymupdf
        value = pdf_snapshot()
        value["responses"][0] = value["responses"][0].replace("第一页", "第一页" + " " * 100)
        with pymupdf.open() as document:
            for text in ["Original page one", "Original page two"]:
                document.new_page().insert_text((40, 60), text)
            raw = document.tobytes()
        raw_hash = hashlib.sha256(raw).hexdigest()
        raw_path = ".cache/acquisition/original.bin"
        (self.root / raw_path).parent.mkdir(parents=True)
        (self.root / raw_path).write_bytes(raw)
        for method in ["pymupdf-page-text", "pymupdf-multi-pdf", "pymupdf-archive-page-text", "ocr-page-text"]:
            with self.subTest(method=method):
                old = self.existing(chars=72, pages=2, method=method, original_sha256=raw_hash, raw_path=raw_path)
                body = (self.root / old["path"]).read_bytes()
                self.assertGreater(remote.validate_remote_snapshot(value, root=self.root)["text_chars"], 72)
                result = remote.import_remote_snapshot(self.root, value)
                self.assertEqual(result[SID], old)
                self.assertEqual(self.read("manifest.json")[SID], old)
                self.assertEqual((self.root / raw_path).read_bytes(), raw)
                self.assertEqual((self.root / old["path"]).read_bytes(), body)
                event = json.loads((self.output / "attempts.jsonl").read_bytes().splitlines()[-1])
                self.assertEqual(event["preserved_source_ids"], [SID])
                self.assertEqual(event["updated_source_ids"], [])

    def test_raw_hash_does_not_protect_metadata_invalid_hash_or_stale_binding(self):
        for kind, raw_hash, stale in [("metadata", "a" * 64, False), ("extracted", "bad", False),
                                      ("extracted", "a" * 64, True)]:
            with self.subTest(kind=kind, raw_hash=raw_hash, stale=stale):
                self.existing(kind=kind, chars=1, original_sha256=raw_hash, method="pymupdf-page-text")
                if stale:
                    self.old[SID]["source_sha256"] = "f" * 64
                    self.save("manifest.json", self.old)
                self.assertEqual(remote.import_remote_snapshot(self.root, snapshot())[SID]["url"], URL)

    def test_disappearing_placeholders_are_not_an_improvement_even_with_more_text(self):
        for chars in [1, len("\n".join(BODY.values()))]:
            with self.subTest(chars=chars):
                old = self.existing(chars=chars, non_text_elements=2)
                self.assertEqual(remote.import_remote_snapshot(self.root, snapshot())[SID], old)

    def test_identity_requires_current_three_field_binding_and_verified_version_quote(self):
        bad = []
        for field in ["source_bindings", "version_evidence"]:
            value = snapshot()
            value["identity_evidence"].pop(field)
            bad.append(value)
        for field, expected in [("source_sha256", "f" * 64), ("document_code", "CCAR-21-R4"), ("publish_date", "2017-01-01")]:
            value = snapshot()
            value["identity_evidence"]["source_bindings"][SID][field] = expected
            bad.append(value)
        for quote in ["x", "CCAR-21-R4 2017-01-01"]:
            value = snapshot()
            value["identity_evidence"]["version_evidence"][0]["quote"] = quote
            bad.append(value)
        before = self.tree()
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.import_remote_snapshot(self.root, value)
            self.assertEqual(self.tree(), before)

    def test_stale_binding_or_corrupt_file_cannot_block_valid_replacement(self):
        for key, value in [("source_sha256", "0" * 64), ("landing_url", URL), ("sha256", "bad"),
                           ("path", "../outside.md")]:
            with self.subTest(key=key):
                self.existing(kind="fulltext")
                self.old[SID][key] = value
                self.save("manifest.json", self.old)
                result = remote.import_remote_snapshot(self.root, snapshot())[SID]
                self.assertEqual(result["source_sha256"], f"{1:064x}")
                self.assertEqual(result["url"], URL)

    def test_invalid_import_is_side_effect_free_including_later_unknown_source(self):
        bad = [snapshot(source_ids=[SID, "UNKNOWN"]), snapshot(responses=[response({1: "只有一行"})]),
               snapshot(identity_evidence=dict(urls=[URL], note="未关联CAAC落地页"))]
        for value in bad:
            before = self.tree()
            with self.subTest(value=value), self.assertRaises(ValueError):
                remote.import_remote_snapshot(self.root, value)
            self.assertEqual(self.tree(), before)

    def test_new_snapshot_paths_do_not_overwrite_previous_evidence_or_shared_body(self):
        first = remote.import_remote_snapshot(self.root, snapshot())[SID]
        cached = (self.root / first["snapshot_path"]).read_bytes()
        body = (self.root / first["path"]).read_bytes()
        second = remote.import_remote_snapshot(self.root, snapshot(source_ids=["CH01-S002"],
                  responses=[response({**BODY, 4: BODY[4] + "新的补充条款"})]))["CH01-S002"]
        self.assertNotEqual(first["path"], second["path"])
        self.assertNotEqual(first["snapshot_path"], second["snapshot_path"])
        self.assertEqual((self.root / first["path"]).read_bytes(), body)
        self.assertEqual((self.root / first["snapshot_path"]).read_bytes(), cached)

    def test_pdf_import_records_extracted_provenance(self):
        item = remote.import_remote_snapshot(self.root, pdf_snapshot())[SID]
        self.assertEqual(item["method"], "web-tool-pdf-text")
        self.assertEqual(item["page_count"], 2)
        self.assertEqual(item["original_sha256"], "")
        self.assertEqual(item["content_kind"], "extracted")
        self.assertIn("## 第 2 页\n", (self.root / item["path"]).read_text(encoding="utf-8"))

    def test_remote_pdf_page_continuation_verifies_clause_six_exact_quote(self):
        from airworthiness.locators import resolve_terms
        quote = "申请人应当向民航局申请型号合格证。"
        value = pdf_snapshot()
        value["responses"] = [response({"0@P0": "第六条 申请", "1@P0": "",
                                        "2@P1": quote, "3@P1": ""}, url=PDF, total=4, pages=2)]
        item = remote.import_remote_snapshot(self.root, value)[SID]
        body = (self.root / item["path"]).read_text(encoding="utf-8")
        term = dict(term="型号合格证", quote=quote, chapter_id="ch01", source_id=SID)
        result = resolve_terms([term], body, extracted=True)[0]
        self.assertEqual(result["locator_status"], "verified_clause")
        self.assertEqual(result["locator_anchor"], "clause-6")
        self.assertEqual(json.loads((self.root / item["snapshot_path"]).read_text(encoding="utf-8")), value)

    def test_image_omissions_are_counted_in_manifest_and_explained_in_markdown(self):
        value = snapshot(responses=[response({**BODY, 3: "公式：cite12†Image"})])
        item = remote.import_remote_snapshot(self.root, value)[SID]
        self.assertEqual(item["non_text_elements"], 1)
        self.assertEqual(item["content_kind"], "extracted")
        self.assertIn("图像/公式", item["note"])
        self.assertIn("1", item["note"])
        self.assertIn("[原文包含图像/公式，见官方原文]", (self.root / item["path"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

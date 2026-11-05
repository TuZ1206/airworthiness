"""The metadata overlay may explain differences, but must never approve law."""
import csv
import importlib
import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SID = "CH01-S001"
URL = "https://www.caac.gov.cn/XXGK/example.html"


class MetadataVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "data/verification/metadata-findings.json"
        self.path.parent.mkdir(parents=True)

    def apply(self, docs, issues, root=None):
        self.assertIsNotNone(importlib.util.find_spec("airworthiness.verification"),
                             "Evidence-only metadata overlay is not implemented")
        return importlib.import_module("airworthiness.verification").apply_metadata(
            docs, issues, root or self.root)

    def document(self, **updates):
        return dict(source_id=SID, title="原题名", document_code="原编号",
                    publish_date="2011-11-07", document_status="unknown",
                    review_status="pending", url=URL, body="原始正文不可改写。",
                    content_kind="excerpt", **updates)

    def finding(self, **updates):
        item = dict(finding_id="P01", source_ids=[SID], field="title",
                    old_values={SID: "原题名"}, verified_value="官方题名",
                    source_urls={SID: URL}, result="verified", resolution="corrected",
                    evidence_url=[URL], evidence={"type": "paraphrase", "text": "官方页载明该题名。"},
                    checked_at="2026-10-13T09:00:00Z")
        item.update(updates)
        return item

    def save(self, findings):
        self.path.write_text(json.dumps({"schema_version": "1.2", "findings": findings},
                                        ensure_ascii=False), encoding="utf-8")

    def issue(self, kind="title_variation", sid=SID):
        return dict(source_id=sid, kind=kind, message="原始提示")

    def test_corrects_in_place_preserves_original_and_returns_separate_issues(self):
        self.save([self.finding()])
        doc = self.document()
        docs, issues = [doc], [self.issue(), self.issue("stale_acquisition")]
        before = deepcopy(issues)
        resolved, unresolved = self.apply(docs, issues)
        self.assertIs(docs[0], doc)
        self.assertEqual(doc["title"], "官方题名")
        self.assertEqual(doc["original_metadata"]["title"], "原题名")
        self.assertEqual(doc["review_status"], "pending")
        self.assertEqual(doc["body"], "原始正文不可改写。")
        self.assertEqual(resolved[0]["resolution"], "corrected")
        self.assertEqual(resolved[0]["evidence"][0]["source_id"], SID)
        self.assertEqual(resolved[0]["finding_ids"], ["P01"])
        self.assertEqual(unresolved, [issues[1]])
        self.assertEqual(issues, before)
        self.assertTrue(doc["metadata_verification"][0]["applied"])

    def test_title_date_and_code_are_mapped_to_document_fields(self):
        for finding_field, target_field, value, kind in (
            ("title", "title", "官方题名", "title_variation"),
            ("date", "publish_date", "2016-03-17", "date_variation"),
            ("publish_date", "publish_date", "2016-03-17", "missing_date"),
            ("code", "document_code", "AC-21-48", "code_conflict"),
            ("document_code", "document_code", "AC-21-48", "code_conflict"),
        ):
            with self.subTest(field=finding_field):
                doc = self.document()
                self.save([self.finding(field=finding_field, old_values={SID: doc[target_field]},
                                        verified_value=value)])
                resolved, unresolved = self.apply([doc], [self.issue(kind)])
                self.assertEqual(doc[target_field], value)
                self.assertEqual((len(resolved), len(unresolved)), (1, 0))
                self.assertNotIn("date", doc)
                self.assertNotIn("code", doc)

    def test_explained_punctuation_or_scope_difference_does_not_unify(self):
        for result in ("equivalent_title", "scope_distinction"):
            self.save([self.finding(result=result, resolution="explained")])
            doc = self.document()
            resolved, unresolved = self.apply([doc], [self.issue()])
            self.assertEqual(doc["title"], "原题名")
            self.assertEqual(resolved[0]["resolution"], "explained")
            self.assertFalse(doc["metadata_verification"][0]["applied"])
            self.assertEqual(unresolved, [])

    def test_verified_alone_or_corrected_alone_cannot_change_or_resolve(self):
        for overrides in ({"resolution": None}, {"resolution": "recorded"},
                          {"result": "unresolved"}, {"result": "equivalent_title"}):
            with self.subTest(overrides=overrides):
                self.save([self.finding(**overrides)])
                doc, issue = self.document(), self.issue()
                self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
                self.assertEqual(doc["title"], "原题名")

    def test_source_id_and_issue_field_must_both_match(self):
        self.save([self.finding()])
        doc = self.document()
        issues = [self.issue("date_variation"), self.issue(sid="CH09-S999")]
        self.assertEqual(self.apply([doc], issues), ([], issues))

    def test_unverified_fields_review_status_body_status_and_urls_are_immutable(self):
        for field, value in (("review_status", "approved"), ("body", "伪正文"),
                             ("document_status", "effective"), ("url", URL + "new"),
                             ("metadata", {"title": "伪题名", "review_status": "approved"})):
            with self.subTest(field=field):
                doc = self.document()
                old = doc.get(field, {"title": "原题名"})
                self.save([self.finding(field=field, old_values={SID: old}, verified_value=value)])
                before = deepcopy(doc)
                resolved, _ = self.apply([doc], [self.issue("status_variation")])
                self.assertEqual({k: doc[k] for k in before}, before)
                self.assertEqual(resolved, [])

    def test_aliases_are_evidence_only_and_never_transfer_text(self):
        value = {"canonical_url": URL, "aliases": [URL + "?phone=1"]}
        self.save([self.finding(field="url_alias", old_values={SID: URL},
                                verified_value=value, result="equivalent_url", resolution="recorded",
                                byte_identity_verified=True)])
        doc, donor = self.document(), self.document()
        donor.update(source_id="CH01-S002", body="另一全文", content_kind="fulltext")
        self.apply([doc, donor], [])
        self.assertEqual(doc["url"], URL)
        self.assertEqual(doc["body"], "原始正文不可改写。")
        self.assertEqual(doc["content_kind"], "excerpt")
        self.assertEqual(doc["metadata_verification"][0]["verified_value"], value)
        self.assertEqual(donor["metadata_verification"], [])

    def test_stale_old_value_or_changed_source_url_blocks_correction_and_explanation(self):
        for result, resolution in (("verified", "corrected"), ("scope_distinction", "explained")):
            for updates in ({"title": "另一版本"}, {"url": URL + "?new=1"}):
                with self.subTest(result=result, updates=updates):
                    self.save([self.finding(result=result, resolution=resolution)])
                    doc = self.document()
                    doc.update(updates)
                    before = deepcopy(doc)
                    issue = self.issue()
                    self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
                    self.assertEqual({k: doc[k] for k in before}, before)
                    self.assertEqual(doc["metadata_verification"][0]["application"], "blocked")

    def test_missing_evidence_or_bindings_and_invalid_values_fail_closed(self):
        for updates in (
            {"evidence_url": []}, {"evidence_url": ["https://gov.cn.evil.test/a"]},
            {"evidence_url": ["https://user@www.caac.gov.cn/a"]},
            {"evidence_url": ["http://[invalid"]}, {"evidence": {}},
            {"evidence": {"type": "quote", "text": "文" * 26}}, {"checked_at": "not-a-date"},
            {"source_urls": {}}, {"old_values": {}}, {"verified_value": None},
            {"verified_value": {"title": "不可递归写入"}},
            {"field": "date", "old_values": {SID: "2011-11-07"}, "verified_value": "2026-02-30"},
        ):
            with self.subTest(updates=updates):
                self.save([self.finding(**updates)])
                doc, issue = self.document(), self.issue()
                self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
                self.assertEqual(doc["title"], "原题名")
                self.assertEqual(doc["publish_date"], "2011-11-07")

    def assert_rejected_proof_url(self, url):
        # A valid URL alongside a forged one must not make the evidence valid.
        self.save([self.finding(evidence_url=[URL, url])])
        doc, issue = self.document(), self.issue()
        before = deepcopy(doc)
        resolved, unresolved = self.apply([doc], [issue])
        self.assertEqual((resolved, unresolved), ([], [issue]), repr(url))
        self.assertEqual({key: doc[key] for key in before}, before)
        self.assertEqual(doc["original_metadata"]["title"], "原题名")
        evidence = doc["metadata_verification"][0]
        self.assertFalse(evidence["applied"])
        self.assertEqual(evidence["application"], "blocked")
        self.assertEqual(evidence["block_reason"], "insufficient_evidence")

    def test_backslash_host_confusion_cannot_authorize_metadata(self):
        for url in (r"https://evil.example\www.caac.gov.cn/forged-proof",
                    r"https://evil.example\@www.caac.gov.cn/forged-proof",
                    r"https://www.caac.gov.cn/path\proof"):
            self.assert_rejected_proof_url(url)

    def test_raw_control_characters_are_rejected_before_url_parsing(self):
        # urlsplit silently removes CR/LF/TAB and leading C0 characters.
        controls = "\r\n\t" + "".join(chr(n) for n in (*range(32), *range(127, 160)))
        for control in controls:
            for url in (control + URL, URL + control, "https://www.caac" + control + ".gov.cn/proof"):
                self.assert_rejected_proof_url(url)

    def test_proof_urls_use_strict_official_authority_and_port_validation(self):
        for url in ("https://www.caac.gov.cn:444/proof", "https://www.caac.gov.cn:bad/proof",
                    "https://www.caac.gov.cn:65536/proof", "https://@www.caac.gov.cn/proof",
                    "https://bad%2fwww.caac.gov.cn/proof", "https://bad_.caac.gov.cn/proof",
                    " https://www.caac.gov.cn/proof", "https://www.caac.gov.cn/proof "):
            self.assert_rejected_proof_url(url)

    def test_strict_validation_preserves_valid_original_evidence_urls(self):
        for url in (URL, "https://www.caac.gov.cn:443/proof?x=1#cover",
                    "http://www.gov.cn:80/proof", "HTTPS://WWW.CAAC.GOV.CN./proof?x=1%202"):
            self.save([self.finding(evidence_url=[url])])
            doc = self.document()
            resolved, unresolved = self.apply([doc], [self.issue()])
            self.assertEqual((len(resolved), unresolved), (1, []))
            self.assertEqual(doc["title"], "官方题名")
            self.assertEqual(doc["metadata_verification"][0]["evidence_url"], [url])

    def test_conflicting_evidence_never_uses_file_order_as_authority(self):
        a, b = self.finding(), self.finding(finding_id="P02", verified_value="另一官方题名")
        for findings in ([a, b], [b, a]):
            self.save(findings)
            doc, issue = self.document(), self.issue()
            self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
            self.assertEqual(doc["title"], "原题名")
            self.assertTrue(all(x["block_reason"] == "conflicting_findings" for x in doc["metadata_verification"]))

    def test_idempotent_and_existing_correct_value_is_not_a_new_change(self):
        self.save([self.finding()])
        doc, issue = self.document(), self.issue()
        first = self.apply([doc], [issue])
        before = deepcopy(doc)
        self.assertEqual(self.apply([doc], [issue]), first)
        self.assertEqual(doc, before)
        other = self.document()
        other["title"] = "官方题名"
        self.apply([other], [issue])
        self.assertFalse(other["metadata_verification"][0]["applied"])
        self.assertEqual(other["original_metadata"]["title"], "官方题名")

    def test_missing_file_is_optional_but_corrupt_or_unknown_schema_warns(self):
        doc, issue = self.document(), self.issue()
        self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
        self.assertEqual(doc["metadata_verification"], [])
        for content in ("{broken", '{"schema_version":"999", "findings":[]}', '[]'):
            self.path.write_text(content, encoding="utf-8")
            with self.assertWarns(RuntimeWarning):
                self.assertEqual(self.apply([self.document()], [issue]), ([], [issue]))

    def test_malformed_entries_do_not_hide_valid_evidence(self):
        self.save([None, "bad", {}, self.finding(finding_id="bad", source_ids=None), self.finding()])
        doc = self.document()
        self.assertEqual(len(self.apply([doc], [self.issue()])[0]), 1)
        self.assertEqual(doc["title"], "官方题名")

    def test_malformed_decision_types_fail_closed_without_crashing(self):
        for updates in ({"field": []}, {"result": {}}, {"resolution": []},
                        {"evidence": {"type": [], "text": "不可用"}}):
            with self.subTest(updates=updates):
                self.save([self.finding(**updates)])
                doc, issue = self.document(), self.issue()
                self.assertEqual(self.apply([doc], [issue]), ([], [issue]))
                self.assertEqual(doc["title"], "原题名")

    def test_unresolved_identity_blocks_all_metadata_decisions_for_that_source(self):
        self.save([self.finding(), self.finding(finding_id="I01", field="source_identity",
                  verified_value=None, result="unresolved_source_identity", resolution="unresolved")])
        doc = self.document()
        issues = [self.issue(), self.issue("unresolved_source_identity")]
        self.assertEqual(self.apply([doc], issues), ([], issues))
        self.assertEqual(doc["title"], "原题名")
        self.assertEqual(doc["metadata_verification"][0]["block_reason"], "unresolved_source_identity")

    def test_real_findings_resolve_25_of_26_and_only_change_eight_fields(self):
        docs = []
        for path in sorted((ROOT / "data/chapters").glob("ch*/sources.csv")):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                docs.extend(csv.DictReader(handle))
        before = deepcopy(docs)
        data = json.loads((ROOT / "data/verification/metadata-findings.json").read_text(encoding="utf-8"))
        priority = [f for f in data["findings"] if f["scope"] == "priority"]
        kinds = {"title": "title_variation", "publish_date": "date_variation", "document_code": "code_conflict"}
        issues = [self.issue("missing_date" if f["finding_id"] == "P01" else kinds[f["field"]], sid)
                  for f in priority for sid in f["source_ids"]]
        self.assertEqual(len(issues), 26)
        resolved, unresolved = self.apply(docs, issues, ROOT)
        self.assertEqual((len(resolved), len(unresolved)), (25, 1))
        self.assertEqual(unresolved[0]["source_id"], "CH04-S010")
        changes = [(d["source_id"], k) for d, old in zip(docs, before) for k in old if d[k] != old[k]]
        self.assertEqual(set(changes), {
            ("CH06-S016", "document_code"), ("CH02-S037", "document_code"),
            ("CH03-S001", "publish_date"), ("CH08-S001", "publish_date"),
            ("CH09-S001", "publish_date"), ("CH08-S008", "title"), ("CH03-S007", "title"),
            ("CH08-S007", "title"),
        })
        self.assertTrue(all(d["review_status"] == old["review_status"] for d, old in zip(docs, before)))


if __name__ == "__main__":
    unittest.main()

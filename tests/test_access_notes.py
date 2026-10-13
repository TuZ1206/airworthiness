import json
import tempfile
import unittest
from pathlib import Path
from importlib.util import find_spec
from unittest.mock import patch


class AccessNotesTests(unittest.TestCase):
    def test_report_keeps_resolved_issue_and_evidence(self):
        from airworthiness.cli import markdown_report
        report = dict(totals=dict(sources=1, chapters=1), generated_at='2026-10-13',
                      chapters=[], gaps=[], issues=[], resolved_issues=[dict(
                          source_id='CH03-S001', message='原日期不一致',
                          resolution='corrected', evidence=[dict(evidence_url=['https://www.caac.gov.cn/proof'])])])
        output = markdown_report(report)
        self.assertIn('已处理提示（保留原记录）', output)
        self.assertIn('原日期不一致', output)
        self.assertIn('字段已纠正', output)
        self.assertIn('https://www.caac.gov.cn/proof', output)

    def test_only_current_matching_source_gets_specific_access_reason(self):
        self.assertIsNotNone(find_spec('airworthiness.access_notes'))
        from airworthiness.access_notes import enrich_access_notes
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root/'data/verification/standards-access.json'
            file.parent.mkdir(parents=True)
            file.write_text(json.dumps(dict(standards=[dict(checked_at='2026-10-13',
                not_retrieved_reason='官方平台明确因采标版权不提供文本阅读。',
                input_sources=[dict(source_id='CH09-S008',url_as_recorded='https://std.samr.gov.cn/a')])])),encoding='utf-8')
            records = [dict(source_id='CH09-S008',url='https://std.samr.gov.cn/a',reason='旧网络失败'),
                       dict(source_id='CH09-S008',url='https://std.samr.gov.cn/new',reason='保留')]
            enrich_access_notes(root, records)
            self.assertIn('版权',records[0]['reason'])
            self.assertEqual(records[0]['previous_reason'],'旧网络失败')
            self.assertEqual(records[1]['reason'],'保留')
            from airworthiness.app import create_app
            fresh = dict(gaps=[dict(source_id='CH09-S008',url='https://std.samr.gov.cn/a',reason='旧网络失败')])
            with patch('airworthiness.app.catalog.ensure_catalog'), patch('airworthiness.app.catalog.quality', return_value=fresh):
                client = create_app(dict(TESTING=True, DATA_ROOT=root)).test_client()
                self.assertIn('版权', client.get('/api/quality').get_json()['gaps'][0]['reason'])

    def test_missing_report_leaves_records_unchanged(self):
        self.assertIsNotNone(find_spec('airworthiness.access_notes'))
        from airworthiness.access_notes import enrich_access_notes
        with tempfile.TemporaryDirectory() as temp:
            records=[dict(source_id='CH01-S001',reason='未取得')]
            enrich_access_notes(Path(temp),records)
            self.assertEqual(records,[dict(source_id='CH01-S001',reason='未取得')])

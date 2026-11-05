"""Regression tests from real official-site collection failures."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from airworthiness.acquire import extract_html, import_web_snapshots, main


class AcquisitionResilienceTests(unittest.TestCase):
    def test_caac_content_role_contains_article_not_outer_chrome(self):
        html = '<html><meta charset="utf-8"><title>法规</title><aside>站点导航</aside><div data-role="n_content"><p>第一条 安全要求。</p><p>第二条 ' + '须保存审定记录。' * 70 + '</p></div></html>'
        result = extract_html(html.encode(), 'https://www.caac.gov.cn/test.html')
        self.assertEqual(result.content_kind, 'fulltext')
        self.assertIn('第一条', result.markdown)
        self.assertNotIn('站点导航', result.markdown)

    def test_amendment_decision_is_saved_as_extracted_not_consolidated_law(self):
        html = '<html><meta charset="utf-8"><title>交通运输部关于修改《规定》的决定</title><div data-role="n_content"><p>一、将第六条修改为：' + '依法登记。' * 45 + '</p><p>二、将第二十一条修改为：' + '登记标志。' * 45 + '</p><p>本决定自2022年9月1日起施行。</p></div></html>'
        result = extract_html(html.encode(), 'https://www.caac.gov.cn/test.html')
        self.assertEqual(result.content_kind, 'extracted')
        self.assertIn('修改决定', result.note)

    def test_formula_images_are_explicitly_marked_and_never_claimed_complete(self):
        html = '<html><meta charset="utf-8"><title>规定</title><div class="TRS_Editor"><p>第一条 计算要求。</p><img src="formula.png"><p>第二条 ' + '按公式计算。' * 80 + '</p></div></html>'
        result = extract_html(html.encode(), 'https://www.gov.cn/test.html')
        self.assertEqual(result.content_kind, 'extracted')
        self.assertIn('[原文包含图像/公式，见官方原文]', result.markdown)
        self.assertEqual(result.non_text_elements, 1)

    def test_nested_hidden_elements_do_not_abort_other_article_content(self):
        html = '<html><title>条例</title><div hidden><span style="display:none">隐藏导航</span></div><div class="TRS_Editor"><p>第一条 适用范围。</p><p>第二条 ' + '真实公开正文。' * 80 + '</p></div></html>'
        result = extract_html(html.encode(), 'https://www.caac.gov.cn/test.html')
        self.assertEqual(result.content_kind, 'fulltext')
        self.assertIn('第一条', result.markdown)
        self.assertNotIn('隐藏导航', result.markdown)


class LegacySnapshotBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.url = 'https://www.caac.gov.cn/legacy.html'
        sources = self.root / 'data/chapters/ch01/sources.csv'
        sources.parent.mkdir(parents=True)
        sources.write_text(f'source_id,url,sha256\nCH01-S001,{self.url},source-hash\n', encoding='utf-8')

    def snapshot(self, body, end=2):
        raw = f'Official law ({self.url})\nContent type: text/html; Total lines: 4\n' + body
        return dict(url=self.url, responses=[raw], line_start=1, line_end=end,
                    captured_at='2026-10-13T01:00:00+00:00')

    def test_embedded_labels_remain_literal_even_with_a_real_matching_label(self):
        body = 'L1: 第一条 正文中的 L2: 只是原文字样，L20: 也不分行。\nL2: 第二条 真实下一行。'
        try:
            item = import_web_snapshots(self.root, [self.snapshot(body)])['CH01-S001']
        except ValueError as exc:
            self.fail(f'Embedded label was incorrectly parsed as a conflicting line: {exc}')
        saved = (self.root / item['path']).read_text(encoding='utf-8')
        self.assertIn('第一条 正文中的 L2: 只是原文字样，L20: 也不分行。\n第二条 真实下一行。', saved)
        self.assertEqual(item['landing_url'], self.url)
        self.assertEqual(item['original_sha256'], '')
        self.assertEqual(item['review_status'], 'pending')

    def test_embedded_or_indented_labels_cannot_fill_missing_line_coverage(self):
        for separator in (' ', '\t', '\n ', '\r'):
            with self.subTest(separator=repr(separator)), self.assertRaisesRegex(ValueError, 'missing lines'):
                body = 'L1: 第一条 正文' + separator + 'L2: 不是物理行首标签\nL3: 第三行。'
                import_web_snapshots(self.root, [self.snapshot(body, end=3)])
        self.assertFalse((self.root / 'data/acquired/manifest.json').exists())

    def test_physical_crlf_boundaries_keep_legacy_empty_line_behavior(self):
        body = 'L1: 第一条 原文。\r\nL2: \r\nL3: 第二条 原文。'
        item = import_web_snapshots(self.root, [self.snapshot(body, end=3)])['CH01-S001']
        saved = (self.root / item['path']).read_text(encoding='utf-8')
        self.assertIn('第一条 原文。\n\n第二条 原文。', saved)

    def strict_snapshot(self):
        from tests.test_remote_import import snapshot, LANDING, CODE, DATE
        sources = self.root / 'data/chapters/ch01/sources.csv'
        sources.write_text('source_id,url,sha256,document_code,publish_date\n'
                           f'CH01-S001,{LANDING},{1:064x},{CODE},{DATE}\n', encoding='utf-8')
        return snapshot()

    def test_cli_rejects_legacy_schema_without_writing_or_auto_identity(self):
        snapshot = self.snapshot('L1: 第一条 原文。\nL2: 第二条 原文。')
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('sys.stdin', io.StringIO(json.dumps([snapshot]))), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(['--root', str(self.root), '--import-web-json'])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_cli_preflights_the_whole_explicit_array_before_any_writes(self):
        valid = self.strict_snapshot()
        old = self.snapshot('L1: 原文。\nL2: 原文。')
        for payload in (valid, [], [valid, old]):
            with self.subTest(payload_type=type(payload).__name__):
                with patch('sys.stdin', io.StringIO(json.dumps(payload))), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main(['--root', str(self.root), '--import-web-json'])
                self.assertEqual(error.exception.code, 2)
                self.assertFalse((self.root / 'data/acquired').exists())
                self.assertFalse((self.root / '.cache').exists())

    def test_cli_imports_explicit_bound_snapshot_through_strict_importer(self):
        snapshot = self.strict_snapshot()
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps([snapshot]))), redirect_stdout(output):
            self.assertEqual(main(['--root', str(self.root), '--import-web-json']), 0)
        manifest = json.loads((self.root / 'data/acquired/manifest.json').read_text(encoding='utf-8'))
        entry = manifest['CH01-S001']
        self.assertEqual(entry['identity_evidence'], snapshot['identity_evidence'])
        self.assertTrue(entry['snapshot_path'].startswith('.cache/acquisition/remote/'))
        self.assertEqual(entry['review_status'], 'pending')
        self.assertEqual(json.loads(output.getvalue()), {'extracted': 1})

    def test_direct_script_empty_array_exits_two_without_import_error_or_writes(self):
        script = Path(__file__).resolve().parents[1] / 'src/airworthiness/acquire.py'
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), '--import-web-json'],
                                input='[]', text=True, encoding='utf-8', capture_output=True,
                                cwd=self.root, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('ImportError', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('nonempty explicit snapshot array', result.stderr)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()

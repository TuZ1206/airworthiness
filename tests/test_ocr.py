"""Local OCR contract: raw text, bounded rendering, honest errors and resume."""
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import pymupdf


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('airworthiness.ocr'),
                             'The independent local OCR API must exist')
        self.ocr = importlib.import_module('airworthiness.ocr')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'ocr'
        self.models = self.root / 'tessdata'
        self.models.mkdir()
        for lang in ('chi_sim', 'eng'):
            (self.models / (lang + '.traineddata')).write_bytes(lang.encode())
        self.pdf = self.root / 'scan.bin'
        with pymupdf.open() as doc:
            for number in range(1, 8):
                page = doc.new_page(width=200, height=200)
                page.insert_text((20, 50), 'PAGE %d' % number)
            doc.save(self.pdf)
        self.calls = []
        self.version = b'tesseract 5.5.2\n leptonica test\n'

    def run_engine(self, command, **kwargs):
        if '--version' in command:
            return subprocess.CompletedProcess(command, 0, self.version, b'')
        number = int(Path(command[1]).stem)
        self.calls.append(number)
        return subprocess.CompletedProcess(command, 0,
            ('  原样 OCR %d\n\n' % number).encode(), b'')

    def extract(self, **kwargs):
        return self.ocr.ocr_pdf(self.pdf, self.cache, self.models, **kwargs)

    def test_raw_page_text_order_and_provenance(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            result = self.extract()
        self.assertEqual(result['page_count'], 7)
        self.assertEqual(result['original_sha256'], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual([p['number'] for p in result['pages']], list(range(1, 8)))
        self.assertEqual(result['pages'][0]['text'], '  原样 OCR 1\n\n')
        self.assertTrue(all(p['error'] is None and p['empty'] is False for p in result['pages']))
        self.assertEqual(result['method'], 'local_ocr_tesseract')
        self.assertIn('未经人工校核', result['note'])
        self.assertNotIn(result.get('content_kind'), ('fulltext', 'approved'))
        self.assertNotIn(result.get('status'), ('fulltext', 'approved'))
        self.assertEqual(result['provenance']['dpi'], 180)
        self.assertEqual(result['provenance']['models']['eng'], hashlib.sha256(b'eng').hexdigest())

    def test_replaced_path_cannot_mix_original_hash_with_replacement_pages(self):
        original_bytes = self.pdf.read_bytes()
        with pymupdf.open() as replacement:
            replacement.new_page(width=100, height=100)
            replacement_bytes = replacement.tobytes()
        def engine(command, **kwargs):
            if '--version' in command:
                # Deterministically replace the source after identity is computed.
                self.pdf.write_bytes(replacement_bytes)
            return self.run_engine(command, **kwargs)
        with patch.object(self.ocr.subprocess, 'run', side_effect=engine), \
                patch.object(self.ocr.pymupdf, 'open', wraps=pymupdf.open) as open_pdf:
            result = self.extract()
        self.assertEqual(result['page_count'], 7)
        self.assertEqual(result['original_sha256'], hashlib.sha256(original_bytes).hexdigest())
        self.assertEqual(result['provenance']['original_sha256'], result['original_sha256'])
        open_pdf.assert_called_once_with(stream=original_bytes, filetype='pdf')
        self.assertEqual(self.pdf.read_bytes(), replacement_bytes)

    def test_page_timeout_above_45_seconds_fails_before_setup(self):
        for timeout in (45.000001, 46, 3600):
            with self.subTest(timeout=timeout), \
                    patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine) as engine, \
                    self.assertRaisesRegex(ValueError, '45'):
                self.extract(timeout=timeout)
            self.assertEqual(engine.call_count, 0)
        self.assertFalse(self.cache.exists())

    def test_source_snapshot_is_size_bounded_and_read_once(self):
        original_open = Path.open
        reads = []
        def tracked_open(path, *args, **kwargs):
            handle = original_open(path, *args, **kwargs)
            if path == self.pdf.resolve() and args == ('rb',):
                from unittest.mock import MagicMock
                wrapper = MagicMock(wraps=handle)
                wrapper.__enter__.return_value = wrapper
                wrapper.__exit__.side_effect = lambda *exc: handle.close()
                reads.append(wrapper)
                return wrapper
            return handle
        with patch.object(self.ocr, 'MAX_PDF_BYTES', 32, create=True), \
                patch.object(Path, 'open', tracked_open), \
                patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine) as engine, \
                patch.object(self.ocr.pymupdf, 'open', wraps=pymupdf.open) as open_pdf:
            with self.assertRaisesRegex(ValueError, 'PDF.*limit'):
                self.extract()
        self.assertEqual(len(reads), 1)
        reads[0].read.assert_called_once_with(33)
        engine.assert_not_called()
        open_pdf.assert_not_called()
        self.assertFalse(self.cache.exists())

    def test_render_on_caller_thread_and_at_most_three_images_or_processes(self):
        owner = threading.get_ident()
        original = pymupdf.Page.get_pixmap
        lock = threading.Lock()
        active = 0
        peak = 0
        def render(page, *args, **kwargs):
            self.assertEqual(threading.get_ident(), owner)
            return original(page, *args, **kwargs)
        def engine(command, **kwargs):
            nonlocal active, peak
            if '--version' in command:
                return self.run_engine(command, **kwargs)
            self.assertNotEqual(threading.get_ident(), owner)
            self.assertEqual(kwargs['env']['OMP_THREAD_LIMIT'], '1')
            self.assertEqual(kwargs['timeout'], 45)
            self.assertIn(str(self.models.resolve()), command)
            self.assertEqual(command[command.index('-l') + 1], 'chi_sim+eng')
            self.assertLessEqual(len(list(self.cache.rglob('*.png'))), 3)
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.04 if Path(command[1]).stem == '000001' else 0.02)
            result = self.run_engine(command, **kwargs)
            with lock:
                active -= 1
            return result
        before = dict(os.environ)
        with patch.object(pymupdf.Page, 'get_pixmap', render), patch.object(self.ocr.subprocess, 'run', side_effect=engine):
            result = self.extract(workers=3)
        self.assertEqual(peak, 3)
        self.assertEqual([p['number'] for p in result['pages']], list(range(1, 8)))
        self.assertFalse(list(self.cache.rglob('*.png')))
        self.assertEqual(dict(os.environ), before)

    def test_timeout_failure_and_empty_are_explicit_and_retried(self):
        def engine(command, **kwargs):
            if '--version' in command:
                return self.run_engine(command, **kwargs)
            number = int(Path(command[1]).stem)
            if number == 2:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=b'partial', stderr=b'slow')
            if number == 3:
                return subprocess.CompletedProcess(command, 1, b'untrusted partial', b'broken model')
            if number == 4:
                return subprocess.CompletedProcess(command, 0, b' \n\x0c', b'blank')
            return self.run_engine(command, **kwargs)
        with patch.object(self.ocr.subprocess, 'run', side_effect=engine):
            result = self.extract(timeout=0.1)
        self.assertEqual(result['error_count'], 3)
        self.assertFalse(result['ocr_complete'])
        self.assertIn('timeout', result['pages'][1]['error'])
        self.assertEqual(result['pages'][1]['text'], 'partial')
        self.assertEqual(result['pages'][1]['stderr'], 'slow')
        self.assertIn('broken model', result['pages'][2]['error'])
        self.assertTrue(result['pages'][3]['empty'])
        self.assertIn('empty', result['pages'][3]['error'])
        self.calls.clear()
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            resumed = self.extract()
        self.assertEqual(sorted(self.calls), [2, 3, 4])
        self.assertTrue(resumed['ocr_complete'])

    def test_successful_cache_resume_and_corrupt_page_recovery(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            first = self.extract()
            self.calls.clear()
            self.assertEqual(self.extract(), first)
            self.assertEqual(self.calls, [])
            pages_dir = self.cache / first['cache_key'] / 'pages'
            (pages_dir / '000002.json').write_text('{truncated', encoding='utf-8')
            cached = json.loads((pages_dir / '000003.json').read_text(encoding='utf-8'))
            cached['page']['text'] = 'tampered'
            (pages_dir / '000003.json').write_text(json.dumps(cached), encoding='utf-8')
            (pages_dir / '000004.json').unlink()
            resumed = self.extract()
        self.assertEqual(sorted(self.calls), [2, 3, 4])
        self.assertEqual(resumed, first)

    def test_pipeline_v2_isolates_v1_cache_without_modifying_legacy_result(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            with patch.object(self.ocr, 'PIPELINE_VERSION', 1):
                legacy = self.extract()
            legacy_path = self.cache / legacy['cache_key'] / 'result.json'
            legacy_bytes = legacy_path.read_bytes()
            self.calls.clear()
            current = self.extract()
            self.assertEqual(current['provenance']['pipeline_version'], 2)
            self.assertNotEqual(current['cache_key'], legacy['cache_key'])
            self.assertEqual(sorted(self.calls), list(range(1, 8)))
            self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
            self.calls.clear()
            self.assertEqual(self.extract(), current)
            self.assertEqual(self.calls, [])

    def test_cache_identity_includes_models_pdf_dpi_engine_and_renderer(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            results = [self.extract()]
            results.append(self.extract(dpi=160))
            (self.models / 'eng.traineddata').write_bytes(b'new model')
            results.append(self.extract())
            self.version = b'tesseract 5.6.0\n'
            results.append(self.extract())
            with patch.object(pymupdf, 'VersionBind', 'new-renderer'):
                results.append(self.extract())
            self.pdf.write_bytes(self.pdf.read_bytes() + b'\n%new original\n')
            results.append(self.extract())
        self.assertEqual(len(set(r['cache_key'] for r in results)), len(results))
        self.assertEqual(len(self.calls), 7 * len(results))

    def test_render_failure_is_local_to_one_page(self):
        original = pymupdf.Page.get_pixmap
        def render(page, *args, **kwargs):
            if page.number == 2:
                raise RuntimeError('cannot decode image')
            return original(page, *args, **kwargs)
        with patch.object(pymupdf.Page, 'get_pixmap', render), patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            result = self.extract()
        self.assertEqual(result['page_count'], 7)
        self.assertEqual(result['error_count'], 1)
        self.assertIn('cannot decode image', result['pages'][2]['error'])
        self.assertEqual(sorted(self.calls), [1, 2, 4, 5, 6, 7])

    def test_missing_models_engine_and_invalid_pdf_report_failure(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=FileNotFoundError('engine missing')):
            with self.assertRaisesRegex(RuntimeError, 'engine missing'):
                self.extract()
        (self.models / 'eng.traineddata').unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'eng.traineddata'):
            self.extract()
        (self.models / 'eng.traineddata').write_bytes(b'eng')
        self.pdf.write_bytes(b'<html>not a pdf</html>')
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            with self.assertRaises((ValueError, pymupdf.FileDataError)):
                self.extract()

    def test_invalid_limits_fail_before_rendering(self):
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            for arguments in ({'workers': 0}, {'workers': -1}, {'workers': True},
                              {'dpi': 0}, {'dpi': 180.5}, {'timeout': 0},
                              {'timeout': float('nan')}, {'timeout': float('inf')}):
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    self.extract(**arguments)
        self.assertFalse(self.calls)

    def test_api_rejects_background_thread_before_opening_pdf(self):
        errors = []
        def background():
            try:
                self.extract()
            except Exception as exc:
                errors.append(exc)
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            thread = threading.Thread(target=background)
            thread.start()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertIn('main thread', str(errors[0]))
        self.assertFalse(self.calls)

    def test_oversized_page_is_rejected_without_allocating_pixmap(self):
        with pymupdf.open() as doc:
            doc.new_page(width=20_000, height=20_000)
            doc.save(self.pdf)
        with patch.object(pymupdf.Page, 'get_pixmap') as render, patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            result = self.extract()
        render.assert_not_called()
        self.assertEqual(result['error_count'], 1)
        self.assertIn('render limit', result['pages'][0]['error'])

    def test_failed_cache_write_preserves_already_finished_pages_for_resume(self):
        original = self.ocr._atomic_json
        def save(path, value):
            if path.name == '000003.json':
                raise OSError('disk full')
            return original(path, value)
        with patch.object(self.ocr.subprocess, 'run', side_effect=self.run_engine):
            with patch.object(self.ocr, '_atomic_json', side_effect=save):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    self.extract(workers=1)
            self.calls.clear()
            result = self.extract(workers=1)
        self.assertEqual(self.calls, [3, 4, 5, 6, 7])
        self.assertTrue(result['ocr_complete'])
        self.assertFalse(list(self.cache.rglob('*.png')))

    def test_process_launch_failure_is_a_page_error(self):
        def engine(command, **kwargs):
            if '--version' in command:
                return self.run_engine(command, **kwargs)
            raise OSError('process creation failed')
        with patch.object(self.ocr.subprocess, 'run', side_effect=engine):
            result = self.extract()
        self.assertEqual(result['error_count'], 7)
        self.assertTrue(all('process creation failed' in p['error'] for p in result['pages']))
        self.assertFalse(list(self.cache.rglob('*.png')))


if __name__ == '__main__':
    unittest.main()

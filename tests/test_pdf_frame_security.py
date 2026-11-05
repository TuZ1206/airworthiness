"""Only successful, verified original PDFs may be framed by this origin."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from airworthiness.app import create_app
from tests.test_locator_integration import make_inputs


class PdfFrameSecurityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        make_inputs(self.root)
        url = 'https://www.caac.gov.cn/frame-test.pdf'
        self.raw = b'%PDF-1.7\nverified official bytes for frame fixture'
        sha = hashlib.sha256(self.raw).hexdigest()
        key = hashlib.sha256(url.encode()).hexdigest()
        cache = self.root / '.cache/acquisition'
        cache.mkdir(parents=True)
        self.path = cache / (key + '.bin')
        self.path.write_bytes(self.raw)
        (cache / (key + '.json')).write_text(json.dumps(dict(
            request_url=url, url=url, original_sha256=sha, size=len(self.raw),
            redirects=[], content_type='application/pdf')), encoding='utf-8')
        manifest_path = self.root / 'data/acquired/manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['CH01-S001'].update(url=url, original_sha256=sha)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        self.app = create_app(dict(TESTING=True, DATA_ROOT=self.root,
                                   DATABASE=self.root / 'test.sqlite3'))
        self.client = self.app.test_client()
        self.original_url = '/api/documents/CH01-S001/original'

    def assert_policy(self, response, ancestors):
        self.assertEqual(response.headers.getlist('Content-Security-Policy'), [
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; "
            f"frame-ancestors {ancestors}; base-uri 'none'; object-src 'none'"
        ])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_verified_pdf_allows_only_same_origin_ancestors(self):
        for method in ('GET', 'HEAD'):
            with self.subTest(method=method):
                with self.client.open(self.original_url, method=method) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'application/pdf')
                    self.assertEqual(response.data, self.raw if method == 'GET' else b'')
                    self.assertIn('inline', response.headers['Content-Disposition'])
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assert_policy(response, "'self'")

    def test_verified_partial_pdf_allows_only_same_origin_ancestors(self):
        with self.client.get(self.original_url, headers={'Range': 'bytes=0-7'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.mimetype, 'application/pdf')
            self.assertEqual(response.data, self.raw[:8])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assert_policy(response, "'self'")

    def test_normal_html_and_api_responses_remain_unframeable(self):
        for url in ('/', '/quality', '/chapters/ch01', '/api/overview',
                    '/api/resources', '/api/chapters/ch01', '/api/documents/CH01-S001',
                    '/api/quality', '/api/health'):
            with self.subTest(url=url):
                with self.client.get(url) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assert_policy(response, "'none'")

    def test_original_request_errors_remain_unframeable(self):
        for url, headers, status in (
            ('/api/documents/missing/original', {}, 404),
            (self.original_url + '?index=1', {}, 404),
            (self.original_url + '?index=-1', {}, 404),
            (self.original_url + '?index=bad', {}, 400),
            (self.original_url, {'Range': 'bytes=99999-'}, 416),
        ):
            with self.subTest(url=url, headers=headers):
                with self.client.get(url, headers=headers) as response:
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.mimetype, 'application/json')
                    self.assert_policy(response, "'none'")

    def test_missing_original_cache_returns_unframeable_404(self):
        self.path.unlink()
        with self.client.get(self.original_url) as response:
            self.assertEqual(response.status_code, 404)
            self.assert_policy(response, "'none'")

    def test_tampered_original_returns_unframeable_404(self):
        self.path.write_bytes(self.raw.replace(b'verified', b'tampered'))
        self.assertEqual(self.path.stat().st_size, len(self.raw))
        with self.client.get(self.original_url) as response:
            self.assertEqual(response.status_code, 404)
            self.assert_policy(response, "'none'")

    def test_pdf_outside_original_endpoint_remains_unframeable(self):
        self.app.add_url_rule('/other.pdf', 'other_pdf', lambda: self.app.response_class(
            self.raw, mimetype='application/pdf'))
        with self.client.get('/other.pdf') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'application/pdf')
            self.assert_policy(response, "'none'")

    def test_original_non_pdf_or_unsuccessful_responses_remain_unframeable(self):
        # Exercise the header hook's MIME/status guards even if route behavior changes.
        with self.app.test_request_context(self.original_url):
            for status, mimetype in ((200, 'text/html'), (200, 'application/json'),
                                     (302, 'application/pdf'), (304, 'application/pdf'),
                                     (404, 'application/pdf'), (500, 'application/pdf')):
                with self.subTest(status=status, mimetype=mimetype):
                    with self.app.response_class(status=status, mimetype=mimetype) as response:
                        self.assert_policy(self.app.process_response(response), "'none'")


if __name__ == '__main__':
    unittest.main()

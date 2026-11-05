"""Large read-only document JSON can cross a slow preview tunnel efficiently."""
import gzip
import unittest
from unittest.mock import patch

from airworthiness.app import create_app


class ResponseCompressionTests(unittest.TestCase):
    def setUp(self):
        with patch('airworthiness.app.catalog.ensure_catalog'):
            self.app = create_app({'TESTING': True})
        self.payload = '法规原文与目录。' * 600
        self.app.add_url_rule('/api/large-fixture', 'large_fixture',
                             lambda: self.app.json.response(body=self.payload))
        self.app.add_url_rule('/small-fixture', 'small_fixture', lambda: 'ok')
        self.app.add_url_rule('/pdf-fixture', 'pdf_fixture',
                             lambda: self.app.response_class(b'%PDF-' + b'x' * 9000,
                                                             mimetype='application/pdf'))
        self.client = self.app.test_client()

    def test_large_json_is_gzip_when_accepted_and_decodes_exactly(self):
        plain = self.client.get('/api/large-fixture')
        zipped = self.client.get('/api/large-fixture', headers={'Accept-Encoding': 'gzip, deflate'})
        self.assertEqual(zipped.headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(gzip.decompress(zipped.data), plain.data)
        self.assertLess(len(zipped.data), len(plain.data) // 4)
        self.assertIn('Accept-Encoding', zipped.headers.get('Vary', ''))
        self.assertIn('Accept-Encoding', plain.headers.get('Vary', ''))
        self.assertEqual(zipped.content_length, len(zipped.data))
        self.assertEqual(zipped.headers['Cache-Control'], 'no-store')

    def test_disabled_gzip_and_missing_accept_header_stay_plain(self):
        for encoding in ('', 'br', 'gzip;q=0, identity', 'gzip;q=0,*;q=1'):
            with self.subTest(encoding=encoding):
                result = self.client.get('/api/large-fixture', headers={'Accept-Encoding': encoding})
                self.assertNotIn('Content-Encoding', result.headers)
                self.assertEqual(result.json['body'], self.payload)

    def test_no_compression_for_pdf_ranges_small_responses_or_head(self):
        for path, headers, method in (
            ('/pdf-fixture', {'Accept-Encoding': 'gzip'}, 'GET'),
            ('/api/large-fixture', {'Accept-Encoding': 'gzip', 'Range': 'bytes=0-63'}, 'GET'),
            ('/small-fixture', {'Accept-Encoding': 'gzip'}, 'GET'),
            ('/api/large-fixture', {'Accept-Encoding': 'gzip'}, 'HEAD'),
        ):
            with self.subTest(path=path, method=method):
                result = self.client.open(path, method=method, headers=headers)
                self.assertNotIn('Content-Encoding', result.headers)


if __name__ == '__main__':
    unittest.main()

import importlib
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        source = (ROOT / 'src/airworthiness/app.py').read_text(encoding='utf-8')
        self.assertIn('def create_app(', source, 'Offline app factory is not implemented')
        factory = importlib.import_module('airworthiness.app').create_app
        self.app = factory({'TESTING': True, 'DATA_ROOT': ROOT, 'DATABASE': Path(self.temp.name) / 'test.sqlite3'})
        self.client = self.app.test_client()

    def test_api_nine_chapters_search_and_quality(self):
        self.assertEqual(self.client.get('/api/overview').json['totals']['sources'], 189)
        self.assertGreater(self.client.get('/api/resources?q=适航').json['total'], 0)
        self.assertEqual(self.client.get('/api/chapters/ch03').json['id'], 'ch03')
        self.assertIn('html', self.client.get('/api/documents/CH03-S001').json)
        self.assertEqual(len(self.client.get('/api/quality').json['chapters']), 9)

    def test_invalid_requests_return_actionable_errors(self):
        for url in ['/api/resources?page=bad', '/api/resources?status=bad', '/api/resources?content_kind=bad', '/api/resources?chapter=ch99', '/api/resources?q=abc%00def']:
            self.assertEqual(self.client.get(url).status_code, 400, url)
        for url in ['/api/documents/no-such-source', '/api/chapters/ch99', '/chapters/ch99']:
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_no_external_runtime_or_database_service_required(self):
        health = self.client.get('/api/health')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json['mode'], 'offline')
        self.assertEqual(health.headers['X-Content-Type-Options'], 'nosniff')


if __name__ == '__main__':
    unittest.main()

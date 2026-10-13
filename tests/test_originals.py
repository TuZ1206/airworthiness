"""A local original is served only when source and cached bytes both verify."""
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


class OriginalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('airworthiness.originals'))
        self.module = importlib.import_module('airworthiness.originals')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.url = 'https://www.caac.gov.cn/file.pdf'
        self.raw = b'%PDF-1.7\nverified official bytes for route fixture'
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.key = hashlib.sha256(self.url.encode()).hexdigest()
        self.cache = self.root / '.cache/acquisition'
        self.cache.mkdir(parents=True)
        self.path = self.cache / (self.key + '.bin')
        self.path.write_bytes(self.raw)
        self.meta = dict(request_url=self.url, url=self.url, original_sha256=self.sha,
                         size=len(self.raw), redirects=[], content_type='application/pdf')
        (self.cache / (self.key + '.json')).write_text(json.dumps(self.meta))
        self.doc = dict(source_id='CH01-S001', body_provenance=dict(url=self.url, original_sha256=self.sha))

    def test_verified_pdf_is_available(self):
        self.assertEqual(self.module.cached_original(self.root, self.doc), self.path)

    def test_redirect_cache_uses_request_key_and_checks_final_url(self):
        final = 'https://www.caac.gov.cn/redirected.pdf'
        self.meta.update(url=final, redirects=[self.url])
        (self.cache / (self.key + '.json')).write_text(json.dumps(self.meta))
        self.doc['body_provenance'].update(url=final, request_url=self.url)
        self.assertEqual(self.module.cached_original(self.root, self.doc), self.path)
        self.assertEqual(self.module.original_snapshot(self.root, self.doc).getvalue(), self.raw)
        self.doc['body_provenance']['url'] = 'https://www.caac.gov.cn/unrelated.pdf'
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_ingest_preserves_request_url_for_original_cache_lookup(self):
        from tests.test_locator_integration import make_inputs
        from airworthiness.ingest import load_inputs
        make_inputs(self.root)
        path = self.root/'data/acquired/manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['CH01-S001']['request_url'] = self.url
        path.write_text(json.dumps(manifest), encoding='utf-8')
        _, docs, _, errors, _ = load_inputs(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(docs[0]['body_provenance'].get('request_url'), self.url)

    def test_tampered_or_wrong_source_hash_is_not_available(self):
        self.doc['body_provenance']['original_sha256'] = '0' * 64
        self.assertIsNone(self.module.cached_original(self.root, self.doc))
        self.doc['body_provenance']['original_sha256'] = self.sha
        self.path.write_bytes(self.raw + b'tampered')
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_html_missing_cache_or_nonofficial_url_never_served(self):
        for url in ['https://evil.example/file.pdf', 'https://www.gov.cn/not-cached.pdf']:
            self.doc['body_provenance']['url'] = url
            self.assertIsNone(self.module.cached_original(self.root, self.doc))
        self.doc['body_provenance']['url'] = self.url
        self.path.write_bytes(b'<html>not PDF</html>')
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_uploaded_pdf_provenance_works_without_acquisition(self):
        self.doc['body_provenance'] = dict(pdf_url=self.url, pdf_sha256=self.sha)
        self.assertEqual(self.module.cached_original(self.root, self.doc), self.path)

    def test_file_is_never_resolved_from_an_arbitrary_manifest_path(self):
        self.doc['body_provenance'] = dict(path='../../secrets.pdf', url=self.url)
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_separate_appendix_retains_its_own_bytes_and_hash(self):
        self.doc['body_provenance']['originals'] = [dict(label='附录', url=self.url, original_sha256=self.sha)]
        self.assertEqual(self.module.cached_original(self.root, self.doc, 0), self.path)
        self.assertIsNone(self.module.cached_original(self.root, self.doc, 1))
        self.assertIsNone(self.module.cached_original(self.root, self.doc, -1))

    def test_archive_original_requires_both_archive_and_member_hash(self):
        archive = b'Rar!\x1a\x07\x01\x00verified archive fixture'
        archive_sha = hashlib.sha256(archive).hexdigest()
        self.path.write_bytes(archive)
        self.meta.update(original_sha256=archive_sha, size=len(archive))
        (self.cache / (self.key + '.json')).write_text(json.dumps(self.meta))
        member = self.cache / 'archive' / (self.key + '.pdf')
        member.parent.mkdir()
        member.write_bytes(self.raw)
        self.doc['body_provenance'].update(original_sha256=archive_sha, archive_member='source.pdf', archive_member_sha256=self.sha)
        self.assertEqual(self.module.cached_original(self.root, self.doc), member)
        member.write_bytes(self.raw + b'tampered')
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_api_serves_verified_pdf_and_advertises_local_link(self):
        from airworthiness.app import create_app
        with patch('airworthiness.app.catalog.ensure_catalog'), patch('airworthiness.app.catalog.document', return_value=self.doc):
            client = create_app(dict(TESTING=True, DATA_ROOT=self.root)).test_client()
            doc = client.get('/api/documents/CH01-S001').get_json()
            self.assertTrue(doc.get('original_available'))
            self.assertEqual(len(doc.get('originals', [])), 1)
            response = client.get(doc['original_url'])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'application/pdf')
            self.assertEqual(response.data, self.raw)
            self.assertIn('inline', response.headers['Content-Disposition'])
            response.close()
            self.path.unlink()
            self.assertEqual(client.get(doc['original_url']).status_code, 404)
            self.assertEqual(client.get(doc['original_url'] + '?index=bad').status_code, 400)

    def test_archive_member_needs_an_actual_rar_parent(self):
        member = self.cache / 'archive' / (self.key + '.pdf')
        member.parent.mkdir()
        member.write_bytes(self.raw)
        self.doc['body_provenance'].update(archive_member='source.pdf', archive_member_sha256=self.sha)
        self.assertIsNone(self.module.cached_original(self.root, self.doc))

    def test_response_serves_verified_snapshot_after_path_replacement(self):
        from airworthiness.app import create_app
        from flask import send_file as real_send_file
        def replace_before_send(target, **kwargs):
            self.path.write_bytes(b'%PDF-1.7\nunverified replacement')
            return real_send_file(target, **kwargs)
        with patch('airworthiness.app.catalog.ensure_catalog'), patch('airworthiness.app.catalog.document', return_value=self.doc):
            client = create_app(dict(TESTING=True, DATA_ROOT=self.root)).test_client()
            with patch('airworthiness.app.send_file', side_effect=replace_before_send):
                response = client.get('/api/documents/CH01-S001/original')
                self.addCleanup(response.close)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, self.raw)
                response.close()


if __name__ == '__main__':
    unittest.main()

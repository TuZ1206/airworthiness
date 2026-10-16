"""Resolve only a hash-bound official PDF from the local download cache."""
import hashlib
from io import BytesIO
import json
import re
from pathlib import Path

from .acquire_http import canonical_url


def cached_original(root, document, index=0):
    """No network or arbitrary manifest paths. Missing originals stay unavailable."""
    source = document.get('body_provenance') or {}
    originals = source.get('originals') or [source]
    if type(index) is not int or not 0 <= index < len(originals):
        return None
    source = originals[index]
    if not isinstance(source, dict):
        return None
    url = source.get('url') or source.get('pdf_url')
    expected = source.get('original_sha256') or source.get('pdf_sha256')
    if not url or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        return None
    try:
        url = canonical_url(url)
        request_url = canonical_url(source.get('request_url') or url)
        root = Path(root).resolve()
        folder = (root / '.cache/acquisition').resolve()
        if not folder.is_relative_to(root):
            return None
        key = hashlib.sha256(request_url.encode()).hexdigest()
        raw = folder / (key + '.bin')
        meta_path = folder / (key + '.json')
        if raw.resolve().parent != folder or meta_path.resolve().parent != folder:
            return None
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if (meta['request_url'] != request_url or canonical_url(meta['url']) != url
                or meta['original_sha256'] != expected
                or not 0 < raw.stat().st_size <= 32 * 1024 * 1024
                or raw.stat().st_size != meta['size']):
            return None
        canonical_url(meta['url'])
        for target in meta.get('redirects', []):
            canonical_url(target)
        with raw.open('rb') as handle:
            magic = handle.read(16).lstrip()
            archive = source.get('archive_member_sha256')
            if archive and not magic.startswith((b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')):
                return None
            if not archive and not magic.startswith(b'%PDF-'):
                return None
            handle.seek(0)
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                return None
        if archive:
            if not re.fullmatch(r'[0-9a-f]{64}', archive):
                return None
            raw = folder / 'archive' / (key + '.pdf')
            if (raw.resolve().parent != folder / 'archive'
                    or not 0 < raw.stat().st_size <= 256 * 1024 * 1024):
                return None
            with raw.open('rb') as handle:
                if not handle.read(16).lstrip().startswith(b'%PDF-'):
                    return None
                handle.seek(0)
                if hashlib.file_digest(handle, 'sha256').hexdigest() != archive:
                    return None
        return raw
    except (OSError, ValueError, KeyError, TypeError):
        return None


def original_snapshot(root, document, index=0):
    """Serve the exact verified immutable bytes, never reopen a verified path."""
    path = cached_original(root, document, index)
    if path is None:
        return None
    source = document['body_provenance']
    source = (source.get('originals') or [source])[index]
    expected = source.get('archive_member_sha256') or source.get('original_sha256') or source.get('pdf_sha256')
    limit = (256 if source.get('archive_member_sha256') else 32) * 1024 * 1024
    try:
        with path.open('rb') as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    if (len(data) > limit or not data.lstrip().startswith(b'%PDF-')
            or hashlib.sha256(data).hexdigest() != expected):
        return None
    return BytesIO(data)

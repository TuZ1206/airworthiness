"""Compress large, read-only text responses without touching PDF byte ranges."""
import gzip

from flask import request


def compress_text_response(response):
    if (request.method != 'GET' or response.status_code != 200
            or response.direct_passthrough or 'Range' in request.headers
            or response.headers.get('Content-Encoding')
            or response.mimetype not in {'application/json', 'text/html', 'text/css',
                                         'text/javascript', 'application/javascript'}):
        return response
    raw = response.get_data()
    if len(raw) < 2048:
        return response
    response.vary.add('Accept-Encoding')
    if request.accept_encodings['gzip'] <= 0:
        return response
    packed = gzip.compress(raw, compresslevel=5, mtime=0)
    if len(packed) < len(raw):
        response.set_data(packed)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers.pop('ETag', None)
    return response

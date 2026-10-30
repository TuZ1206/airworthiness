"""Offline resource hall. No credentials, Neo4j or model service required."""
import os

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import HTTPException

from . import catalog
from .config import project_root
from .originals import cached_original, original_snapshot
from .access_notes import enrich_access_notes
from .http_response import compress_text_response


def create_app(settings=None):
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    root = project_root()
    app.config.update(DATA_ROOT=root, DATABASE=root / ".cache/library.sqlite3", MAX_CONTENT_LENGTH=1024 * 1024)
    app.config.update(settings or {})
    app.json.ensure_ascii = False
    catalog.ensure_catalog(app.config["DATA_ROOT"], app.config["DATABASE"])

    @app.get("/")
    def home():
        return render_template("hall.html")

    @app.get("/quality")
    def quality_page():
        return redirect(url_for("home"))

    @app.get("/chapters/<chapter_id>")
    def chapter_page(chapter_id):
        if not catalog.chapter(app.config["DATABASE"], chapter_id):
            abort(404, description="未找到该章节")
        return render_template("hall.html")

    @app.get("/api/overview")
    def overview():
        return jsonify(catalog.overview(app.config["DATABASE"]))

    @app.get("/api/resources")
    def resources():
        values = {name: request.args.get(name, "").strip() for name in ("q", "chapter", "status", "content_kind")}
        if len(values["q"]) > 200:
            abort(400, description="搜索关键词请控制在 200 字以内")
        if any(ord(char) < 32 for char in values["q"]):
            abort(400, description="搜索关键词包含不支持的控制字符")
        choices = {"chapter": {"", *(f"ch{x:02}" for x in range(1, 10))}, "status": {"", "effective", "abolished", "unknown"}, "content_kind": {"", "fulltext", "extracted", "excerpt", "metadata"}}
        for key, allowed in choices.items():
            if values[key] not in allowed:
                abort(400, description=f"无效的筛选条件：{key}")
        try:
            values["page"] = int(request.args.get("page", 1))
            values["page_size"] = int(request.args.get("page_size", 20))
        except ValueError:
            abort(400, description="页码和每页条数必须为整数")
        return jsonify(catalog.resources(app.config["DATABASE"], **values))

    @app.get("/api/chapters/<chapter_id>")
    def chapter(chapter_id):
        result = catalog.chapter(app.config["DATABASE"], chapter_id)
        if not result:
            abort(404, description="未找到该章节")
        return jsonify(result)

    @app.get("/api/chapters/<chapter_id>/knowledge-map")
    def knowledge_map(chapter_id):
        result = catalog.knowledge_map(app.config["DATABASE"], chapter_id)
        if not result:
            abort(404, description="未找到该章节")
        return jsonify(result)

    @app.get("/api/knowledge-nodes/<knowledge_node_id>")
    def knowledge_node(knowledge_node_id):
        result = catalog.knowledge_node(app.config["DATABASE"], knowledge_node_id)
        if not result:
            abort(404, description="未找到已审核的知识节点")
        return jsonify(result)

    @app.get("/api/documents/<source_id>")
    def document(source_id):
        result = catalog.document(app.config["DATABASE"], source_id)
        if not result:
            abort(404, description="未找到该资料")
        enrich_access_notes(app.config['DATA_ROOT'], [result])
        if result.get('access_note'):
            result['extraction_note'] = result.get('extraction_note', '') + ' 获取核对：' + result['access_note']
        provenance = result.get('body_provenance') or {}
        candidates = provenance.get('originals') or [provenance]
        result['originals'] = [
            dict(label=item.get('label') or '本地 PDF 原件',
                 url=url_for('original', source_id=source_id, **({'index': index} if index else {})))
            for index, item in enumerate(candidates[:16])
            if cached_original(app.config['DATA_ROOT'], result, index) is not None
        ]
        result['original_available'] = bool(result['originals'])
        result['original_url'] = result['originals'][0]['url'] if result['originals'] else ''
        return jsonify(result)

    @app.get('/api/documents/<source_id>/original')
    def original(source_id):
        try:
            index = int(request.args.get('index', '0'))
        except ValueError:
            abort(400, description='无效的附件索引')
        document = catalog.document(app.config['DATABASE'], source_id)
        snapshot = original_snapshot(app.config['DATA_ROOT'], document, index) if document else None
        if snapshot is None:
            abort(404, description='本机没有已校验的该资料 PDF 原件')
        return send_file(snapshot, mimetype='application/pdf', as_attachment=False,
                         download_name=source_id + '.pdf', conditional=True)

    @app.get("/api/quality")
    def quality():
        result = catalog.quality(app.config['DATABASE'])
        enrich_access_notes(app.config['DATA_ROOT'], result['gaps'])
        return jsonify(result)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", mode="offline", sources=catalog.overview(app.config["DATABASE"])["totals"]["sources"])

    @app.errorhandler(HTTPException)
    def error(exc):
        if request.path.startswith("/api/"):
            return jsonify(error=exc.description), exc.code
        return f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>页面未找到</title><h1>{exc.code}</h1><p>未找到所请求的页面。</p><a href='/'>返回资源大厅</a></html>", exc.code

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        frame_ancestors = "'none'"
        if (request.endpoint == "original" and 200 <= response.status_code < 300
                and response.mimetype == "application/pdf"):
            frame_ancestors = "'self'"
        response.headers["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors {frame_ancestors}; base-uri 'none'; object-src 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return compress_text_response(response)

    return app


def main():
    from waitress import serve
    port = int(os.environ.get("AIRWORTHINESS_PORT", "5000"))
    print(f"资源大厅：http://127.0.0.1:{port} （仅本机访问）", flush=True)
    serve(create_app(), host="127.0.0.1", port=port, threads=4)


if __name__ == "__main__":
    main()

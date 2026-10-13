"""Offline resource hall. No credentials, Neo4j or model service required."""
import os

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import catalog
from .config import project_root


def create_app(settings=None):
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    root = project_root()
    app.config.update(DATA_ROOT=root, DATABASE=root / ".cache/library.sqlite3", MAX_CONTENT_LENGTH=1024 * 1024)
    app.config.update(settings or {})
    app.json.ensure_ascii = False
    catalog.ensure_catalog(app.config["DATA_ROOT"], app.config["DATABASE"])

    @app.get("/")
    @app.get("/quality")
    def home():
        return render_template("hall.html")

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

    @app.get("/api/documents/<source_id>")
    def document(source_id):
        result = catalog.document(app.config["DATABASE"], source_id)
        if not result:
            abort(404, description="未找到该资料")
        return jsonify(result)

    @app.get("/api/quality")
    def quality():
        return jsonify(catalog.quality(app.config["DATABASE"]))

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
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


def main():
    from waitress import serve
    port = int(os.environ.get("AIRWORTHINESS_PORT", "5000"))
    print(f"资源大厅：http://127.0.0.1:{port} （仅本机访问）", flush=True)
    serve(create_app(), host="127.0.0.1", port=port, threads=4)


if __name__ == "__main__":
    main()

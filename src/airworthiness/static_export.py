"""Bounded, offline GitHub Pages export of the existing catalog and reader.

Destinations must be new or empty. A failed export is left in place for
inspection; this module never deletes a destination or recursively removes
files. Only generated JSON/HTML, named browser assets and opted-in verified
PDF snapshots are published.
"""
import argparse
import gzip
from html import escape
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from . import catalog
from .access_notes import enrich_access_notes
from .app import create_app
from .originals import cached_original, original_snapshot


MAX_ORIGINAL_BYTES = 20 * 1024 * 1024
MAX_ORIGINALS_BYTES = 350 * 1024 * 1024
MAX_SITE_BYTES = 1024 ** 3
STATIC_ASSETS = (
    "hall.css", "hall.js", "hall-core.js", "hall-app.js", "hall-home.js",
    "hall-content.js", "hall-document-view.js", "hall-reader.js",
    "hall-quality.js", "hall-static.js",
)
# Acquisition payloads also contain local paths and raw diagnostic logs.
# Retain documentary facts; publishing those machine-local fields is unnecessary.
ACQUISITION_FIELDS = frozenset((
    "content_kind", "url", "landing_url", "request_url", "sha256",
    "source_sha256", "original_sha256", "tool_snapshot_sha256", "method",
    "crawled_at", "acquired_at", "retrieved_at", "fetched_at", "page_count",
    "text_chars", "non_text_elements", "note", "review_status", "applied",
    "skip_reason", "originals", "archive_member", "archive_member_sha256",
))


def _base_path(value):
    if not isinstance(value, str):
        raise ValueError("base_path must be a root-relative URL path")
    if value in ("", "/"):
        return ""
    # Deliberately reject encoded paths, traversal, authorities and query strings.
    if not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+/?", value):
        raise ValueError("base_path must contain only safe URL path segments")
    return value.rstrip("/")


def _no_links(path):
    """Check lexical ancestors before resolution, including Windows junctions."""
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Symlinks and reparse points are not allowed: {current}")


def _locations(root, output):
    root = Path(root).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    _no_links(root)
    _no_links(output)
    root, output = root.resolve(), output.resolve()
    home = Path.home().resolve()
    if output in {root, *root.parents, home, *home.parents}:
        raise ValueError("Output cannot be the source root, home, or an ancestor")
    if any(output.is_relative_to(root / folder) for folder in ("data", ".git")):
        raise ValueError("Output cannot be inside source data or .git")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory; existing files are never removed")
    if not (root / "data/chapters/catalog.json").is_file():
        raise ValueError("Source root must contain data/chapters/catalog.json")
    for name in ("chapters", "acquired", "verification"):
        folder = root / "data" / name
        _no_links(folder)
        for path in folder.rglob("*"):
            _no_links(path)
    chapters = json.loads((root / "data/chapters/catalog.json").read_text(encoding="utf-8"))
    if not isinstance(chapters, list) or any(
            not isinstance(chapter, dict) or not re.fullmatch(r"ch[0-9]{2}", str(chapter.get("id", "")))
            for chapter in chapters):
        raise ValueError("Chapter IDs must have the form chNN")
    return root, output


def _route(value, base):
    if not value.startswith("/") or value.startswith("//"):
        return value
    parts = urlsplit(value)
    path = parts.path
    if path.rstrip("/") == "/quality" or re.fullmatch(r"/chapters/ch[0-9]{2}/?", path):
        path = path.rstrip("/") + "/"
    elif path != "/" and not path.startswith("/static/"):
        return value
    return urlunsplit(("", "", base + path, parts.query, parts.fragment))


def _glossary_routes(record, base):
    for term in record.get("glossary", []):
        term["anchor_or_url"] = _route(term["anchor_or_url"], base)


def _shell(client, base):
    response = client.get("/")
    if response.status_code != 200:
        raise ValueError("The existing hall template could not be rendered")
    rendered = response.get_data(as_text=True)
    for old, new in (("适航离线资源馆", "适航法规资源馆"), ("离线资料库", "在线验收版"),
                     ("本地资料", "在线资料")):
        rendered = rendered.replace(old, new)
    soup = BeautifulSoup(rendered, "html.parser")
    for old in soup.find_all("meta", attrs={"http-equiv": re.compile(r"^content-security-policy$", re.I)}):
        old.decompose()
    soup.head.insert(0, soup.new_tag("meta", attrs={
        "http-equiv": "Content-Security-Policy",
        "content": ("default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'"),
    }))
    for name, content in (("airworthiness-mode", "static"), ("airworthiness-base", base)):
        for old in soup.find_all("meta", attrs={"name": name}):
            old.decompose()
        node = soup.new_tag("meta", attrs={"name": name, "content": content})
        soup.head.append(node)
    for node in soup.select("[href], [src]"):
        for attribute in ("href", "src"):
            if node.has_attr(attribute):
                node[attribute] = _route(node[attribute], base)
    return str(soup).encode("utf-8")


def _source_revision(root):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=5, check=False)
        lines = result.stdout.splitlines()
        if (result.returncode == 0 and len(lines) == 2 and Path(lines[0]).resolve() == root
                and re.fullmatch(r"[0-9a-f]{40,64}", lines[1])):
            return lines[1]
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    return None


def export_site(root, output, base_path="/airworthiness", include_originals=False):
    """Export a new site and return its public ``manifest.json`` dictionary.

    JSON uses the existing API shapes, with all resource rows in ``{items:[]}``.
    Documents additionally retain raw ``body`` and set ``deployment_mode`` to
    ``static``. Server original fields always remain false/empty; optional
    verified copies appear solely in ``static_originals: [{label, url}]``.
    Every JSON, including the manifest, has an identical decompressed .gz copy.
    Size failures leave a bounded partial output; retry with a fresh destination.
    """
    base = _base_path(base_path)
    root, output = _locations(root, output)
    written_bytes = 0
    original_bytes = 0
    original_count = 0

    def write(name, data):
        nonlocal written_bytes
        if written_bytes + len(data) >= MAX_SITE_BYTES:
            raise ValueError("Export would exceed the GitHub Pages site size budget")
        target = output / name
        _no_links(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        written_bytes += len(data)

    def write_json(name, value):
        data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        write(name, data)
        write(name + ".gz", gzip.compress(data, mtime=0))

    # The catalog is disposable and never lives in the source tree or export.
    fd, database_name = tempfile.mkstemp(prefix="airworthiness-export-", suffix=".sqlite3")
    os.close(fd)
    database = Path(database_name)
    try:
        app = create_app(dict(TESTING=True, DATA_ROOT=root, DATABASE=database))
        assets = {}
        for name in STATIC_ASSETS:
            asset = Path(app.static_folder) / name
            _no_links(asset)
            if not asset.is_file():
                raise ValueError(f"Required static asset is missing: {name}")
            assets[name] = asset.read_bytes()
        client = app.test_client()
        overview = client.get("/api/overview").get_json()
        quality = client.get("/api/quality").get_json()
        with catalog.connect(database) as db:
            rows = db.execute("SELECT payload,search_text FROM documents ORDER BY chapter_id,source_id").fetchall()
        documents = [(json.loads(row["payload"]), row["search_text"]) for row in rows]
        chapter_ids = [chapter["id"] for chapter in overview["chapters"]]
        for payload, _ in documents:
            if (not re.fullmatch(r"CH[0-9]{2}-S[0-9]{3}", payload["source_id"])
                    or payload["chapter_id"] not in chapter_ids):
                raise ValueError("Invalid source or chapter ID")
        html = _shell(client, base)
        write("index.html", html)
        write("quality/index.html", html)
        write(".nojekyll", b"")
        write("404.html", (
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>页面未找到</title></head><body><h1>404 · 页面未找到</h1>'
            f'<p><a href="{escape(base, quote=True)}/">返回资源大厅</a></p></body></html>'
        ).encode("utf-8"))
        for name, data in assets.items():
            write("static/" + name, data)
        write_json("data/overview.json", overview)
        write_json("data/quality.json", quality)
        write_json("data/resources.json", {"items": [catalog._public(payload) for payload, _ in documents]})
        for chapter_id in chapter_ids:
            chapter = catalog.chapter(database, chapter_id)
            _glossary_routes(chapter, base)
            write(f"chapters/{chapter_id}/index.html", html)
            write_json(f"data/chapters/{chapter_id}.json", chapter)
            write_json(f"data/search/{chapter_id}.json", [
                dict(source_id=payload["source_id"], search_text=search_text,
                     plain=re.sub(r"\s+", "", re.sub(r"(?m)^#{1,6}\s+", "", payload["body"])))
                for payload, search_text in documents if payload["chapter_id"] == chapter_id
            ])
        for payload, _ in documents:
            source_id = payload["source_id"]
            doc = catalog.document(database, source_id)
            enrich_access_notes(root, [doc])
            if doc.get("access_note"):
                doc["extraction_note"] += " 获取核对：" + doc["access_note"]
            doc.update(body=payload["body"], deployment_mode="static", original_available=False,
                       original_url="", originals=[], static_originals=[])
            doc["acquisition"] = {key: value for key, value in doc.get("acquisition", {}).items()
                                  if key in ACQUISITION_FIELDS}
            _glossary_routes(doc, base)
            if include_originals:
                provenance = doc.get("body_provenance") or {}
                candidates = provenance.get("originals") or [provenance]
                for index, item in enumerate(candidates[:16]):
                    path = cached_original(root, doc, index)
                    if path is None:
                        continue
                    try:
                        _no_links(path)
                        size = path.stat().st_size
                    except (OSError, ValueError):
                        continue
                    if size > MAX_ORIGINAL_BYTES or original_bytes + size > MAX_ORIGINALS_BYTES:
                        continue
                    snapshot = original_snapshot(root, doc, index)
                    if snapshot is None:
                        continue
                    with snapshot:
                        data = snapshot.getvalue()
                    if len(data) > MAX_ORIGINAL_BYTES or original_bytes + len(data) > MAX_ORIGINALS_BYTES:
                        continue
                    name = f"originals/{source_id}/{index}.pdf"
                    write(name, data)
                    doc["static_originals"].append(dict(label=item.get("label") or "本地 PDF 原件", url=base + "/" + name))
                    original_bytes += len(data)
                    original_count += 1
            write_json(f"data/documents/{source_id}.json", doc)
        manifest = dict(source_count=overview["totals"]["sources"], document_count=len(documents),
                        chapter_count=len(chapter_ids), original_count=original_count,
                        original_bytes=original_bytes, generated_at=quality["generated_at"],
                        source_revision=_source_revision(root), base_path=base,
                        deployment_mode="static", include_originals=bool(include_originals))
        write_json("manifest.json", manifest)
        return manifest
    finally:
        database.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-path", default="/airworthiness")
    parser.add_argument("--include-originals", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = export_site(args.root, args.output, args.base_path, args.include_originals)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Export failed: {exc}\n")
    print(json.dumps(manifest, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

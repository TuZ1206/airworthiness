"""Rebuildable SQLite catalog and literal Chinese substring search."""
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .ingest import load_inputs
from .reading import render_document

PUBLIC_FIELDS = "source_id,title,chapter_id,chapter_title,document_code,document_status,publish_date,url,review_status,content_kind".split(",")
NAVIGATION_NOTE = ("条款、章节定位依据正文的明确编号；PDF 页目录依据提取页码。"
                   "自动阅读分段和普通段落仅用于导航，不代表原文条款。"
                   "术语关键词匹配不等于释义核验；精确引文定位也不代表专业审核通过。")


@contextmanager
def connect(path):
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def input_fingerprint(root):
    root = Path(root).resolve()
    paths = [path for folder in ("chapters", "acquired", "verification")
             for path in sorted((root / "data" / folder).rglob("*"))]
    digest = hashlib.sha256()
    for module in ("catalog.py", "ingest.py", "reading.py", "locators.py", "verification.py"):
        path = Path(__file__).with_name(module)
        digest.update(module.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<not-installed>")
    for path in paths:
        if path.is_file():
            stat = path.stat()
            digest.update(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
            if path.is_relative_to(root / "data/verification"):
                digest.update(path.read_bytes())
    return digest.hexdigest()


def build_catalog(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    chapters, docs, terms, errors, issues = load_inputs(root)
    if errors:
        raise ValueError("Data validation failed:\n" + "\n".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="catalog-", suffix=".sqlite3", dir=path.parent)
    os.close(fd)
    try:
        with connect(temporary) as db:
            db.executescript("""
                CREATE TABLE chapters (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE documents (source_id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL,
                  title TEXT, document_code TEXT, document_status TEXT, content_kind TEXT,
                  search_text TEXT, payload TEXT NOT NULL);
                CREATE INDEX docs_chapter ON documents(chapter_id);
                CREATE TABLE terms (term_id TEXT PRIMARY KEY, chapter_id TEXT, source_id TEXT, payload TEXT);
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE VIRTUAL TABLE search USING fts5(search_text, tokenize='trigram');
            """)
            for chapter in chapters:
                db.execute("INSERT INTO chapters VALUES (?,?)", (chapter["id"], json.dumps(chapter, ensure_ascii=False)))
            for doc in docs:
                search_text = re.sub(r"\s+", "", doc["title"] + " " + doc["document_code"] + " " + doc["body"]).lower()
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)", (doc["source_id"], doc["chapter_id"], doc["title"], doc["document_code"], doc["document_status"], doc["content_kind"], search_text, json.dumps(doc, ensure_ascii=False)))
                rowid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                db.execute("INSERT INTO search(rowid,search_text) VALUES (?,?)", (rowid, search_text))
            for term in terms:
                db.execute("INSERT INTO terms VALUES (?,?,?,?)", (term["term_id"], term["chapter_id"], term["source_id"], json.dumps(term, ensure_ascii=False)))
            for key, value in {"generated_at": datetime.now(timezone.utc).isoformat(), "fingerprint": input_fingerprint(root), "issues": issues, "errors": errors}.items():
                db.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))
            db.commit()
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    return {"errors": errors, "issues": issues, "sources": len(docs), "chapters": len(chapters)}


def ensure_catalog(root, path):
    if Path(path).is_file():
        try:
            with connect(path) as db:
                stored = json.loads(db.execute("SELECT value FROM metadata WHERE key='fingerprint'").fetchone()[0])
            if stored == input_fingerprint(Path(root).resolve()):
                return
        except (sqlite3.Error, TypeError, json.JSONDecodeError):
            pass
    build_catalog(root, path)


def _public(payload, q=""):
    result = {key: payload[key] for key in PUBLIC_FIELDS}
    plain = re.sub(r"\s+", "", re.sub(r"(?m)^#{1,6}\s+", "", payload["body"]))
    needle = re.sub(r"\s+", "", q).lower()
    position = plain.lower().find(needle) if needle else -1
    start = max(0, position - 45) if position >= 0 else 0
    result["snippet"] = ("…" if start else "") + plain[start:start + 180] + ("…" if len(plain) > start + 180 else "")
    return result


def overview(path):
    with connect(path) as db:
        chapters = [json.loads(row[0]) for row in db.execute("SELECT payload FROM chapters ORDER BY id")]
        totals = dict(chapters=len(chapters), sources=0, fulltext=0, extracted=0, excerpt=0, metadata=0)
        for chapter in chapters:
            chapter["count"] = 0
            for kind in ("fulltext", "extracted", "excerpt", "metadata"):
                count = db.execute("SELECT count(*) FROM documents WHERE chapter_id=? AND content_kind=?", (chapter["id"], kind)).fetchone()[0]
                chapter[kind + "_count"] = count
                chapter["count"] += count
                totals[kind] += count
            totals["sources"] += chapter["count"]
    return {"chapters": chapters, "totals": totals}


def resources(path, q="", chapter="", status="", content_kind="", page=1, page_size=20):
    page_size, page = max(1, min(100, int(page_size))), max(1, int(page))
    clauses, params = [], []
    for key, value in (("chapter_id", chapter), ("document_status", status), ("content_kind", content_kind)):
        if value:
            clauses.append("d." + key + "=?")
            params.append(value)
    needle = re.sub(r"\s+", "", q[:200]).lower()
    order = "d.chapter_id, d.source_id"
    join = ""
    if len(needle) >= 3:
        join = " JOIN search ON search.rowid=d.rowid"
        clauses.append("search MATCH ?")
        params.append('"' + needle.replace('"', '""') + '"')
        order = "bm25(search), " + order
    elif needle:
        clauses.append("instr(d.search_text, ?) > 0")
        params.append(needle)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(path) as db:
        total = db.execute("SELECT count(*) FROM documents d" + join + where, params).fetchone()[0]
        pages = max(1, math.ceil(total / page_size))
        page = min(page, pages)
        rows = db.execute("SELECT d.payload FROM documents d" + join + where + " ORDER BY " + order + " LIMIT ? OFFSET ?", [*params, page_size, (page - 1) * page_size]).fetchall()
    return {"items": [_public(json.loads(row[0]), q) for row in rows], "total": total, "page": page, "page_size": page_size, "pages": pages}


def chapter(path, chapter_id):
    with connect(path) as db:
        row = db.execute("SELECT payload FROM chapters WHERE id=?", (chapter_id,)).fetchone()
        if not row:
            return None
        result = json.loads(row[0])
        result["documents"] = [_public(json.loads(x[0])) for x in db.execute("SELECT payload FROM documents WHERE chapter_id=? ORDER BY source_id", (chapter_id,))]
        result["glossary"] = [json.loads(x[0]) for x in db.execute("SELECT payload FROM terms WHERE chapter_id=? ORDER BY term_id", (chapter_id,))]
    text = "## 阅读导引\n\n" + result["description"] + "\n\n本页为资料导航，不构成官方原文或专业结论。选择左侧文件，可在本页阅读现有正文。\n\n## 本章主题\n\n" + "\n".join("- " + x for x in result.get("topics", [])) + "\n\n## 使用提示\n\n先查看文件有效状态与正文可用性，再核对相关段落。所有待审资料均需专业成员复核。"
    result["guide_html"] = render_document(text)[0]
    return result


def document(path, source_id):
    with connect(path) as db:
        row = db.execute("SELECT payload FROM documents WHERE source_id=?", (source_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        result = {**payload, **_public(payload)}
        result.pop("body")
        result["html"], result["toc"] = render_document(payload["body"], extracted=payload["content_kind"] == "extracted")
        result["navigation_note"] = NAVIGATION_NOTE
        if payload["content_kind"] == "extracted":
            result["extraction_note"] += " 自动阅读分段仅用于导航，不代表原文条款。"
        result["glossary"] = [json.loads(x[0]) for x in db.execute("SELECT payload FROM terms WHERE source_id=? ORDER BY term_id", (source_id,))]
        result["related_sources"] = []
        for other in db.execute("SELECT payload FROM documents WHERE source_id<>? ORDER BY source_id", (source_id,)):
            candidate = json.loads(other[0])
            if candidate["url"] == payload["url"]:
                result["related_sources"].append(_public(candidate))
    return result


def quality(path):
    result = overview(path)
    with connect(path) as db:
        for key in ("generated_at", "issues", "errors"):
            result[key] = json.loads(db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()[0])
        result["gaps"] = []
        result["resolved_metadata"] = []
        result["resolved_issues"] = []
        for row in db.execute("SELECT payload FROM documents ORDER BY source_id"):
            doc = json.loads(row[0])
            result["resolved_issues"].extend(doc.get("resolved_issues", []))
            result["resolved_metadata"].extend(
                {**entry, "source_id": doc["source_id"]}
                for entry in doc.get("metadata_verification", []) if isinstance(entry, dict)
                and entry.get("application") in {"corrected", "already_matches", "explained", "confirmed"})
            if doc["content_kind"] in {"metadata", "excerpt"}:
                result["gaps"].append({**_public(doc), "reason": doc["extraction_note"]})
    return result

"""Human-authored chapter knowledge maps, separate from source relation CSVs."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


STATUSES = {"pending", "approved", "rejected", "update_required"}
RELATION_TYPES = {"组成", "前提", "流程", "验证", "约束", "输出", "衔接"}
REVIEW_FIELDS = ["entity_type", "entity_id", "review_status", "reviewer", "reviewed_at",
                 "basis_source_ids", "comment", "data_version"]


def _csv_rows(path: Path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != REVIEW_FIELDS:
            raise ValueError("review-ledger.csv 表头不符合约定")
        return list(reader)


def load_review_ledger(root: Path):
    rows = _csv_rows(Path(root) / "data" / "reviews" / "review-ledger.csv")
    errors = []
    latest = {}
    for index, row in enumerate(rows, start=2):
        if row["review_status"] not in STATUSES:
            errors.append(f"review-ledger.csv:{index}: invalid status")
            continue
        if not row["entity_type"].strip() or not row["entity_id"].strip():
            errors.append(f"review-ledger.csv:{index}: entity required")
            continue
        if row["review_status"] == "approved" and not all(row[field].strip() for field in
                                                             ("reviewer", "reviewed_at", "basis_source_ids")):
            errors.append(f"review-ledger.csv:{index}: approved record needs reviewer/date/basis")
            continue
        latest[(row["entity_type"], row["entity_id"])] = {**row, "line": index}
    return rows, latest, errors


def _refs(value, source_ids, chapter_id, errors, label):
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: source_refs required")
        return []
    result = []
    for ref in value:
        if not isinstance(ref, dict) or ref.get("source_id") not in source_ids:
            errors.append(f"{label}: invalid source reference")
            continue
        if not ref["source_id"].startswith(chapter_id.upper() + "-"):
            errors.append(f"{label}: cross-chapter source reference")
            continue
        locator = ref.get("source_locator", "")
        if not isinstance(locator, str):
            errors.append(f"{label}: invalid source locator")
            continue
        result.append({"source_id": ref["source_id"], "source_locator": locator.strip()})
    return result


def load_knowledge_maps(root: Path, chapters: list[dict], documents: list[dict], ledger=None):
    """Load drafts and validate them without altering the fixed chapter CSVs."""
    root = Path(root)
    by_chapter = {chapter["id"]: chapter for chapter in chapters}
    doc_by_source = {doc["source_id"]: doc for doc in documents}
    if ledger is None:
        _, ledger, errors = load_review_ledger(root)
    else:
        errors = []
    maps = {}
    folder = root / "data" / "knowledge-maps"
    # Small offline fixtures and older checked-out datasets remain readable;
    # the real repository carries one explicit draft file per chapter.
    if not folder.is_dir():
        return maps, ledger, errors
    for chapter_id in by_chapter:
        path = folder / f"{chapter_id}.json"
        if not path.is_file():
            errors.append(f"{chapter_id}: knowledge map missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"{chapter_id}: knowledge map is invalid JSON")
            continue
        if payload.get("chapter_id") != chapter_id or not isinstance(payload.get("version"), str):
            errors.append(f"{chapter_id}: invalid knowledge map identity")
            continue
        if payload.get("review_status") not in STATUSES:
            errors.append(f"{chapter_id}: invalid knowledge map status")
        source_ids = {doc["source_id"] for doc in documents if doc["chapter_id"] == chapter_id}
        nodes, node_ids = [], set()
        for node in payload.get("nodes", []):
            node_id = node.get("knowledge_node_id", "")
            if (not re.fullmatch(r"KM-CH\d{2}-N\d{3}", node_id) or not node_id.startswith("KM-" + chapter_id.upper())
                    or node_id in node_ids):
                errors.append(f"{chapter_id}: invalid knowledge node ID {node_id}")
                continue
            node_ids.add(node_id)
            if node.get("review_status") not in STATUSES or not all(isinstance(node.get(key), str) and node[key].strip()
                                                                       for key in ("name", "category", "summary")):
                errors.append(f"{node_id}: incomplete knowledge node")
                continue
            refs = _refs(node.get("source_refs"), source_ids, chapter_id, errors, node_id)
            nodes.append({**node, "source_refs": refs})
        relations, relation_ids = [], set()
        for relation in payload.get("relations", []):
            relation_id = relation.get("knowledge_relation_id", "")
            if (not re.fullmatch(r"KM-CH\d{2}-R\d{3}", relation_id) or not relation_id.startswith("KM-" + chapter_id.upper())
                    or relation_id in relation_ids or relation.get("from_node_id") not in node_ids
                    or relation.get("to_node_id") not in node_ids or relation.get("type") not in RELATION_TYPES
                    or relation.get("review_status") not in STATUSES):
                errors.append(f"{chapter_id}: invalid knowledge relation {relation_id}")
                continue
            relation_ids.add(relation_id)
            refs = _refs(relation.get("source_refs"), source_ids, chapter_id, errors, relation_id)
            relations.append({**relation, "source_refs": refs})
        maps[chapter_id] = {**payload, "nodes": nodes, "relations": relations}
    return maps, ledger, errors


def _approved(item: dict, entity_type: str, ledger: dict):
    record = ledger.get((entity_type, item.get("knowledge_node_id") or item.get("knowledge_relation_id") or item.get("chapter_id")))
    return item.get("review_status") == "approved" and record and record["review_status"] == "approved"


def public_map(payload: dict | None, ledger: dict, documents: dict):
    """Expose only professionally approved nodes and traceable source references."""
    if not payload or not _approved(payload, "knowledge_map", ledger):
        return {"chapter_id": payload.get("chapter_id") if payload else "", "available": False,
                "message": "章节知识导图暂未发布。"}
    nodes = []
    for node in payload["nodes"]:
        if not _approved(node, "knowledge_node", ledger):
            continue
        refs = [ref for ref in node["source_refs"] if ref["source_locator"] and
                documents.get(ref["source_id"], {}).get("document_status") == "effective" and
                documents.get(ref["source_id"], {}).get("content_kind") in {"fulltext", "extracted"} and
                documents.get(ref["source_id"], {}).get("review_status") == "approved"]
        if refs:
            nodes.append({**node, "source_refs": refs})
    node_ids = {node["knowledge_node_id"] for node in nodes}
    relations = []
    for relation in payload["relations"]:
        if not _approved(relation, "knowledge_relation", ledger):
            continue
        refs = [ref for ref in relation["source_refs"] if ref["source_locator"] and
                documents.get(ref["source_id"], {}).get("document_status") == "effective" and
                documents.get(ref["source_id"], {}).get("content_kind") in {"fulltext", "extracted"} and
                documents.get(ref["source_id"], {}).get("review_status") == "approved"]
        if relation["from_node_id"] in node_ids and relation["to_node_id"] in node_ids and refs:
            relations.append({**relation, "source_refs": refs})
    if not nodes:
        return {"chapter_id": payload["chapter_id"], "available": False, "message": "章节知识导图暂未发布。"}
    return {"chapter_id": payload["chapter_id"], "title": payload.get("title", "章节知识导图"),
            "version": payload["version"], "available": True, "nodes": nodes, "relations": relations}


def node_context(payload: dict | None, node_id: str, ledger: dict, documents: dict):
    visible = public_map(payload, ledger, documents)
    if not visible.get("available"):
        return None
    node = next((item for item in visible["nodes"] if item["knowledge_node_id"] == node_id), None)
    if not node:
        return None
    related = [edge for edge in visible["relations"] if node_id in (edge["from_node_id"], edge["to_node_id"])]
    return {"node": node, "relations": related, "question_context": {
        "chapter_id": visible["chapter_id"], "knowledge_node_id": node_id, "name": node["name"],
        "allowed_sources": [{**ref, "canonical_id": documents[ref["source_id"]].get("canonical_id", "")}
                            for ref in node["source_refs"]]
    }}

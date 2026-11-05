"""Pending-review chapter graph from the existing fixed CSV interface.

Guide sections are navigation branches, not asserted regulatory relationships.
Only rows in relations.csv are presented as relationships.
"""
import csv
from pathlib import Path


def _rows(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def build_chapter_graph(root, chapter, documents):
    chapter_id = chapter["id"]
    folder = Path(root) / "data" / "chapters" / chapter_id
    sources = {item["source_id"]: item for item in documents if item["chapter_id"] == chapter_id}
    sections = [{"id": item["id"], "title": item["title"], "node_ids": []}
                for item in chapter.get("guide", {}).get("sections", [])]
    source_section = {}
    for section in chapter.get("guide", {}).get("sections", []):
        for ref in section["sources"]:
            source_id = ref if isinstance(ref, str) else ref["source_id"]
            source_section.setdefault(source_id, section["id"])
    if not sections:
        sections = [{"id": "all", "title": "本章节点", "node_ids": []}]
    section_by_id = {item["id"]: item for item in sections}
    nodes = []
    omitted = 0
    for row in _rows(folder / "nodes.csv"):
        source = sources.get(row["source_id"])
        if not source or not row["node_id"].startswith(chapter_id.upper() + "-N"):
            continue
        if source["document_status"] != "effective" or source["content_kind"] not in {"fulltext", "extracted"}:
            omitted += 1
            continue
        section_id = source_section.get(row["source_id"], "other")
        if section_id not in section_by_id:
            section_by_id[section_id] = {"id": section_id, "title": "其他关联节点", "node_ids": []}
            sections.append(section_by_id[section_id])
        node = {key: row[key] for key in ("node_id", "name", "code", "summary", "display_type",
                                               "source_id", "source_locator", "review_status")}
        node.update(section_id=section_id, source_kind=source["content_kind"],
                    source_status=source["document_status"])
        nodes.append(node)
        section_by_id[section_id]["node_ids"].append(row["node_id"])
    node_ids = {item["node_id"] for item in nodes}
    relations = []
    for row in _rows(folder / "relations.csv"):
        source = sources.get(row["source_id"])
        if (row["from_node_id"] not in node_ids or row["to_node_id"] not in node_ids or not source
                or source["document_status"] != "effective"
                or source["content_kind"] not in {"fulltext", "extracted"}):
            continue
        relation = {key: row[key] for key in ("relation_id", "from_node_id", "type",
                                                 "to_node_id", "source_id", "evidence", "review_status")}
        relation.update(source_kind=source["content_kind"], source_status=source["document_status"])
        relations.append(relation)
    return {"nodes": nodes, "relations": relations, "sections": sections, "omitted_nodes": omitted,
            "review_status": "pending", "navigation_note": "圆点来自节点表，连线仅来自关系表；请对照来源和证据核查。"}

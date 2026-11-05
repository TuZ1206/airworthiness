"""Future Neo4j export preparation; this module never connects to Neo4j."""
from __future__ import annotations

import json

from .catalog import connect


def approved_graph_payload(database):
    """Return explicitly namespaced, professionally approved graph records only.

    Callers may map this neutral payload to Neo4j later. Keeping the two graph
    vocabularies separate prevents a source-reference edge from being mistaken
    for an authored chapter-knowledge relationship.
    """
    with connect(database) as db:
        chapters = [json.loads(row[0]) for row in db.execute("SELECT payload FROM chapters ORDER BY id")]
        documents = {row["source_id"]: json.loads(row["payload"]) for row in
                     db.execute("SELECT source_id,payload FROM documents")}
        canonical = [json.loads(row[0]) for row in db.execute(
            "SELECT payload FROM canonical_documents WHERE review_status='approved' ORDER BY canonical_id")]
    eligible = {source_id for source_id, document in documents.items()
                if document["review_status"] == "approved" and document["document_status"] == "effective"
                and document["content_kind"] in {"fulltext", "extracted"}}
    source_nodes, source_relations, knowledge_nodes, knowledge_relations = [], [], [], []
    for chapter in chapters:
        graph = chapter.get("graph") or {}
        node_ids = set()
        for node in graph.get("nodes", []):
            if node.get("review_status") == "approved" and node.get("source_id") in eligible:
                source_nodes.append({"label": "SourceIndexNode", **node})
                node_ids.add(node["node_id"])
        for relation in graph.get("relations", []):
            if (relation.get("review_status") == "approved" and relation.get("source_id") in eligible and
                    relation.get("from_node_id") in node_ids and relation.get("to_node_id") in node_ids):
                source_relations.append({"namespace": "source_index", **relation})
        knowledge = chapter.get("knowledge_map") or {}
        if knowledge.get("available"):
            knowledge_nodes.extend({"label": "ChapterKnowledgeNode", **node} for node in knowledge.get("nodes", []))
            knowledge_relations.extend({"namespace": "chapter_knowledge", **relation}
                                       for relation in knowledge.get("relations", []))
    return {"canonical_documents": canonical, "source_index_nodes": source_nodes,
            "source_index_relations": source_relations, "knowledge_nodes": knowledge_nodes,
            "knowledge_relations": knowledge_relations}

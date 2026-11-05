"""Editable property navigation over the immutable chapter source records."""
import csv
from pathlib import Path


CATEGORIES = (
    ("strength", "强度与承载"),
    ("stiffness", "刚度与稳定性"),
    ("impact", "冲击与损伤"),
    ("fatigue", "疲劳与寿命"),
    ("environment", "环境适应性"),
    ("manufacturing", "制造与一致性"),
    ("general", "通用适航与管理流程"),
)
CATEGORY_IDS = {item[0] for item in CATEGORIES}
FIELDS = ("source_id", "property_id", "sort_order", "mapping_status", "mapping_note")


def load_property_index(root, documents):
    path = Path(root) / "data" / "property-index" / "source-map.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("property source-map.csv header mismatch")
        rows = list(reader)
    known = {item["source_id"] for item in documents}
    seen = set()
    assigned = set()
    for row in rows:
        sid = row["source_id"]
        key = (sid, row["property_id"])
        if key in seen or sid not in known or row["property_id"] not in CATEGORY_IDS:
            raise ValueError(f"invalid property mapping: {sid}")
        if row["mapping_status"] != "pending" or not row["sort_order"].isdigit():
            raise ValueError(f"invalid property review/order: {sid}")
        seen.add(key)
        assigned.add(sid)
    if assigned != known:
        raise ValueError(f"property mapping incomplete: {sorted(known - assigned)}")
    return sorted(rows, key=lambda x: (next(i for i, item in enumerate(CATEGORIES) if item[0] == x["property_id"]), int(x["sort_order"]), x["source_id"]))


def entity_mappings(root, source_rows):
    """Project source navigation onto nodes, relations and terms without editing them."""
    by_source = {}
    for row in source_rows:
        by_source.setdefault(row["source_id"], []).append(row["property_id"])
    result = []
    for chapter in sorted((Path(root) / "data/chapters").glob("ch[0-9][0-9]")):
        for filename, entity_type, id_field in (
            ("nodes.csv", "node", "node_id"),
            ("relations.csv", "relation", "relation_id"),
            ("glossary.csv", "term", "term_id"),
        ):
            with (chapter / filename).open(encoding="utf-8-sig", newline="") as handle:
                for item in csv.DictReader(handle):
                    sid = item["source_id"]
                    if sid not in by_source:
                        raise ValueError(f"property entity source missing: {entity_type} {item[id_field]}")
                    for prop in by_source[sid]:
                        result.append((entity_type, item[id_field], sid, prop, item["review_status"]))
    return result

"""One-time draft mapping; edit source-map.csv directly after professional review."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/property-index/source-map.csv"
BASE = {
    "ch01": "general", "ch02": "general", "ch03": "strength",
    "ch04": "manufacturing", "ch05": "general", "ch06": "manufacturing",
    "ch07": "strength", "ch08": "fatigue", "ch09": "strength",
}
EXTRA = {
    "CH03-S001": ("stiffness", "environment"),
    "CH03-S002": ("stiffness", "environment"),
    "CH04-S003": ("environment",),
    "CH07-S001": ("stiffness", "impact", "fatigue"),
    "CH07-S002": ("stiffness", "impact", "environment"),
    "CH08-S001": ("strength", "impact"),
    "CH08-S006": ("impact",),
    "CH09-S011": ("fatigue",),
}


def property_for(chapter, title):
    if chapter in {"ch01", "ch02", "ch05"}:
        return "general", "制度或审定流程资料；按原章节暂归通用入口"
    if chapter == "ch06":
        return "manufacturing", "质量体系与供应链资料；按原章节暂归制造入口"
    if chapter == "ch04":
        return "manufacturing", "制造工艺资料；按原章节暂归制造入口"
    if chapter == "ch08":
        return "fatigue", "疲劳与损伤容限资料；按原章节暂归疲劳入口"
    if "疲劳" in title:
        return "fatigue", "标题含疲劳；具体适用范围待核"
    if "冲击" in title or "损伤" in title:
        return "impact", "标题含冲击或损伤；具体适用范围待核"
    if "环境" in title or "高温" in title or "湿热" in title:
        return "environment", "标题含环境条件；具体适用范围待核"
    if "刚度" in title or "屈曲" in title:
        return "stiffness", "标题含刚度或稳定性；具体适用范围待核"
    return BASE[chapter], "按原章节主题暂归；须对照条款细化特性"


def main():
    if DEST.exists() and "--replace-draft" not in sys.argv:
        raise SystemExit(f"Refusing to overwrite reviewed mapping: {DEST}")
    if DEST.exists():
        with DEST.open(encoding="utf-8-sig", newline="") as handle:
            if any(row["mapping_status"] != "pending" for row in csv.DictReader(handle)):
                raise SystemExit("Refusing to overwrite reviewed mapping")
    rows = []
    for path in sorted((ROOT / "data/chapters").glob("ch*/sources.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for source in csv.DictReader(handle):
                prop, note = property_for(path.parent.name, source["title"])
                rows.append({"source_id": source["source_id"], "property_id": prop,
                             "sort_order": 0, "mapping_status": "pending", "mapping_note": note})
                for extra in EXTRA.get(source["source_id"], ()):
                    if extra != prop:
                        rows.append({"source_id": source["source_id"], "property_id": extra,
                                     "sort_order": 0, "mapping_status": "pending",
                                     "mapping_note": "跨特性资料入口；条款适用性待专业核验"})
    order = ["strength", "stiffness", "impact", "fatigue", "environment", "manufacturing", "general"]
    rows.sort(key=lambda row: (order.index(row["property_id"]), row["source_id"]))
    for index, row in enumerate(rows, 1):
        row["sort_order"] = index
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_id", "property_id", "sort_order", "mapping_status", "mapping_note"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Mapped {len(rows)} chapter sources to {len(order)} navigation sections")


if __name__ == "__main__":
    main()

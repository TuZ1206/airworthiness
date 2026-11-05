"""Render the property index into the local static review preview."""
import csv
import html
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".cache/property-preview"
NAMES = [
    ("strength", "强度与承载"), ("stiffness", "刚度与稳定性"),
    ("impact", "冲击与损伤"), ("fatigue", "疲劳与寿命"),
    ("environment", "环境适应性"), ("manufacturing", "制造与一致性"),
    ("general", "通用适航与管理流程"),
]


def main():
    with (ROOT / "data/property-index/source-map.csv").open(encoding="utf-8-sig", newline="") as f:
        mappings = list(csv.DictReader(f))
    sources = {}
    for path in (ROOT / "data/chapters").glob("ch*/sources.csv"):
        with path.open(encoding="utf-8-sig", newline="") as f:
            sources.update({r["source_id"]: r for r in csv.DictReader(f)})
    groups = defaultdict(list)
    for mapping in sorted(mappings, key=lambda r: int(r["sort_order"])):
        groups[mapping["property_id"]].append(sources[mapping["source_id"]])
    sections = ['<section class="wrap full-index"><div class="section-title"><div><p class="eyebrow">03 / COMPLETE INDEX</p><h2>九章来源 · 特性排序</h2></div><p>全部 189 条章节来源；归类待专业核验</p></div>']
    for index, (key, name) in enumerate(NAMES, 1):
        items = groups[key]
        sections.append('<details class="property-group" id="index-{}"{}><summary><span>{:02d}　{}</span><small>{} 条关联</small></summary><ol>'.format(key, ' open' if index == 1 else '', index, name, len(items)))
        for item in items:
            sid = html.escape(item["source_id"])
            chapter = sid[:4].lower()
            sections.append('<li><a href="/airworthiness/chapters/{}/?source={}"><span class="index-code">{}</span><span class="index-title">{}</span><span class="index-document">{}</span><span class="index-arrow">↗</span></a></li>'.format(chapter, sid, sid, html.escape(item["title"]), html.escape(item["document_code"])))
        sections.append('</ol></details>')
    sections.append('</section>')
    template = (ROOT / "src/airworthiness/web/templates/properties-preview.html").read_text(encoding="utf-8")
    template = re.sub(r"\{% if property_groups %\}.*\{% endif %\}", "\n".join(sections), template, flags=re.S)
    template = template.replace("{{ url_for('static', filename='properties-preview.css') }}", "properties-preview.css")
    template = template.replace('href="/chapters/', 'href="/airworthiness/chapters/').replace('href="/"', 'href="/airworthiness/"')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(template, encoding="utf-8")
    shutil.copyfile(ROOT / "src/airworthiness/web/static/properties-preview.css", OUT / "properties-preview.css")
    print("Property preview: {} unique sources, {} links".format(len(sources), len(mappings)))


if __name__ == "__main__":
    main()

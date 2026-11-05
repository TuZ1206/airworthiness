"""The chapter-end graph must remain a traceable, pending-review preview."""
import unittest
import shutil
import subprocess
import csv
import json
import re
from pathlib import Path

from airworthiness.chapter_graph import build_chapter_graph
from airworthiness.ingest import load_inputs


ROOT = Path(__file__).resolve().parents[1]


class ChapterGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chapters, cls.documents, _, cls.errors, _ = load_inputs(ROOT)

    def test_all_nine_chapters_have_traceable_nodes_and_relations(self):
        self.assertFalse(self.errors)
        self.assertEqual(len(self.chapters), 9)
        for chapter in self.chapters:
            with self.subTest(chapter=chapter["id"]):
                graph = build_chapter_graph(ROOT, chapter, self.documents)
                self.assertTrue(graph["nodes"])
                self.assertTrue(graph["relations"])
                ids = {node["node_id"] for node in graph["nodes"]}
                self.assertEqual(sum(len(section["node_ids"]) for section in graph["sections"]), len(ids))
                self.assertEqual(graph["review_status"], "pending")
                for node in graph["nodes"]:
                    self.assertTrue(node["source_locator"])
                    self.assertEqual(node["review_status"], "pending")
                    self.assertIn(node["source_kind"], {"fulltext", "extracted"})
                    self.assertEqual(node["source_status"], "effective")
                for relation in graph["relations"]:
                    self.assertIn(relation["from_node_id"], ids)
                    self.assertIn(relation["to_node_id"], ids)
                    self.assertTrue(relation["evidence"])
                    self.assertEqual(relation["review_status"], "pending")
                    self.assertIn(relation["source_kind"], {"fulltext", "extracted"})
                    self.assertEqual(relation["source_status"], "effective")

    def test_guide_branch_is_not_invented_as_a_relation(self):
        chapter = self.chapters[0]
        graph = build_chapter_graph(ROOT, chapter, self.documents)
        raw_relations = (ROOT / "data" / "chapters" / chapter["id"] / "relations.csv").read_text(encoding="utf-8-sig")
        self.assertTrue(all(edge["relation_id"] in raw_relations for edge in graph["relations"]))
        self.assertTrue(all(section["id"] not in {edge["type"] for edge in graph["relations"]}
                            for section in graph["sections"]))

    def test_visual_graph_uses_real_edges_and_bounded_nodes(self):
        if not shutil.which("node"):
            self.skipTest("Node.js unavailable")
        script = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\r?$/gm,'').replace(/^export .*;\r?$/gm,'');
const context={list:value=>Array.isArray(value)?value:[]};
vm.createContext(context); vm.runInContext(code,context);
const graph={nodes:['a','b','c','d','e'].map(node_id=>({node_id})),
  relations:[{from_node_id:'a',to_node_id:'b'},{from_node_id:'a',to_node_id:'c'},
    {from_node_id:'a',to_node_id:'d'},{from_node_id:'e',to_node_id:'missing'}],
  sections:[{id:'topic',node_ids:['a','b','c','d','e']}]};
const layout=context.layoutGraph(graph);
assert.equal(layout.points.size,5);
assert.equal(layout.edges.length,3);
assert.equal(layout.hubId,'a');
assert.ok([...layout.points.values()].every(p=>p.x>=96&&p.x<=layout.width-96));
assert.ok([...layout.points.values()].every(p=>p.y>=72&&p.y<=layout.height-72));
assert.ok(layout.width>=1000&&layout.height>=780);
"""
        path = ROOT / "src/airworthiness/web/static/hall-graph.js"
        result = subprocess.run([shutil.which("node"), "-e", script, str(path)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_relation_types_have_distinct_colors_and_matching_legend(self):
        script = (ROOT / "src/airworthiness/web/static/hall-graph.js").read_text(encoding="utf-8")
        css = (ROOT / "src/airworthiness/web/static/hall.css").read_text(encoding="utf-8")
        colors = dict(re.findall(r"([\u4e00-\u9fff]+): '(#[0-9a-f]{6})'", script))
        types = set()
        for chapter in self.chapters:
            path = ROOT / "data" / "chapters" / chapter["id"] / "relations.csv"
            with path.open(encoding="utf-8-sig", newline="") as source:
                types.update(row["type"] for row in csv.DictReader(source))
        self.assertTrue(types <= colors.keys(), types - colors.keys())
        self.assertEqual(len(colors), len(set(colors.values())))
        self.assertIn("line.style.setProperty('--relation-color', relationColor(edge.type))", script)
        self.assertIn("relationLegend", script)
        self.assertIn("stroke: var(--relation-color", css)
        self.assertNotRegex(css, r"\.graph-relation-line\.is-active\s*\{[^}]*stroke:")

    def test_group_outlines_do_not_overlap_in_any_chapter(self):
        if not shutil.which("node"):
            self.skipTest("Node.js unavailable")
        graphs = [build_chapter_graph(ROOT, chapter, self.documents) for chapter in self.chapters]
        script = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\r?$/gm,'').replace(/^export .*;\r?$/gm,'');
const context={list:value=>Array.isArray(value)?value:[]};
vm.createContext(context); vm.runInContext(code,context);
const {groupFor,clusterOutline}=vm.runInContext('({groupFor,clusterOutline})',context);
for (const [chapterIndex,graph] of JSON.parse(fs.readFileSync(0,'utf8')).entries()) {
  const layout=context.layoutGraph(graph), groups=new Map();
  assert.equal(layout.points.size,graph.nodes.length);
  for (const node of graph.nodes) {
    const group=groupFor(node);
    if (!groups.has(group)) groups.set(group,[]);
    groups.get(group).push(layout.points.get(node.node_id));
  }
  const outlines=[...groups].map(([group,points])=>({group,...clusterOutline(points).bounds}));
  for (let i=0;i<outlines.length;i++) for (let j=i+1;j<outlines.length;j++) {
    const a=outlines[i],b=outlines[j];
    assert.ok(a.right<b.left||b.right<a.left||a.bottom<b.top||b.bottom<a.top,
      `chapter ${chapterIndex+1}: ${a.group} overlaps ${b.group}`);
  }
}
"""
        path = ROOT / "src/airworthiness/web/static/hall-graph.js"
        result = subprocess.run([shutil.which("node"), "-e", script, str(path)],
                                input=json.dumps(graphs, ensure_ascii=False), capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

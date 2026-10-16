"""Reader/SQLite integration using isolated inputs; repository CSVs stay immutable."""
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from airworthiness import catalog, ingest
from airworthiness.app import create_app
from airworthiness.locators import resolve_terms
from airworthiness.reading import render_document

ROOT = Path(__file__).resolve().parents[1]
QUOTE = "民用航空器必须具有民航局颁发的适航证，方可飞行。"
LOSS_NOTE = "图片与公式未完整提取，不得据此推断原文。"
GLOSSARY_FIELDS = "term_id,term,aliases,definition,group,has_page,anchor_or_url,related_node_id,source_id,review_status,quote".split(",")


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_inputs(root, alias=False):
    chapter = root / "data/chapters/ch01"
    (chapter / "documents").mkdir(parents=True)
    (root / "data/chapters/catalog.json").write_text(json.dumps([
        dict(id="ch01", title="测试章", description="仅测试定位", topics=[])
    ]), encoding="utf-8")
    rows = []
    for number in range(1, 4):
        source_id = f"CH01-S{number:03}"
        raw = "# 来源\n\n## 摘录\n\n当前仅有整理内容。"
        path = chapter / "documents" / f"{source_id}.md"
        path.write_text(raw, encoding="utf-8")
        url = "https://www.caac.gov.cn/" + ("alias" if number == 2 and alias else "other" if number == 3 else "canonical") + ".html"
        rows.append(dict(source_id=source_id, title="测试来源", document_code=f"TEST-{number}",
                         document_status="effective", publish_date="2026-01-01", url=url,
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest(), crawled_at="2026-01-02", review_status="pending"))
    write_csv(chapter / "sources.csv", ingest.SOURCE_FIELDS, rows)
    terms = []
    for number, (term, source, quote) in enumerate((("适航证", "CH01-S002", ""), ("外部术语", "CH01-S003", ""), ("适航证", "CH01-S001", QUOTE)), 1):
        terms.append(dict(term_id=f"CH01-T{number:03}", term=term, aliases="", definition="编辑释义，未经核验。",
                          group="测试", has_page="true", anchor_or_url=f"#original-{number}", related_node_id="",
                          source_id=source, review_status="pending", quote=quote))
    write_csv(chapter / "glossary.csv", GLOSSARY_FIELDS, terms)
    acquired = root / "data/acquired/documents"
    acquired.mkdir(parents=True)
    body = "## 正文\n\n## 第 1 页\n\n第九条 适航证\n\n" + QUOTE + "\n\n外部术语只出现在这份来源。\n\n" + "原文内容。" * 1500
    saved = acquired / "source.md"
    saved.write_text(body, encoding="utf-8")
    entry = dict(path="data/acquired/documents/source.md", content_kind="extracted", note=LOSS_NOTE,
                 source_sha256=rows[0]["sha256"], landing_url=rows[0]["url"], url=rows[0]["url"],
                 sha256=hashlib.sha256(saved.read_bytes()).hexdigest(), method="test-fixture")
    (root / "data/acquired/manifest.json").write_text(json.dumps({rows[0]["source_id"]: entry}), encoding="utf-8")
    return terms


def save_findings(root, findings):
    path = root / "data/verification/metadata-findings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(schema_version="1.2", findings=findings)), encoding="utf-8")


def code_finding(number, **updates):
    sid = f"CH01-S{number:03}"
    url = f"https://www.caac.gov.cn/{'other' if number == 3 else 'canonical'}.html"
    finding = dict(finding_id=f"CODE-{number}", source_ids=[sid], field="document_code",
                   old_values={sid: f"TEST-{number}"}, verified_value="TEST-1",
                   source_urls={sid: url}, result="verified", resolution="corrected",
                   evidence_url=[url], evidence=dict(type="paraphrase", text="官方页面载明测试文号。"),
                   checked_at="2026-10-13T09:00:00Z")
    return {**finding, **updates}


class LocatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.original_terms = make_inputs(self.root)
        self.db = self.root / "catalog.sqlite3"

    def test_resolves_against_shared_body_without_changing_csv_evidence(self):
        paths = list((self.root / "data").rglob("*.csv"))
        before = {path: path.read_bytes() for path in paths}
        _, docs, terms, errors, _ = ingest.load_inputs(self.root)
        self.assertEqual(errors, [])
        target = next(doc for doc in docs if doc["source_id"] == "CH01-S002")
        self.assertEqual(target["reused_from"], "CH01-S001")
        self.assertIn(LOSS_NOTE, target["extraction_note"])
        by_id = {term["term_id"]: term for term in terms}
        matched = by_id["CH01-T001"]
        self.assertEqual(matched["locator_status"], "text_match")
        self.assertEqual(matched["anchor_or_url"], "/chapters/ch01?source=CH01-S002#clause-9")
        self.assertEqual(by_id["CH01-T002"]["locator_status"], "source_only")
        self.assertEqual(by_id["CH01-T003"]["locator_status"], "verified_clause")
        for original in self.original_terms:
            term = by_id[original["term_id"]]
            self.assertEqual(term["original_anchor_or_url"], original["anchor_or_url"])
            self.assertEqual(term["original_has_page"], original["has_page"])
            self.assertFalse(term["definition_verified"])
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_metadata_runs_before_sharing_and_preserves_resolved_issue_records(self):
        save_findings(self.root, [code_finding(2)])
        share = ingest.share_originals
        def checked_share(documents):
            target = next(doc for doc in documents if doc["source_id"] == "CH01-S002")
            self.assertEqual(target["document_code"], "TEST-1")
            self.assertEqual(target["content_kind"], "excerpt")
            self.assertEqual(target["metadata_verification"][0]["application"], "corrected")
            share(documents)
        with patch.object(ingest, "share_originals", side_effect=checked_share) as sharing:
            _, docs, terms, errors, issues = ingest.load_inputs(self.root)
        sharing.assert_called_once()
        target = next(doc for doc in docs if doc["source_id"] == "CH01-S002")
        self.assertEqual(errors, [])
        self.assertEqual(target.get("reused_from"), "CH01-S001")
        self.assertEqual(target["metadata_verification"][0]["resolution"], "corrected")
        self.assertEqual(target["original_metadata"]["document_code"], "TEST-2")
        self.assertEqual([(i["source_id"], i["kind"]) for i in issues], [("CH01-S001", "code_conflict")])
        self.assertEqual(terms[0]["locator_status"], "text_match")

    def test_editorial_metadata_and_excerpt_never_supply_original_text_evidence(self):
        folder = self.root / 'data/chapters/ch01'
        source = folder / 'documents/CH01-S003.md'
        quote = '外部术语仅用于编辑整理说明，并非来源原文。'
        for kind, heading in (('metadata', '仅登记'), ('excerpt', '整理摘录')):
            source.write_text(f'# 来源\n\n## {heading}\n\n第六条 编辑标题\n\n{quote}', encoding='utf-8')
            rows = ingest.read_csv(folder / 'sources.csv')
            rows[2]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            write_csv(folder / 'sources.csv', ingest.SOURCE_FIELDS, rows)
            for exact in (False, True):
                with self.subTest(kind=kind, exact_quote=exact):
                    terms = [dict(term) for term in self.original_terms]
                    terms[1]['quote'] = quote if exact else ''
                    write_csv(folder / 'glossary.csv', GLOSSARY_FIELDS, terms)
                    _, docs, located, errors, _ = ingest.load_inputs(self.root)
                    self.assertEqual(errors, [])
                    doc = next(doc for doc in docs if doc['source_id'] == 'CH01-S003')
                    self.assertEqual(doc['content_kind'], kind)
                    self.assertIn(quote, doc['body'])
                    term = next(term for term in located if term['source_id'] == doc['source_id'])
                    self.assertEqual(term['locator_status'], 'source_only')
                    self.assertEqual(term['locator_evidence'], '')
                    self.assertEqual(term['locator_anchor'], '')
                    self.assertEqual(term['has_page'], 'false')
                    self.assertEqual(term['original_has_page'], 'true')
                    self.assertEqual(term['original_anchor_or_url'], '#original-2')
                    self.assertFalse(term['definition_verified'])

    def test_originals_and_archive_member_survive_sharing_and_sqlite(self):
        path = self.root / "data/acquired/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        fields = dict(originals=[
            dict(label="主文（434页）", url="https://www.caac.gov.cn/main.pdf", original_sha256="1" * 64),
            dict(label="附录（82页）", url="https://www.caac.gov.cn/appendix.pdf", original_sha256="2" * 64)],
            archive_member="AP21R2.pdf", archive_member_sha256="3" * 64)
        manifest["CH01-S001"].update(fields)
        body = "## 正文\n\n## 主文\n\n## 第1页\n\n第六条 总则\n\n" + QUOTE + "\n\n## 附录\n\n## 第1页\n\n附录原文。"
        saved = self.root / manifest["CH01-S001"]["path"]
        saved.write_text(body, encoding="utf-8")
        manifest["CH01-S001"]["sha256"] = hashlib.sha256(saved.read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        catalog.build_catalog(self.root, self.db)
        for sid in ("CH01-S001", "CH01-S002"):
            doc = catalog.document(self.db, sid)
            self.assertEqual({key: doc["body_provenance"].get(key) for key in fields}, fields)
            self.assertIn("主文", doc["html"])
            self.assertIn("附录原文。", doc["html"])
            self.assertEqual([item["id"] for item in doc["toc"] if item["kind"] == "page"],
                             ["page-1", "page-1--2"])
            self.assertEqual(doc["review_status"], "pending")
            self.assertIn(LOSS_NOTE, doc["extraction_note"])

    def test_resolved_original_issue_is_persisted_and_exposed_separately(self):
        _, _, _, _, before = ingest.load_inputs(self.root)
        original = next(issue for issue in before if issue["source_id"] == "CH01-S002")
        save_findings(self.root, [code_finding(2)])
        app = create_app(dict(TESTING=True, DATA_ROOT=self.root, DATABASE=self.db))
        client = app.test_client()
        doc = client.get("/api/documents/CH01-S002").get_json()
        self.assertIsInstance(doc.get("resolved_issues"), list)
        self.assertEqual(len(doc["resolved_issues"]), 1)
        resolved = doc["resolved_issues"][0]
        self.assertEqual({key: resolved[key] for key in original}, original)
        self.assertEqual(resolved["resolution"], "corrected")
        self.assertEqual(resolved["finding_ids"], ["CODE-2"])
        self.assertEqual(resolved["evidence"], doc["metadata_verification"])
        self.assertEqual(doc["review_status"], "pending")
        with catalog.connect(self.db) as db:
            payload = json.loads(db.execute("SELECT payload FROM documents WHERE source_id=?",
                                            (doc["source_id"],)).fetchone()[0])
        self.assertEqual(payload["resolved_issues"], doc["resolved_issues"])
        quality = client.get("/api/quality").get_json()
        self.assertEqual(quality.get("resolved_issues"), [resolved])
        self.assertEqual([issue["source_id"] for issue in quality["issues"]], ["CH01-S001"])
        self.assertEqual(quality["resolved_metadata"], doc["metadata_verification"])
        self.assertEqual(catalog.document(self.db, "CH01-S001")["resolved_issues"], [])

    def test_sqlite_and_api_keep_locator_targets_notes_and_metadata(self):
        save_findings(self.root, [code_finding(number) for number in range(1, 4)] + [
            code_finding(2, finding_id="BLOCKED", evidence_url=[]),
            code_finding(2, finding_id="UNRESOLVED", result="unresolved", resolution="unresolved"),
            code_finding(2, finding_id="RECORDED", resolution="recorded")])
        app = create_app(dict(TESTING=True, DATA_ROOT=self.root, DATABASE=self.db))
        client = app.test_client()
        doc = client.get("/api/documents/CH01-S002").get_json()
        self.assertEqual(doc["glossary"][0]["locator_status"], "text_match")
        self.assertEqual([entry["application"] for entry in doc["metadata_verification"]],
                         ["corrected", "blocked", "unresolved", "recorded"])
        soup = BeautifulSoup(doc["html"], "html.parser")
        for term in doc["glossary"]:
            self.assertIsNotNone(soup.find(id=term["locator_anchor"]))
            self.assertIn(term["locator_evidence"], QUOTE)
        self.assertIn(LOSS_NOTE, doc["extraction_note"])
        self.assertIn("自动", doc.get("navigation_note", ""))
        self.assertIn("不代表原文条款", doc.get("navigation_note", ""))
        self.assertIn("明确编号", doc.get("navigation_note", ""))
        chapter = client.get("/api/chapters/ch01").get_json()
        self.assertEqual(chapter["glossary"][0], doc["glossary"][0])
        quality = client.get("/api/quality").get_json()
        self.assertEqual({item["source_id"] for item in quality.get("resolved_metadata", [])},
                         {"CH01-S001", "CH01-S002", "CH01-S003"})
        self.assertEqual({item["finding_id"] for item in quality["resolved_metadata"]},
                         {"CODE-1", "CODE-2", "CODE-3"})
        self.assertEqual(quality["issues"], [])

    def test_fingerprint_includes_nested_verification_content_even_with_same_stat(self):
        baseline = catalog.input_fingerprint(self.root)
        directory = self.root / "data/verification/evidence"
        directory.mkdir(parents=True)
        path = directory / "nested.json"
        path.write_text('{"value":1}', encoding="utf-8")
        added = catalog.input_fingerprint(self.root)
        self.assertNotEqual(baseline, added)
        stat = path.stat()
        path.write_text('{"value":2}', encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertNotEqual(added, catalog.input_fingerprint(self.root))
        path.unlink()
        self.assertEqual(baseline, catalog.input_fingerprint(self.root))

    def test_fingerprint_includes_locator_and_optional_verification_implementation(self):
        modules = self.root / "modules"
        modules.mkdir()
        for name in ("catalog", "ingest", "reading", "locators"):
            (modules / f"{name}.py").write_text("# version 1", encoding="utf-8")
        with patch.object(catalog, "__file__", str(modules / "catalog.py")):
            first = catalog.input_fingerprint(self.root)
            (modules / "locators.py").write_text("# version 2", encoding="utf-8")
            second = catalog.input_fingerprint(self.root)
            self.assertNotEqual(first, second)
            (modules / "verification.py").write_text("# available now", encoding="utf-8")
            self.assertNotEqual(second, catalog.input_fingerprint(self.root))


class ClauseBoundaryRegressionTests(unittest.TestCase):
    def test_unpromoted_standalone_article_never_inherits_previous_clause(self):
        for extracted in (False, True):
            for gap in ("\n", "\n\n"):
                with self.subTest(extracted=extracted, gap=repr(gap)):
                    body = "第六条 总则\n上一条的正文尚未留空行。\n第七条" + gap + QUOTE
                    term = dict(term="适航证", quote=QUOTE)
                    result = resolve_terms([term], body, extracted=extracted)[0]
                    self.assertNotEqual(result["locator_anchor"], "clause-6")
                    if result["locator_status"] == "verified_clause":
                        self.assertEqual(result["locator_anchor"], "clause-7")
                    else:
                        self.assertEqual(result["locator_status"], "text_match")
                    html, _ = render_document(body, extracted=extracted)
                    self.assertIsNotNone(BeautifulSoup(html, "html.parser").find(id=result["locator_anchor"]))
                    self.assertIn(result["locator_evidence"], body)

    def test_ambiguous_table_article_clears_scope_for_later_paragraphs(self):
        body = "第六条 总则\n\n条款号\n专业\n9\n第25.181条\n操稳\n6\n\n" + QUOTE
        result = resolve_terms([dict(term="适航证", quote=QUOTE)], body, extracted=True)[0]
        self.assertEqual(result["locator_status"], "text_match")
        self.assertTrue(result["locator_anchor"].startswith("paragraph-"))


class ReaderJavascriptTests(unittest.TestCase):
    def run_js(self, check):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required to run reader navigation checks")
        source = (ROOT / "src/airworthiness/web/static/hall-reader.js").read_text(encoding="utf-8")
        # Execute the real reader functions. Only browser primitives/imports are supplied.
        prelude = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8').replace(/^import .*;\r?$/gm, '').replace(/^export .*;\r?$/gm, '');
const location = {origin:'http://localhost', href:'http://localhost/chapters/ch01?source=CH01-S002', hash:'', search:''};
function el(tag, attrs={}, ...children) {
  return {tag, attrs, value:'', children:children.flat(Infinity).filter(x=>x!=null),
    append(...xs) { this.children.push(...xs); },
    replaceChildren(...xs) { this.children=xs; }, addEventListener() {},
    get textContent() { return this.children.map(x=>typeof x==='object' ? x.textContent : String(x)).join(''); },
    set textContent(value) { this.children=[value]; }};
}
const list = x=>Array.isArray(x)?x:[];
const chapterURL = (chapter, source)=>`/chapters/${chapter}?source=${source}`;
const sourceChapter = (source, fallback)=>/^CH\d{2}-/.test(source)?source.slice(0,4).toLowerCase():fallback;
const link = (text, href, attrs={})=>el('a', {href, ...attrs}, text);
const context = {URL, location, el, list, chapterURL, sourceChapter, link, reviewLabel:()=> '待专业审核',
  document:{getElementById:()=>null}, kinds:{extracted:'提取正文'}, state:{}, mobile:{matches:false}};
vm.createContext(context);
vm.runInContext(source, context);
const core = fs.readFileSync(process.argv[1], 'utf8');
vm.runInContext(core.slice(core.indexOf('function safeURL('), core.indexOf('\nfunction badge(')), context);
function walk(node) { return [node, ...node.children.flatMap(x=>typeof x==='object'?walk(x):[])]; }
"""
        result = subprocess.run([node, "-e", prelude + check, str(ROOT / "src/airworthiness/web/static/hall-core.js")], input=source, text=True,
                                encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_raw_and_prefixed_fragments_find_actual_reader_ids(self):
        self.run_js(r"""
const target = {id:'reading-clause-9'};
context.document.getElementById=id=>id===target.id?target:null;
location.hash='#clause-9'; assert.equal(context.hashTarget(), target);
location.hash='#reading-clause-9'; assert.equal(context.hashTarget(), target);
location.hash='#%ZZ'; assert.equal(context.hashTarget(), null);
""")

    def test_canonical_chapter_redirect_preserves_exact_fragment(self):
        self.run_js(r"""
location.search='?source=CH02-S002'; location.hash='#reading-clause-9';
Object.assign(context, {URLSearchParams, main:el('main'), loading:()=>el('p'),
  overview:async()=>({chapters:[]}), renderRail(){},
  record:async(_cache, id)=>id==='ch01'?{id}:{source_id:id, chapter_id:'ch02'}});
context.state={generation:1, disposers:[]};
context.mobile.addEventListener=()=>{};
let target;
context.navigate=(url, options)=>{target=url; assert.equal(options.replace, true);};
context.renderReader('ch01', {aborted:false}, 1).then(()=>{
  assert.equal(target, '/chapters/ch02?source=CH02-S002#reading-clause-9');
}).catch(error=>{console.error(error); process.exitCode=1;});
""")

    def test_glossary_uses_real_location_and_explains_keyword_evidence(self):
        self.run_js(r"""
const root=el('div');
context.renderGlossary(root, [{term:'适航证', definition:'编辑释义', source_id:'CH01-S002',
  locator_status:'text_match', locator_anchor:'clause-9', locator_evidence:'原文 <script> 不执行',
  anchor_or_url:'/chapters/ch01?source=CH01-S002#clause-9'}], {id:'ch01'});
const target=walk(root).find(x=>x.tag==='a');
assert.equal(target.attrs.href, '/chapters/ch01?source=CH01-S002#reading-clause-9');
assert.match(root.textContent, /关键词/); assert.match(root.textContent, /未核验.*释义/);
assert.match(root.textContent, /原文 <script> 不执行/);
assert.equal(walk(root).some(x=>x.tag==='script'), false);
""")

    def test_source_only_ignores_old_csv_fragment(self):
        self.run_js(r"""
const root=el('div');
context.renderGlossary(root, [{term:'术语', source_id:'CH01-S002', locator_status:'source_only',
  anchor_or_url:'#invented', original_anchor_or_url:'#invented'}], {id:'ch01'});
assert.equal(walk(root).find(x=>x.tag==='a').attrs.href, '/chapters/ch01?source=CH01-S002');
assert.match(root.textContent, /仅定位来源/);
""")

    def test_reader_shows_navigation_note_without_losing_extraction_limit(self):
        self.run_js(r"""
const notice=context.documentNotice({content_kind:'extracted', extraction_note:'图片公式缺失说明',
  navigation_note:'自动阅读分段不代表原文条款'});
assert.match(notice.textContent, /图片公式缺失说明/);
assert.match(notice.textContent, /自动阅读分段不代表原文条款/);
""")

    def test_local_pdf_button_uses_fixed_same_origin_endpoint_and_new_tab(self):
        self.run_js(r"""
const doc={source_id:'CH01-S002', original_available:true, original_url:'/api/documents/CH01-S002/original'};
const box=context.provenanceDetails(doc);
const anchor=walk(box).find(x=>x.tag==='a');
assert.ok(anchor, 'Missing local PDF button');
assert.equal(anchor.attrs.href, doc.original_url);
assert.equal(anchor.attrs.target, '_blank');
assert.match(anchor.attrs.rel, /noopener/);
assert.equal(anchor.attrs['data-route'], undefined);
assert.match(box.textContent, /本地.*PDF/); assert.match(box.textContent, /对照.*图表|图表.*对照/);
""")

    def test_pdf_button_rejects_external_urls_and_unavailable_originals(self):
        self.run_js(r"""
for(const [available, url] of [[true,'https://example.com/file.pdf'], [true,'//example.com/a'],
  [true,'/api/documents/CH09-S999/original'], [true,'javascript:alert(1)'],
  [false,'/api/documents/CH01-S002/original']]) {
  const box=context.provenanceDetails({source_id:'CH01-S002', original_available:available, original_url:url});
  assert.equal(walk(box).filter(x=>x.tag==='a').length, 0);
}
""")

    def test_originals_list_keeps_main_and_appendix_buttons_and_rejects_bad_urls(self):
        self.run_js(r"""
const base='/api/documents/CH01-S002/original';
const originals=[{label:'主文（434页）',url:base},{label:'附录（82页）<script>',url:base+'?index=1'},
  {label:'外站',url:'https://evil.test/file.pdf'}, {url:base+'?index=-1'},
  {url:base+'?index=1&redirect=https://evil.test'}, {url:base+'?index=NaN'},
  {url:'/api/documents/CH02-S002/original?index=1'}, null];
const doc={source_id:'CH01-S002',original_available:true,original_url:base,originals};
const box=context.provenanceDetails(doc);
const anchors=walk(box).filter(x=>x.tag==='a');
assert.equal(anchors.length,2);
assert.equal(anchors[0].attrs.href,base); assert.match(anchors[0].textContent,/主文/);
assert.equal(anchors[1].attrs.href,base+'?index=1'); assert.match(anchors[1].textContent,/附录/);
for(const a of anchors) {assert.equal(a.attrs.target,'_blank');assert.match(a.attrs.rel,/noopener/);}
assert.equal(walk(box).some(x=>x.tag==='script'),false);
doc.original_available=false;
assert.equal(walk(context.provenanceDetails(doc)).filter(x=>x.tag==='a').length,0);
""")

    def test_appendix_only_available_still_shows_pdf_and_missing_text_notice(self):
        self.run_js(r"""
const url='/api/documents/CH01-S002/original?index=1';
for(const originals of [undefined,[],[{label:'附录',url}]]) {
  const doc={source_id:'CH01-S002',content_kind:'metadata',original_available:true,original_url:url,originals};
  assert.equal(walk(context.provenanceDetails(doc)).find(x=>x.tag==='a')?.attrs.href,url);
  assert.match(context.documentNotice(doc).textContent,/暂缺可检索文字/);
}
""")

    def test_metadata_with_original_explains_missing_searchable_text(self):
        self.run_js(r"""
const notice=context.documentNotice({source_id:'CH01-S002', content_kind:'metadata', original_available:true,
  original_url:'/api/documents/CH01-S002/original', extraction_note:'扫描页面需对照'});
assert.match(notice.textContent, /暂缺可检索文字/);
assert.match(notice.textContent, /PDF/); assert.match(notice.textContent, /扫描页面需对照/);
""")

    def test_provenance_shows_metadata_changes_and_official_evidence_without_approval(self):
        self.run_js(r"""
const doc={source_id:'CH01-S002', review_status:'pending', metadata_verification:[
  {field:'title',original_value:'原题名<script>',verified_value:'官方题名',application:'corrected',
   evidence_url:['https://www.caac.gov.cn/title.html','javascript:alert(1)','https://gov.cn.evil.test/a']},
  {field:'publish_date',original_value:'2011-11-07',verified_value:'2016-03-17',application:'corrected',
   evidence_url:['https://www.gov.cn/date.html','https://user@www.gov.cn/a']}]};
const before=JSON.stringify(doc), box=context.provenanceDetails(doc);
assert.match(box.textContent,/元数据核对记录/);
assert.match(box.textContent,/题名.*原题名<script> → 官方题名/);
assert.match(box.textContent,/发布日期.*2011-11-07 → 2016-03-17/);
assert.match(box.textContent,/已纠正/); assert.match(box.textContent,/不改变专业审核状态.*待专业审核/);
const anchors=walk(box).filter(x=>x.tag==='a');
assert.deepEqual(anchors.map(x=>x.attrs.href),['https://www.caac.gov.cn/title.html','https://www.gov.cn/date.html']);
for(const a of anchors) {assert.equal(a.attrs.target,'_blank');assert.match(a.attrs.rel,/noopener/);}
assert.equal(walk(box).some(x=>x.tag==='script'),false);
assert.equal(JSON.stringify(doc),before);
""")

    def test_nonapplied_metadata_never_presents_candidate_as_a_change(self):
        self.run_js(r"""
for(const [application,status] of [['explained','差异已解释'],['blocked','未应用'],
  ['unresolved','未解决'],['recorded','仅记录']]) {
  const doc={source_id:'CH01-S002',review_status:'pending',metadata_verification:[null,
    {field:'document_code',original_value:'原文号',verified_value:'核对文号',application,evidence_url:[]}]};
  const box=context.provenanceDetails(doc);
  assert.match(box.textContent,/文件文号.*原文号.*原值保留.*核对文号/);
  assert.ok(box.textContent.includes(status)); assert.equal(box.textContent.includes('原文号 → 核对文号'),false);
  assert.equal(doc.review_status,'pending');
}
""")


if __name__ == "__main__":
    unittest.main()

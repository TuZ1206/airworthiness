"""Reading presentation must not turn source layout artifacts into typography."""
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'src/airworthiness/web/static'


class ReaderLayoutTests(unittest.TestCase):
    def run_js(self, filename, check):
        self.assertTrue((STATIC / filename).is_file(), f'Missing reader module: {filename}')
        runner = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync(process.argv[1], 'utf8')
 .replace(/^import .*;\r?$/gm, '').replace(/^export .*;\r?$/gm, '');
const context = {URL, URLSearchParams};
vm.createContext(context); vm.runInContext(code, context);
"""
        result = subprocess.run([shutil.which('node'), '-e', runner + check, str(STATIC / filename)],
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_and_directory_labels_are_not_large_body_headings(self):
        self.run_js('hall-content.js', r"""
assert.equal(typeof context.readingPresentation, 'function', 'Missing presentation classification');
assert.equal(context.readingPresentation('h2', 'reading-page-1', '第 1 页', false).className, 'source-page-label');
assert.equal(context.readingPresentation('h2', 'reading-toc-chapter-2', '第二章 民用航空器', false).className, 'source-directory-heading');
assert.equal(context.readingPresentation('h3', 'reading-clause-25', '第二十五条', false).className, '');
""")

    def test_web_directory_and_enumerated_lines_remain_vertical(self):
        self.run_js('hall-content.js', r"""
assert.equal(typeof context.readingPresentation, 'function', 'Missing line presentation');
for (const raw of ['第一节　民用航空器国籍 \n　　　　第二节　民用航空器权利 \n　　　　第三节　民用航空器适航管理 ',
 '(一) 第一项；\n　　(二) 第二项。\n　　其余按原文执行。']) {
 const result = context.readingPresentation('p', 'reading-paragraph-123', raw, false);
 assert.equal(result.className, 'source-lines');
 assert.equal(result.lines.length, 3);
 assert.equal(result.lines.join('').replace(/\s/g,''), raw.replace(/\s/g,''));
 assert.ok(result.lines.every(line=>line===line.trim()));
}
assert.equal(context.readingPresentation('pre', 'code', 'a\n b', false).lines, undefined);
assert.equal(context.readingPresentation('p', 'raw', '中国\n民航', true).className, 'extracted-block');
""")

    def test_pdf_default_and_search_anchor_override(self):
        self.run_js('hall-document-view.js', r"""
const doc={source_id:'CH02-S006', content_kind:'extracted'};
const originals=[{url:'/api/documents/CH02-S006/original',label:'原件'}];
assert.equal(context.initialDocumentMode(doc, originals), 'original');
assert.equal(context.initialDocumentMode(doc, originals, {search:'设计'}), 'text');
assert.equal(context.initialDocumentMode(doc, originals, {hash:'#reading-clause-1'}), 'text');
assert.equal(context.initialDocumentMode(doc, []), 'text');
assert.equal(context.initialDocumentMode({...doc, content_kind:'fulltext'}, originals), 'text');
assert.equal(context.initialDocumentMode({...doc, content_kind:'metadata'}, originals), 'original');
""")

    def test_only_fixed_local_original_urls_can_enter_pdf_frame(self):
        self.run_js('hall-document-view.js', r"""
const source='CH02-S006', good='/api/documents/CH02-S006/original';
assert.equal(context.isOriginalPath(source, good),true);
assert.equal(context.isOriginalPath(source, good+'?index=1'),true);
for(const path of ['//evil.test/pdf','https://evil.test/pdf','javascript:alert(1)',
 '/api/documents/CH02-S007/original',good+'?index=-1',good+'?index=1&redirect=x',good+'/../evil']) {
 assert.equal(context.isOriginalPath(source,path),false,path);
}
assert.equal(context.isOriginalPath('../secret',good),false);
""")

    def test_pages_pdf_paths_are_separate_and_official_links_are_not_iframes(self):
        self.run_js('hall-document-view.js', r"""
assert.equal(typeof context.isStaticOriginalPath,'function');
const base='/airworthiness', good=base+'/originals/CH02-S006/0.pdf';
assert.equal(context.isStaticOriginalPath('CH02-S006',good,base),true);
for(const path of [good+'?redirect=evil',good+'/../x','https://evil.test/x.pdf',
 '//evil.test/x.pdf','/originals/CH02-S006/0.pdf',base+'/originals/CH02-S007/0.pdf']) {
 assert.equal(context.isStaticOriginalPath('CH02-S006',path,base),false,path);
}
const doc={source_id:'CH02-S006',content_kind:'extracted',deployment_mode:'static',
 body_provenance:{url:'https://www.caac.gov.cn/document.pdf',originals:[
 {url:'https://www.caac.gov.cn/document.pdf',label:'主文'},
 {url:'javascript:alert(1)'},{url:'https://evil.test/test.pdf'}]}};
assert.equal(context.officialPDFs(doc).length,1);
assert.equal(context.initialDocumentMode(doc,[{url:good}],{base}), 'original');
assert.equal(context.initialDocumentMode({...doc,deployment_mode:'offline'},[{url:good}],{base}), 'text');
assert.equal(context.initialDocumentMode(doc,[{url:'https://www.caac.gov.cn/document.pdf'}],{base}), 'text');
""")


if __name__ == '__main__':
    unittest.main()

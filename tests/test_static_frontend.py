"""Behavioral tests for the Pages adapter without a backend or DOM library."""
import shutil
import subprocess
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'src/airworthiness/web/static'


class StaticFrontendTests(unittest.TestCase):
    def run_js(self, check):
        path = STATIC / 'hall-static.js'
        self.assertTrue(path.is_file(), 'Static browser adapter is not implemented')
        runner = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const context={URL,URLSearchParams,Map,Set,AbortController,DOMException,Response,Blob,
 DecompressionStream,TextDecoder,setTimeout,clearTimeout};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8').replace(/^export .*;$/gm,''),context);
"""
        result = subprocess.run([shutil.which('node'), '-e', runner + check, str(path)],
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_base_paths_directory_routes_and_queries_are_preserved(self):
        self.run_js(r"""
assert.equal(context.prefixPath('/chapters/ch03?source=CH03-S001#reading-clause-1','/airworthiness',true),
 '/airworthiness/chapters/ch03/?source=CH03-S001#reading-clause-1');
assert.equal(context.prefixPath('/airworthiness/quality/','/airworthiness',true),'/airworthiness/quality/');
assert.equal(context.prefixPath('/?q=材料#resources','/airworthiness',true),'/airworthiness/?q=材料#resources');
assert.equal(context.prefixPath('/chapters/ch03?source=X','',false),'/chapters/ch03?source=X');
assert.equal(context.prefixPath('#reading-page-1','/airworthiness',true),'#reading-page-1');
assert.equal(context.unprefixPath('/airworthiness/chapters/ch03/','/airworthiness'),'/chapters/ch03/');
assert.equal(context.unprefixPath('/airworthiness/','/airworthiness'),'/');
assert.equal(context.unprefixPath('/airworthiness/index.html','/airworthiness'),'/');
assert.equal(context.unprefixPath('/airworthiness-evil/','/airworthiness'),null);
assert.equal(context.unprefixPath('/quality','/airworthiness'),null);
""")

    def test_literal_chinese_search_filters_snippets_and_pagination(self):
        self.run_js(r"""
const rows=[
 {source_id:'CH02-S001',chapter_id:'ch02',title:'其他',document_code:'CCAR-25',content_kind:'extracted',document_status:'effective',snippet:'旧摘要'},
 {source_id:'CH01-S001',chapter_id:'ch01',title:'材料标准',document_code:'GB-1',content_kind:'fulltext',document_status:'effective',snippet:'第一份'},
 {source_id:'CH01-S002',chapter_id:'ch01',title:'旧标准',document_code:'GB-2',content_kind:'metadata',document_status:'abolished',snippet:'登记'}];
const entries=[
 {source_id:'CH02-S001',search_text:'其他ccar-25中文复合材料疲劳'.repeat(8),plain:'很长的前文'.repeat(30)+'复合材料疲劳%*引号"'},
 {source_id:'CH01-S001',search_text:'材料标准gb-1复合材料',plain:'正文复合材料'},
 {source_id:'CH01-S002',search_text:'旧标准gb-2登记',plain:'登记'}];
const search=q=>context.searchResources(rows,entries,new URLSearchParams(q));
let result=search('q=复合 材料&page_size=1');
assert.equal(result.total,2); assert.equal(result.pages,2); assert.equal(result.items[0].source_id,'CH01-S001');
result=search('q=复合材料&page_size=1&page=999');
assert.equal(result.page,2); assert.ok(result.items[0].snippet.includes('复合材料')); assert.ok(result.items[0].snippet.startsWith('…'));
assert.equal(search('q=ccar-25').total,1);
assert.equal(search('q=复合材料&chapter=ch02&content_kind=extracted&status=effective').total,1);
assert.equal(search('q=%22%20OR%201=1%20--').total,0);
assert.equal(search('q=<script>').total,0);
assert.equal(search('status=abolished').total,1);
assert.equal(context.searchResources(rows,[],new URLSearchParams()).total,3);
assert.throws(()=>context.searchResources(rows,[],new URLSearchParams('q=正文')),/index/i);
""")

    def test_invalid_filters_and_query_are_actionable(self):
        self.run_js(r"""
for(const query of ['chapter=ch99','status=bad','content_kind=bad','page=oops','page_size=1e2','q=abc%00def','q='+ 'a'.repeat(201)]) {
 assert.throws(()=>context.searchResources([],[],new URLSearchParams(query)),e=>e.status===400 && e.userMessage.length>0,query);
}
assert.equal(context.searchResources([],[],new URLSearchParams('page=-2&page_size=0')).page,1);
""")

    def test_requests_use_fixed_paths_gzip_and_metadata_only_for_empty_search(self):
        self.run_js(r"""
(async()=>{
 const calls=[], payload={items:[{source_id:'CH01-S001',chapter_id:'ch01',title:'甲',document_code:'A',snippet:'甲'}]};
 context.fetch=async(url,options)=>{
  calls.push(url); assert.ok(options.signal);
  if(url.endsWith('.gz')) return new Response('not found',{status:404});
  return new Response(JSON.stringify(payload),{status:200});
 };
 const signal=new AbortController().signal;
 let result=await context.staticRequest('/api/resources?page=1','/airworthiness',signal);
 assert.equal(result.total,1);
 assert.ok(calls.every(x=>x.startsWith('/airworthiness/data/resources.json')));
 const before=calls.length;
 await context.staticRequest('/api/resources?page=1','/airworthiness',signal);
 assert.equal(calls.length,before);
 for(const path of ['/api/documents/../../secret','https://evil.test/x','/api/documents/CH01-S001/original','/api/chapters/ch99']) {
  await assert.rejects(context.staticRequest(path,'/airworthiness',signal),e=>e.status===404);
 }
 assert.equal(calls.length,before);
 const aborted=new AbortController(); aborted.abort();
 await assert.rejects(context.staticRequest('/api/resources','/airworthiness',aborted.signal),e=>e.name==='AbortError');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_knowledge_map_snapshot_never_exposes_missing_or_unapproved_nodes(self):
        self.run_js(r"""
(async()=>{
 const calls=[];
 context.fetch=async(url)=>{
  calls.push(url);
  if(url.endsWith('.gz')) return new Response('not found',{status:404});
  return new Response(JSON.stringify({knowledge_map:{chapter_id:'ch01',available:false,message:'暂无已审核内容'}}),{status:200});
 };
 const signal=new AbortController().signal;
 const map=await context.staticRequest('/api/chapters/ch01/knowledge-map','/airworthiness',signal);
 assert.equal(map.available,false); assert.equal(map.chapter_id,'ch01');
 await assert.rejects(context.staticRequest('/api/knowledge-nodes/KM-CH01-N001','/airworthiness',signal),e=>e.status===404);
 assert.ok(calls.every(url=>url.includes('/data/chapters/ch01.json')));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_gzip_bytes_decode_and_failed_shards_are_not_partial_results(self):
        self.run_js(r"""
(async()=>{
 const {gzipSync}=require('node:zlib');
 let failures=0;
 context.fetch=async(url)=>{
  if(url.includes('/resources.json')) return new Response(gzipSync(JSON.stringify({items:[
   {source_id:'CH01-S001',chapter_id:'ch01',title:'甲'}, {source_id:'CH02-S001',chapter_id:'ch02',title:'乙'}]})));
  if(url.includes('/search/ch01.json')) return new Response(gzipSync(JSON.stringify([{source_id:'CH01-S001',search_text:'材料',plain:'材料'}])));
  failures++; return new Response('unavailable',{status:503});
 };
 await assert.rejects(context.staticRequest('/api/resources?q=材料','/test',new AbortController().signal));
 assert.ok(failures>0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


if __name__ == '__main__':
    unittest.main()

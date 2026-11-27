import sys,tempfile,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from html_parser import parse_html
from material_registry.core import build_registry,link_parsed
class LayeredTests(unittest.TestCase):
 def test_html_provenance_table_and_policy_without_report_year(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'policy.html'
   p.write_text('<html><nav>导航噪声</nav><script>bad()</script><h1>员工政策</h1><p>工资按时支付。</p><table><tr><th>福利</th><th>对象</th></tr><tr><td>保险</td><td>员工</td></tr></table></html>')
   out=root/'parsed';self.assertEqual(parse_html(p,out),2)
   chunks=[json.loads(x) for x in (out/'retrieval_chunks.jsonl').read_text().splitlines()]
   self.assertFalse(any('导航' in x['text'] or 'bad()' in x['text'] for x in chunks))
   self.assertTrue(any(x['block_type']=='table_text' and '对象' in x['text'] for x in chunks))
   entry=dict(company_id='001',company_name='企业',publisher='企业',title='员工政策',source_kind='policy',original_url='https://example.com/policy',official_verified=True,classification_basis='原件标题',local_path=str(p),evidence_issues=['effective_date_unknown'])
   sources,_=build_registry([entry],root)
   self.assertEqual(sources[0]['metadata_status'],'registered')
   self.assertIsNone(sources[0]['report_year'])
   linked=link_parsed(sources[0],out)
   self.assertEqual(linked['retrieval_chunks.jsonl'][0]['evidence_issues'],['effective_date_unknown'])
   self.assertIsNone(linked['retrieval_chunks.jsonl'][0]['quote_match'])
if __name__=='__main__':unittest.main()

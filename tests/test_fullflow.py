import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.web import allowed,source_nature
from fullflow.scoring import score_indicator
from fullflow.engine import merge
from fullflow.evidence import restore_native_quote
class Fake:
 def ask(self,stage,prompt,data,validate,**kw):
  obj={'groups':[dict(group_id=g['group_id'],status='verified',score=0,reason='模型认为未披露',evidence_refs=[]) for g in data['groups']]};validate(obj);return obj
class FullFlowTests(unittest.TestCase):
 def test_ordinary_missing_cannot_be_zero_when_incomplete(self):
  groups=[dict(group_id=f'E{i}') for i in range(1,6)]
  records=[dict(group_id=g['group_id'],search_complete=False,retrieval_status='pending_review',issues=['缺材料'],assessment={},evidence=[]) for g in groups]
  obj=score_indicator(Fake(),'S1.1.1 C',groups,records,None,'rules')
  self.assertIsNone(obj['final_score']);self.assertTrue(all(g['score'] is None for g in obj['groups']))
 def test_pending_official_check_blocks_final_but_keeps_base(self):
  groups=[dict(group_id=f'P{i}') for i in range(1,6)]
  records=[dict(group_id=g['group_id'],search_complete=True,retrieval_status='no_relevant_evidence_found',issues=[],assessment=dict(content_sufficient=False,evidence_ids=[],conflicts=[]),evidence=[],coverage=[dict(level=i,source_ids=[str(i)],retrieval_completed=True,supplementary_completed=True,coverage_mode='local_rag_v2',planned_query_count=2,completed_query_count=2) for i in (1,2,3)]) for g in groups]
  obj=score_indicator(Fake(),'S1.1.2 C',groups,records,{'retrieval_status':'pending_review'},'rules')
  self.assertEqual(obj['base_score'],0);self.assertIsNone(obj['final_score'])
 def test_normalization_restores_actual_quote_without_guessing(self):
  original='前言。全體員工，均有權申訴。後文'
  self.assertEqual(restore_native_quote('全體員工,均有權申訴。',original),'全體員工，均有權申訴。')
  self.assertIsNone(restore_native_quote('全體員工均有權申訴。',original))
  self.assertIsNone(restore_native_quote('全體員工，不可申訴。',original))
 def test_domain_boundaries(self):
  self.assertTrue(allowed('https://pccz.court.gov.cn/a'))
  self.assertFalse(allowed('https://court.gov.cn.evil.example/a'))
  self.assertFalse(allowed('http://127.0.0.1/a'))
  self.assertFalse(allowed('https://example.com/a'))
 def test_file_nature_overrides_discovery_level(self):
  self.assertEqual(source_nature('Employees and Remuneration','INTERIM\nRESULTS FOR THE SIX MONTHS ENDED 30 JUNE 2025',3),(2,'financial_statement'))
  self.assertEqual(source_nature('2025 ESG Report','',3),(1,'esg'))
  self.assertTrue(allowed('https://cansinotech.com.cn/policy.pdf',['www.cansinotech.com.cn']))
 def test_shared_evidence_not_duplicated(self):
  e=dict(evidence_id='p1',group_ids=['E2'])
  result=merge([e,dict(evidence_id='p1',group_ids=['E3'])])
  self.assertEqual(len(result),1);self.assertEqual(result[0]['group_ids'],['E2','E3'])
if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.gates import evidence_gate,bind_decisive_evidence
from fullflow.scoring import score_indicator
class NoLLM:
 def ask(self,*a,**kw):raise AssertionError('Scoring must not invoke an LLM')
class Tests(unittest.TestCase):
 def record(self,gid):
  a=dict(group_id=gid,content_sufficient=True,evidence_ids=['core'],conflicts=[])
  es=[dict(evidence_id='core',quote_match=True,group_ids=[gid],quote='当期实际支付补偿'),dict(evidence_id='extra',quote_match=None,group_ids=[gid])]
  gate=evidence_gate(a,es,[],[])
  return dict(group_id=gid,assessment=a,evidence=es,decision_input_issues=[],coverage=[],decision_gate=gate)
 def test_minimum_verified_set_cannot_be_overridden_by_ancillary(self):
  rs=[self.record('P'+str(i)) for i in range(1,6)]
  score=score_indicator(NoLLM(),'S1.1.2 C',[dict(group_id=r['group_id']) for r in rs],rs,None,'rules')
  self.assertEqual(score['base_score'],100)
  for r,g in zip(rs,score['groups']):
   self.assertEqual(g,r['decision_gate']['decision']);self.assertEqual(g['evidence_ids'],['core'])
 def test_explicit_cross_group_references_are_preserved(self):
  es=[dict(evidence_id='policy',group_ids=['P1'],quote_match=True),dict(evidence_id='scope',group_ids=['P4'],quote_match=True)]
  a=dict(group_id='P4',content_sufficient=True,evidence_ids=['policy','scope'],conflicts=[])
  bound=bind_decisive_evidence('P4',a,es)
  self.assertEqual(evidence_gate(a,bound,[],[])['decision']['score'],100)
  self.assertEqual(es[0]['group_ids'],['P1'])
 def test_conflict_blocks_even_verified_support(self):
  r=self.record('P1');r['assessment']['conflicts']=['material conflict']
  self.assertIsNone(evidence_gate(r['assessment'],r['evidence'],[],[])['decision']['score'])
 def test_stale_gate_is_not_silently_scored(self):
  rs=[self.record('P'+str(i)) for i in range(1,6)];rs[0]['decision_gate']['decision']['score']=0
  with self.assertRaisesRegex(ValueError,'Stale group decision'):score_indicator(NoLLM(),'S1.1.2 C',[dict(group_id=r['group_id']) for r in rs],rs,None,'rules')
 def test_actual_period_fact_cannot_be_skipped(self):
  r=self.record('E5')
  self.assertIsNone(r['decision_gate']['decision']['score'])
 def test_unknown_content_cannot_be_zero(self):
  cs=[dict(level=i,source_ids=[str(i)],retrieval_completed=True,supplementary_completed=True,coverage_mode='local_rag_v2',planned_query_count=2,completed_query_count=2) for i in (1,2,3)]
  self.assertIsNone(evidence_gate(dict(group_id='P5'),[],[],cs)['decision']['score'])
if __name__=='__main__':unittest.main()

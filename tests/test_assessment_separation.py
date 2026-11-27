import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.evidence import assess
class Model:
 def ask(self,stage,prompt,data,validate,**kw):
  if '_materiality_' in stage:
   obj={'material_refs':[x['ref_id'] for x in data['uncertain_candidates'] if '离职率' in x['quote']],'reason':'仅保留可能满足目标判据的候选'};validate(obj);return obj
  group=data['groups'][0];rs=[e['ref_id'] for e in data['evidence']]
  sufficient=bool(rs)
  if group['group_id']=='E5' and '_support_review_' in stage:sufficient=False
  event=dict(occurred=True,period_confirmed=True,evidence_refs=rs) if group['group_id']=='E5' and sufficient else None
  result={'groups':[dict(group_id=group['group_id'],content_sufficient=sufficient,evidence_refs=rs if sufficient else [],supported_paths=[],missing=[] if sufficient else ['缺少实际结果或原件核验'],conflicts=[],actual_event=event)]};validate(result);return result

def card(eid,verified,quote,gid):
 return dict(evidence_id=eid,group_ids=[gid],quote=quote,period='2025',scope='员工',kind='result',relevance='事实',quote_match=verified,source=dict(source_level=1,report_year=2025,title='报告',original_url='https://example.com/report'))
class Test(unittest.TestCase):
 def test_unverified_candidate_is_not_schema_failure(self):
  r=assess(Model(),[dict(group_id='E1')],[card('table',None,'离职率14.4%','E1')],'rules','test')[0]
  self.assertTrue(r['content_sufficient']);self.assertFalse(r['verified_support_sufficient'])
 def test_verified_alternative_replaces_unnecessary_table(self):
  r=assess(Model(),[dict(group_id='E4')],[card('core',True,'员工可申请内部转岗','E4'),card('table',None,'内部填岗19%','E4')],'rules','test')[0]
  self.assertTrue(r['verified_support_sufficient']);self.assertEqual(r['evidence_ids'],['core'])
 def test_e5_zero_payment_goes_to_semantic_review(self):
  r=assess(Model(),[dict(group_id='E5',actual_current_period_required=True)],[card('zero',True,'年內概無董事收取離職補償','E5')],'rules','test')[0]
  self.assertFalse(r['content_sufficient']);self.assertFalse(r['verified_support_sufficient'])
if __name__=='__main__':unittest.main()

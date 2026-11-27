import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.gates import evidence_gate,explicit_e5_nonoccurrence
class GatesTest(unittest.TestCase):
 def test_verified_path_not_blocked_by_unrelated_supplement(self):
  a=dict(content_sufficient=True,evidence_ids=['core'],conflicts=[])
  evidence=[dict(evidence_id='core',quote_match=True),dict(evidence_id='table',quote_match=None)]
  result=evidence_gate(a,evidence,[dict(kind='quote_not_in_supplied_text',chunk_id='other')],[dict(level=1,source_ids=['report'])])
  self.assertEqual(result['retrieval_status'],'relevant_evidence_found');self.assertTrue(result['decisive_support_verified']);self.assertEqual(result['ancillary_unverified_ids'],['table'])
 def test_necessary_unverified_support_still_pending(self):
  a=dict(content_sufficient=True,evidence_ids=['core'],conflicts=[])
  r=evidence_gate(a,[dict(evidence_id='core',quote_match=None)],[],[dict(level=i,source_ids=[str(i)],indexed_content_reviewed=False,retrieval_completed=True,supplementary_completed=True,coverage_mode='local_rag_v2',planned_query_count=2,completed_query_count=2) for i in (1,2,3)])
  self.assertEqual(r['retrieval_status'],'pending_review')
 def test_conflict_not_erased_by_positive_quote(self):
  r=evidence_gate(dict(content_sufficient=True,evidence_ids=['a'],conflicts=['实质冲突']),[dict(evidence_id='a',quote_match=True)],[],[dict(level=1,source_ids=['r'])])
  self.assertTrue(r['search_complete']);self.assertEqual(r['retrieval_status'],'pending_review')
 def test_irrelevant_unverified_balance_does_not_block_completed_zero(self):
  a=dict(content_sufficient=False,evidence_ids=[],conflicts=[],materiality_reviewed=True,material_unverified_ids=[])
  r=evidence_gate(a,[dict(evidence_id='balance',quote_match=None)],[dict(kind='quote_not_in_supplied_text',chunk_id='irrelevant')],[dict(level=i,source_ids=[str(i)],indexed_content_reviewed=False,retrieval_completed=True,supplementary_completed=True,coverage_mode='local_rag_v2',planned_query_count=2,completed_query_count=2) for i in (1,2,3)])
  self.assertTrue(r['search_complete']);self.assertNotEqual(r['retrieval_status'],'pending_review')
 def test_completed_rag_can_finish_negative_without_full_text(self):
  coverage=[dict(level=i,source_ids=[str(i)],indexed_content_reviewed=False,retrieval_completed=True,supplementary_completed=True,coverage_mode='local_rag_v2',planned_query_count=2,completed_query_count=2) for i in (1,2,3)]
  r=evidence_gate(dict(content_sufficient=False,evidence_ids=[],conflicts=[]),[],[],coverage)
  self.assertTrue(r['search_complete']);self.assertEqual(r['retrieval_status'],'no_relevant_evidence_found')
  coverage[2]['completed_query_count']=1
  self.assertFalse(evidence_gate(dict(content_sufficient=False,evidence_ids=[],conflicts=[]),[],[],coverage)['search_complete'])
 def test_old_retrieval_marker_does_not_claim_supplements_completed(self):
  coverage=[dict(level=i,source_ids=[str(i)],retrieval_completed=True) for i in (1,2,3)]
  self.assertFalse(evidence_gate(dict(content_sufficient=False,evidence_ids=[],conflicts=[]),[],[],coverage)['search_complete'])
 def test_negative_result_not_affirmative_payment(self):
  self.assertTrue(explicit_e5_nonoccurrence('年內概無董事收取任何酬金作為離職補償。'))
  self.assertFalse(explicit_e5_nonoccurrence('本年已向离职员工支付终止补偿。'))
if __name__=='__main__':unittest.main()

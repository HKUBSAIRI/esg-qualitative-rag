import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.engine import Engine,judge_independent
from fullflow.scoring import indicator_rules

class Tests(unittest.TestCase):
 def test_supplement_merges_shared_paragraph_once(self):
  e=Engine.__new__(Engine);e.llm=Mock();e.take=Mock()
  groups=[{'group_id':'P1'},{'group_id':'P2'}]
  c={'source_id':'s','chunk_id':'c'}
  with patch('fullflow.engine.extract',return_value=([],[],[('s','c',0,10)])) as extract:
   e.extract_supplement(groups,[c,c],{},1,1)
   self.assertEqual(extract.call_args.args[1],groups)
   self.assertEqual(extract.call_args.args[2],[c])
   e.take.assert_called_once()
 def test_missing_l4_skips_model_and_preserves_scan_issue(self):
  llm=Mock();issues=['local_only_official_coverage_unconfirmed','existing_official_scanned_lead_requires_quote_and_subject_review']
  r=judge_independent(llm,'S1.1.3',[],[{'result':'No supplied L4 regulatory/judicial notice index'}],issues,'rules',{},Path('.'))
  llm.ask.assert_not_called();self.assertFalse(r['search_complete'])
  self.assertEqual(r['retrieval_status'],'pending_review');self.assertEqual(r['issues'],issues)
 def test_rules_keep_common_and_current_qualitative_only(self):
  rules=(Path(__file__).resolve().parents[1]/'S1.1 大模型评分规则.md').read_text()
  for indicator,title in [('S1.1.1 C','### C.'),('S1.1.2 C','### C.'),('S1.1.3','T5'),('S1.1.4','W5'),('S1.1.5','D5')]:
   selected=indicator_rules(rules,indicator)
   self.assertIn('## 一、',selected);self.assertIn('## 三、',selected);self.assertIn(title,selected)
   self.assertNotIn('### A.',selected);self.assertNotIn('## 九、',selected)
   if indicator!='S1.1.5':self.assertNotIn('## 八、',selected)
 def test_empty_or_single_evidence_skips_conflict_model(self):
  for cards in ([],[{'evidence_id':'one'}]):
   e=Engine.__new__(Engine);e.config={'groups':[],'configuration_id':'test'};e.cards=cards;e.llm=Mock();e.rules='rules';e.checks=Mock(return_value=[])
   with tempfile.TemporaryDirectory() as tmp,patch('fullflow.engine.compact',return_value=({},cards)),patch('fullflow.engine.score_indicator',return_value={}):
    e.out=Path(tmp);e.run({'company_id':'x','company_name':'test'})
   e.llm.ask.assert_not_called()
if __name__=='__main__':unittest.main()

import sys, unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.engine import Engine

class TokenBudgetTests(unittest.TestCase):
 def setUp(self):
  self.engine=Engine.__new__(Engine)
  self.engine.llm=object();self.engine.config={'general_rules':'rules'}
  self.engine.cards=[];self.engine.issues=defaultdict(list)
  self.engine.assessments={};self.engine.assessment_inputs={}
  self.engine.read_chunks=defaultdict(set)
  self.groups=[dict(group_id='P1',indicator_id='S1.1.2 C'),dict(group_id='P2',indicator_id='S1.1.2 C')]
 def fake_assess(self,llm,groups,*args,**kwargs):
  return [dict(group_id=g['group_id'],verified_support_sufficient=False,conflicts=[]) for g in groups]
 def test_unchanged_inputs_skip_and_new_evidence_only_reassesses_affected_group(self):
  e=self.engine
  with patch('fullflow.engine.assess',side_effect=self.fake_assess) as call:
   e.evaluate(self.groups,'initial');self.assertEqual(call.call_count,1)
   e.evaluate(self.groups,'later');self.assertEqual(call.call_count,1)
   e.cards=[dict(evidence_id='a',group_ids=['P2'],quote_match=True)]
   e.evaluate(self.groups,'new');self.assertEqual(call.call_count,2)
   self.assertEqual(call.call_args.args[1],[self.groups[1]])
   e.issues['P1'].append({'kind':'quote_not_in_supplied_text'})
   e.evaluate(self.groups,'issue');self.assertEqual(call.call_count,3)
   self.assertEqual(call.call_args.args[1],[self.groups[0]])
 def test_unread_is_scoped_by_source_and_target(self):
  e=self.engine;e.read_chunks['P1'].add(('s1','c1'))
  chunks=[dict(source_id='s1',chunk_id='c1'),dict(source_id='s2',chunk_id='c1')]
  self.assertEqual(e.unread(self.groups[0],chunks),[chunks[1]])
  self.assertEqual(e.unread(self.groups[1],chunks),chunks)
 def test_satisfied_targets_stop_but_conflicts_continue(self):
  e=self.engine
  e.assessments={'P1':dict(verified_support_sufficient=True,conflicts=[]),'P2':dict(verified_support_sufficient=True,conflicts=['conflict'])}
  self.assertEqual(e.unresolved(self.groups),[self.groups[1]])

if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrieval.configuration import configuration
from retrieval.run_l1 import round_robin
class RetrievalTests(unittest.TestCase):
 def test_only_25_qualitative_groups(self):
  c=configuration();self.assertEqual(len(c['groups']),25)
  self.assertEqual({g['group_id'] for g in c['groups'] if g['actual_current_period_required']},{'E5','T5','W5'})
 def test_parent_dedup_and_group_seats(self):
  ranked=[[dict(unit_id=f'{i}-{j}',parent_chunk_id=f'{i}-{j//2}',source_id='s') for j in range(50)] for i in range(5)]
  chosen=round_robin(ranked)
  self.assertEqual(len(chosen),18);self.assertEqual(len({(x['source_id'],x['parent_chunk_id']) for x in chosen}),18)
  self.assertEqual({x['parent_chunk_id'].split('-')[0] for x in chosen[:15]},set('01234'))
if __name__=='__main__':unittest.main()

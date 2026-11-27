import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.engine import screen_failed_official_sources
class Fake:
 def ask(self,*a,**kw):return {'classification':'uncertain','basis':'无法确认关联'}
class Tests(unittest.TestCase):
 def test_generic_failure_does_not_block(self):
  logs=[{'opened_sources':[{'url':'u','title':'市场监督管理行政处罚信息公示规定','reason':'official_source_unreadable'}]}]
  issues=[{'kind':'official_source_unreadable','url':'u'},'online_search_unconfirmed_or_failed']
  result,remaining=screen_failed_official_sources(Fake(),'S1.1.3',logs,issues,{'company_name':'翰森','company_id':'03692'})
  self.assertEqual(remaining,['online_search_unconfirmed_or_failed'])
  self.assertFalse(result[0]['opened_sources'][0]['blocks_this_check'])
  self.assertNotIn('blocks_this_check',logs[0]['opened_sources'][0])
 def test_uncertain_case_still_blocks(self):
  logs=[{'opened_sources':[{'url':'u','title':'翰森劳动监察案件','reason':'official_source_unreadable'}]}]
  issues=[{'kind':'official_source_unreadable','url':'u'}]
  result,remaining=screen_failed_official_sources(Fake(),'S1.1.3',logs,issues,{'company_name':'翰森'})
  self.assertEqual(remaining,issues)
  self.assertTrue(result[0]['opened_sources'][0]['blocks_this_check'])
 def test_missing_title_still_blocks(self):
  logs=[{'opened_sources':[{'url':'u','reason':'official_source_unreadable'}]}]
  issues=[{'kind':'official_source_unreadable','url':'u'}]
  self.assertEqual(screen_failed_official_sources(Fake(),'S1.1.3',logs,issues,{})[1],issues)
if __name__=='__main__':unittest.main()

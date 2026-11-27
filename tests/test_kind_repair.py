import sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.evidence import repair_kinds
class Model:
 def ask(self,stage,instruction,data,validate,**kw):
  self.items=data['items'];o={'corrections':[{'item_id':x['item_id'],'kind':'mechanism'} for x in data['items']]};validate(o);return o
class Test(unittest.TestCase):
 def test_model_corrects_only_bad_kind_and_preserves_quote(self):
  evidence=[dict(kind='rule',quote='员工可申请复核工资。',period='未明确',scope='员工'),dict(kind='action',quote='已补发工资。')];old=deepcopy(evidence);m=Model()
  repair_kinds(m,evidence,'test')
  self.assertEqual(evidence[0]['kind'],'mechanism');self.assertEqual(evidence[0]['quote'],old[0]['quote']);self.assertEqual(evidence[0]['kind_raw'],'rule');self.assertEqual(evidence[1],old[1]);self.assertEqual(len(m.items),1)
if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrieval.llm import parse_object
class RootTest(unittest.TestCase):
 def test_empty_conflict_object(self):self.assertEqual(parse_object('{"conflicts":[]}'),{'conflicts':[]})
 def test_wrong_root_is_repairable_validation_error(self):
  with self.assertRaises(ValueError):parse_object('[]')
  with self.assertRaises(ValueError):parse_object('null')
if __name__=='__main__':unittest.main()

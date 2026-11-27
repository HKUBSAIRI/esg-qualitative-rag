import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf_parser.retrieval_units import build_units

class UnitsTest(unittest.TestCase):
    def test_long_unicode_restores_original_without_mutation(self):
        text = '员工福利😀及工资支付。\n' * 1500
        chunk = dict(chunk_id='P1', text=text, section='员工', pages=[1,2], source_id='s')
        units = build_units([chunk], 128)
        self.assertGreater(len(units), 1)
        self.assertEqual(''.join(u['text'] for u in units), text)
        self.assertEqual(chunk['text'], text)
        for u in units:
            self.assertEqual(u['text'], text[u['char_start']:u['char_end']])
            self.assertLessEqual(len(u['retrieval_text'].encode()),128)
            self.assertEqual(u['parent_chunk_id'],'P1')
        self.assertEqual(units, build_units([chunk],128))
    def test_short_paragraph_stays_one_unit(self):
        c = dict(chunk_id='P2', text='完整自然段。', section='', pages=[1], source_id='s')
        u = build_units([c])
        self.assertEqual(len(u),1)
        self.assertFalse(u[0]['is_subchunk'])
        self.assertEqual(u[0]['unit_id'],'P2')

if __name__ == '__main__': unittest.main()

import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from material_registry.core import build_registry

class RegistryTests(unittest.TestCase):
    def test_mirrors_and_corrections(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'a.pdf').write_bytes(b'original'); (root/'b.pdf').write_bytes(b'corrected')
            a=dict(company_id='00867',local_path='a.pdf',source_kind='esg',report_year=2025,original_url='https://official/a')
            rows,_=build_registry([a,dict(a,original_url='https://exchange/a')],root)
            self.assertEqual(len(rows),1); self.assertEqual(rows[0]['source_level'],1)
            self.assertEqual(len(rows[0]['urls']),2)
            b=dict(a,local_path='b.pdf',supersedes_source_id=rows[0]['source_id'])
            rows,_=build_registry([a,b],root)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[1]['supersedes_source_id'],rows[0]['source_id'])
    def test_unknown_and_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'2025_ESG.pdf').write_bytes(b'x')
            a=dict(company_id='001',local_path='2025_ESG.pdf')
            rows,_=build_registry([a],root)
            self.assertIsNone(rows[0]['source_level']); self.assertIsNone(rows[0]['report_year'])
            self.assertEqual(rows[0]['metadata_status'],'pending_review')
            with self.assertRaises(ValueError): build_registry([dict(a,company_id=1)],root)
            with self.assertRaises(ValueError): build_registry([dict(a,source_kind='annual',source_level=1)],root)
            with self.assertRaises(ValueError): build_registry([dict(a,file_sha256='bad')],root)

if __name__=='__main__': unittest.main()

import sys,tempfile,unittest,copy
from pathlib import Path
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullflow.table_verification import verify_table
class Tests(unittest.TestCase):
 def setup_table(self):
  doc=fitz.open();page=doc.new_page(width=500,height=250);cells=[]
  values=[['Metric','Unit','2024','2025'],['Turnover','%','11','10']]
  for row,values_row in enumerate(values):
   for col,text in enumerate(values_row):
    page.insert_text((30+col*110,50+row*35),text,fontsize=10)
  for row,values_row in enumerate(values):
   for col,text in enumerate(values_row):
    rect=page.search_for(text)[0]
    # Duplicated numeric strings are absent in this fixture.
    cells.append(dict(text=text,start_row_offset_idx=row,start_col_offset_idx=col,column_header=row==0,bbox=dict(l=rect.x0,t=rect.y0,r=rect.x1,b=rect.y1,coord_origin='TOPLEFT')))
  e=dict(quote='Metric | Unit | 2024 | 2025\nTurnover | % | 11 | 10',location=dict(pages=[1]),table_structure=dict(self_ref='#/tables/0',prov=[dict(page_no=1)],data=dict(table_cells=cells)))
  return doc,e
 def test_cell_and_year_mapping(self):
  doc,e=self.setup_table();v=verify_table(e,doc);self.assertIsNotNone(v);self.assertEqual(v['year_columns'],{'2':'2024','3':'2025'});self.assertFalse(v['continuous_text']);doc.close()
 def test_changed_number_rejected(self):
  doc,e=self.setup_table();e['quote']=e['quote'].replace('| 10','| 99');self.assertIsNone(verify_table(e,doc));doc.close()
 def test_swapped_years_rejected(self):
  doc,e=self.setup_table();e['quote']=e['quote'].replace('2024 | 2025','2025 | 2024');self.assertIsNone(verify_table(e,doc));doc.close()
 def test_wrong_cell_coordinates_rejected(self):
  doc,e=self.setup_table();e['table_structure']['data']['table_cells'][-1]['bbox']=dict(e['table_structure']['data']['table_cells'][-2]['bbox']);self.assertIsNone(verify_table(e,doc));doc.close()
 def test_wrong_page_rejected(self):
  doc,e=self.setup_table();e['location']['pages']=[2];self.assertIsNone(verify_table(e,doc));doc.close()
 def test_negative_number_cannot_become_positive(self):
  doc,e=self.setup_table();e['quote']=e['quote'].replace('| 10','| -10');self.assertIsNone(verify_table(e,doc));doc.close()
if __name__=='__main__':unittest.main()

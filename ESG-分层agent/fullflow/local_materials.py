"""User-supplied local originals only; no search or download operations."""
import json
from pathlib import Path
from retrieval.run_l1 import rows
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'runs/local_supplements/materials.json'
def local_materials(company_id,level,website_only=False):
 if not MANIFEST.exists():raise RuntimeError('Local supplementary material preparation has not finished')
 result=[]
 for item in json.loads(MANIFEST.read_text()):
  s=item['source']
  if s['company_id']!=company_id or s['source_level']!=level:continue
  # Local policy and thematic originals belong to the website substage.
  if level==3 and not website_only:continue
  result.append((s,rows(Path(item['chunks_path']))))
 return result

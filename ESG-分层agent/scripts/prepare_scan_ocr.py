"""Material-readability sidecar only. Does not replace canonical PDF chunks."""
import json,hashlib,subprocess
from pathlib import Path
import fitz,httpx
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'runs/random10_20261127/materials_preparation';data=ROOT/'resources/tessdata';data.mkdir(parents=True,exist_ok=True)
model=data/'chi_sim.traineddata'
url='https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/chi_sim.traineddata'
if not model.exists():
 with httpx.Client(timeout=90,follow_redirects=True,transport=httpx.HTTPTransport(local_address='0.0.0.0')) as client:
  r=client.get(url);r.raise_for_status();model.write_bytes(r.content)
# English pack is a third-party runtime resource; copy it locally for reproducibility.
import shutil
shutil.copy2('/opt/homebrew/share/tessdata/eng.traineddata',data/'eng.traineddata')
e=next(x for x in json.loads((base/'local_inventory.json').read_text()) if x['source_level']==4)
out=base/'ocr'/e['file_sha256'];out.mkdir(parents=True,exist_ok=True);pages=[]
with fitz.open(e['local_path']) as doc:
 for i,page in enumerate(doc):
  image=out/f'page_{i+1}.png';page.get_pixmap(matrix=fitz.Matrix(2,2)).save(str(image))
  prefix=out/f'page_{i+1}'
  subprocess.run(['tesseract',str(image),str(prefix),'--tessdata-dir',str(data),'-l','chi_sim+eng','--psm','3'],check=True,capture_output=True,timeout=120)
  pages.append(dict(page=i+1,text=prefix.with_suffix('.txt').read_text(),image=str(image.resolve()),quote_match=None,verification_status='ocr_not_verified'))
(out/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
(out/'manifest.json').write_text(json.dumps(dict(original_pdf=e['local_path'],file_sha256=e['file_sha256'],engine='local_tesseract',language='chi_sim+eng',model_url=url,model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),pages=len(pages),is_canonical_parser_output=False,quote_verification='not_performed'),ensure_ascii=False,indent=2))
print('OCR sidecar complete:',len(pages),'pages')

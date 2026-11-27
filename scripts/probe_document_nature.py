import hashlib,json,sys
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fullflow.web import classify_pdf
from retrieval.llm import LLM
out=ROOT/'runs/full5_20261127/document_nature_probe'
for f in (ROOT/'runs/full5_20261127/01801/web_sources').glob('*/source.json'):
 s=json.loads(f.read_text())
 if hashlib.sha256(s['original_url'].encode()).hexdigest().startswith('2c0d13437696'):
  with fitz.open(s['local_path']) as pdf:preview='\n'.join(pdf[i].get_text() for i in range(min(5,len(pdf))))[:16000]
  result=classify_pdf(LLM(sys.argv[1],out/'calls'),s,preview)
  assert result['kind']=='esg' and result['report_year']==2024,result
  print('PASS: image-cover 2024 ESG report correctly excluded from L4')
  break
else:raise RuntimeError('Reproduction source not found')

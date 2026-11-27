"""Local-only auxiliary L4 candidate index. OCR pages are not natural-paragraph chunks."""
import json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from indexing.bm25 import tokenize
from pdf_parser.retrieval_units import build_units
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'runs/random10_20261127';PREP=RUN/'materials_preparation'
e=next(json.loads(x) for x in (PREP/'material_catalog.jsonl').read_text().splitlines() if json.loads(x).get('source_level')==4)
pages=json.loads(Path(e['ocr_sidecar']).read_text());chunks=[]
for p in pages:
 cid='OCR_'+hashlib.sha256(f"{e['file_sha256']}:{p['page']}".encode()).hexdigest()[:24]
 chunks.append(dict(chunk_id=cid,source_id=e['source_id'],company_id=e['company_id'],source_level=4,text=p['text'],retrieval_text=p['text'],pages=[p['page']],block_type='auxiliary_ocr_page',section='',image=p['image'],quote_match=None,requires_review=True))
units=build_units(chunks)
out=RUN/'layered/auxiliary_local_index'/e['company_id']/'L4';out.mkdir(parents=True,exist_ok=True)
for name,rows in [('chunks.jsonl',chunks),('units.jsonl',units),('sources.jsonl',[e]),('bm25_tokens.jsonl',[dict(unit_id=u['unit_id'],tokens=tokenize(u['retrieval_text'])) for u in units])]:
 (out/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
(out/'manifest.json').write_text(json.dumps(dict(company_id=e['company_id'],source_level=4,vector_ready=False,local_only=True,not_canonical_paragraph_output=True,quote_match=None,retrieval_status='pending_review',rows=len(units),bm25=dict(k1=1.5,b=0.75),issues=['OCR not quote-verified','group relationship and materiality not verified']),ensure_ascii=False,indent=2))
assert len(chunks)==5 and ''.join(u['text'] for u in units)==''.join(c['text'] for c in chunks)
print('PASS: local-only L4 OCR candidate index,',len(chunks),'pages;',len(units),'units')

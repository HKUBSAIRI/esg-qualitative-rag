"""Verify structured PDF cells against their native glyphs and coordinates.

No fuzzy matching, numeric conversion, OCR, or LLM call is used. Pipe characters
are serialization separators, not a claim of a continuous native text passage.
"""
import json,unicodedata,re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
def canonical(text):
 return ''.join(unicodedata.normalize('NFKC',text).translate(str.maketrans({'—':'-','–':'-'})).split())
@lru_cache(maxsize=64)
def stored_structure(company_id,level,source_id,chunk_id):
 paths=[ROOT/'runs/local_material_rag/index'/company_id/f'L{level}'/'chunks.jsonl',ROOT/'runs/random10_20261127/layered/registry/linked'/source_id/'retrieval_chunks.jsonl']
 for path in paths:
  if not path.is_file():continue
  for line in path.read_text().splitlines():
   c=json.loads(line)
   if c.get('source_id')==source_id and c.get('chunk_id')==chunk_id:return c.get('raw_table')
 return None

def verify_table(e,doc):
 structure=e.get('table_structure')
 if not structure:
  s=e['source'];structure=stored_structure(s['company_id'],s['source_level'],s['source_id'],e['chunk_id'])
 if not structure:return None
 prov=structure.get('prov') or []
 # Page identity must be explicit; multi-page/ambiguous grids stay unresolved.
 if len(prov)!=1 or prov[0].get('page_no') not in e['location']['pages']:return None
 number=prov[0]['page_no'];page=doc[number-1];rows=defaultdict(list)
 for c in structure.get('data',{}).get('table_cells',[]):
  if str(c.get('text','')).strip():rows[c['start_row_offset_idx']].append(c)
 if not rows:return None
 ordered=[c for _,cs in sorted(rows.items()) for c in sorted(cs,key=lambda c:c['start_col_offset_idx'])]
 serial=[];spans=[];pos=0
 for i,c in enumerate(ordered):
  if i:
   separator='\n' if ordered[i-1]['start_row_offset_idx']!=c['start_row_offset_idx'] else ' | '
   serial.append(separator);pos+=len(canonical(separator))
  text=c['text'];start=pos;serial.append(text);pos+=len(canonical(text));spans.append((start,pos,c))
 full=''.join(serial);needle=canonical(e['quote']);haystack=canonical(full)
 if not needle or haystack.count(needle)!=1:return None
 start=haystack.index(needle);end=start+len(needle)
 chosen=[c for a,b,c in spans if a<end and b>start]
 # Include the header row to preserve the meaning and year-column mapping.
 headers=[c for c in ordered if c.get('column_header')]
 targets={id(c):c for c in headers+chosen};verified={};year_headers={}
 for c in headers:
  if re.fullmatch(r'(?:19|20)\d{2}',c['text'].strip()):year_headers[c['start_col_offset_idx']]=c
 for c in targets.values():
  b=c.get('bbox')
  if not b:return None
  if b.get('coord_origin')=='BOTTOMLEFT':rect=fitz.Rect(b['l'],page.rect.height-b['t'],b['r'],page.rect.height-b['b'])
  elif b.get('coord_origin')=='TOPLEFT':rect=fitz.Rect(b['l'],b['t'],b['r'],b['b'])
  else:return None
  rect=rect+(-1,-1,1,1)
  if rect.is_empty or not page.rect.intersects(rect):return None
  native=page.get_textbox(rect)
  if canonical(native)!=canonical(c['text']):return None
  # A value assigned to a year column must geometrically lie under that header.
  column=c['start_col_offset_idx']
  if column in year_headers and not c.get('column_header'):
   centers=sorted((k,(v['bbox']['l']+v['bbox']['r'])/2) for k,v in year_headers.items())
   i=next(i for i,(k,x) in enumerate(centers) if k==column);x=(rect.x0+rect.x1)/2
   left=(centers[i-1][1]+centers[i][1])/2 if i else centers[i][1]-80
   right=(centers[i][1]+centers[i+1][1])/2 if i+1<len(centers) else centers[i][1]+80
   if not left<x<right:return None
  verified[id(c)]=dict(page=number,row=c['start_row_offset_idx'],column=column,row_span=c.get('row_span',1),column_span=c.get('col_span',1),bbox=list(rect),native_text=native.strip(),column_header=bool(c.get('column_header')))
 selected_rows=defaultdict(list)
 for c in chosen:selected_rows[c['start_row_offset_idx']].append(verified[id(c)])
 quote='\n'.join(' | '.join(cell['native_text'] for cell in sorted(cs,key=lambda c:c['column'])) for _,cs in sorted(selected_rows.items()))
 markers=[dict(marker=m.group(1),row=c['start_row_offset_idx'],column=c['start_col_offset_idx'],page=number,bbox=verified[id(c)]['bbox']) for c in chosen if not c.get('column_header') for m in [re.search(r'[^0-9\s]\s+(\d{1,3})$',c['text'])] if m]
 return dict(footnote_markers=markers,quote=quote,page=number,table_ref=structure.get('self_ref'),cells=list(verified.values()),year_columns={str(k):v['text'] for k,v in year_headers.items()},normalization='NFKC/whitespace and parser dash variants only; native glyphs retained',continuous_text=False)

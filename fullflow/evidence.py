import hashlib,json,re,unicodedata
from pathlib import Path
import fitz
from retrieval.run_l1 import norm,save
from pdf_parser.retrieval_units import build_units
from fullflow.gates import explicit_e5_nonoccurrence

KINDS={'policy','mechanism','action','result','plan','boundary'}

def repair_kinds(llm,evidence,stage):
 bad=[(i,e) for i,e in enumerate(evidence) if e.get('kind') not in KINDS]
 if not bad:return
 items=[dict(item_id=str(i),invalid_kind=e.get('kind_raw',e.get('kind')),quote=e['quote'],period=e.get('period'),scope=e.get('scope')) for i,e in bad]
 def validate_fix(obj):
  corrections=obj.get('corrections',[])
  if len(corrections)!=len(items) or {c.get('item_id') for c in corrections}!={x['item_id'] for x in items}:raise ValueError('Return exactly one correction for each item_id')
  for c in corrections:
   if c.get('kind') not in KINDS:raise ValueError('kind must be exactly one of: policy, mechanism, action, result, plan, boundary; do not return slash-separated choices')
 fixed=llm.ask('kind_fix_'+stage,'上次证据类型字段不合规范。只更正这些条目的kind，不重写、不概括、不修改引文或任何其他事实。每条只能选择一个英文标签：policy=政策要求，mechanism=程序机制，action=实际行动，result=实际结果，plan=未来计划，boundary=范围或限制。复合原文选最能表达本条采证事实的类别，不能因存在制度就推断已经执行。输出示例{"corrections":[{"item_id":"0","kind":"policy"}]}。',dict(items=items),validate_fix,max_tokens=1600)
 lookup={c['item_id']:c['kind'] for c in fixed['corrections']}
 for i,e in bad:
  e['kind_raw']=e.get('kind_raw',e.get('kind'));e['kind']=lookup[str(i)]
  e['kind_note']='类型字段经模型定向纠正并通过单值枚举校验；原文及其他字段未改。'

def extract(llm,groups,chunks,sources,stage):
 """Only matching continuous quotes survive; malformed candidates become issues."""
 parts=[]
 for c in chunks:
  for u in build_units([c],max_bytes=22000):
   parts.append(dict(c, text=u['text'],char_start=u['char_start'],char_end=u['char_end']))
 batches=[];batch=[];size=0
 for c in parts:
  n=len(c['text'].encode())+500
  if batch and size+n>46000:batches.append(batch);batch=[];size=0
  batch.append(c);size+=n
 if batch:batches.append(batch)
 evidence=[];issues=[];viewed=[]
 for i,batch in enumerate(batches):
  refs={f'p{j+1:03}':c for j,c in enumerate(batch)}
  data=dict(evaluation_companies=[dict(company_id=s.get('company_id'),company_name=s.get('company_name')) for s in sources.values()],targets=groups,paragraphs=[dict(ref_id=k,text=c['text'],section=c.get('section'),pages=c['pages'],source_period=sources[c['source_id']].get('period'),source_year=sources[c['source_id']].get('report_year'),source_title=sources[c['source_id']]['title'],source_url=sources[c['source_id']]['original_url'],publisher=sources[c['source_id']].get('publisher'),evidence_issues=c.get('evidence_issues',[])) for k,c in refs.items()])
  def validate(obj):
   if not isinstance(obj.get('evidence'),list):raise ValueError('evidence must be a list')
   for e in obj['evidence']:
    if e.get('ref_id') not in refs or not isinstance(e.get('quote'),str):raise ValueError('Invalid short reference or quote')
    if not isinstance(e.get('group_ids'),list) or not set(e['group_ids'])<={g['group_id'] for g in groups}:raise ValueError('Invalid group references')
    if not all(isinstance(e.get(k),str) for k in ('period','scope','relevance')):raise ValueError('Missing evidence metadata')
   repair_kinds(llm,obj['evidence'],stage+f'_batch{i}')
   if any(e.get('kind') not in KINDS for e in obj['evidence']):raise ValueError('Evidence kind repair did not pass validation')
  prompt='你是检索取证Agent，不评分。只提取评价企业及原文明确关联的员工事项。检索归档主体不等于原文实际主体；其他公司、政府一般劳动政策不得冒充评价企业措施。子公司关系须有原文依据，不因名称相似推断。阅读本批全部原文，提取与目标有明确事实关联的最少充分连续引文。保留支持、限制或冲突证据；无关段落不返回。表格引文须包含必要表头、单位、脚注；无法连续引用时分别返回关联引文。不要改字、标点，不用省略号拼接。期间/范围无法确定写未明确。原文同一事实支持多组时复用一条。只按允许路径找证据，不要求凑齐全部例子。E5/T5/W5需当期事实，费用确认不等于支付。输出{"evidence":[{"ref_id":"p001","group_ids":["E2"],"quote":"连续原文","kind":"policy/mechanism/action/result/plan/boundary","period":"期间或未明确","scope":"范围或未明确","relevance":"事实关联"}]}。不得断言整个来源无披露。'
  obj=llm.ask(stage+f'_batch{i}',prompt,data,validate,max_tokens=10000)
  save(llm.dest.parent/'batch_progress'/f'{stage}.json',dict(completed_batches=i+1,total_batches=len(batches),last_batch_parts=len(batch)))
  for c in batch:viewed.append((c['source_id'],c['chunk_id'],c['char_start'],c['char_end']))
  for e in obj['evidence']:
   c=refs[e['ref_id']]
   if not e['quote'].strip() or norm(e['quote']) not in norm(c['text']):
    issues.append(dict(kind='quote_not_in_supplied_text',chunk_id=c['chunk_id'],quote=e['quote'],group_ids=e['group_ids']));continue
   eid=c['chunk_id']+'_'+hashlib.sha256((c['source_id']+norm(e['quote'])).encode()).hexdigest()[:16]
   evidence.append(dict(evidence_id=eid,chunk_id=c['chunk_id'],group_ids=e['group_ids'],quote=e['quote'],source=sources[c['source_id']],location=dict(pages=c['pages'],printed_pages=c.get('printed_pages',[]),section=c.get('section'),bboxes=c.get('bboxes',[]),html_location=c.get('location')),quote_match=None,parsed_text_match=True,block_type=c.get('block_type'),table_structure=c.get('raw_table') if c.get('block_type')=='table_text' else None,kind=e['kind'],kind_raw=e.get('kind_raw'),kind_note=e.get('kind_note'),period=e['period'],scope=e['scope'],relevance=e['relevance']))
 return evidence,issues,viewed

def restore_native_quote(quote,text):
 # Map normalized characters back to actual native-PDF character offsets.
 # This restores parser normalization; it never drops punctuation or guesses words.
 chars=[];positions=[]
 for i,ch in enumerate(text):
  for normalized in unicodedata.normalize('NFKC',ch):
   if not normalized.isspace():chars.append(normalized);positions.append(i)
 needle=''.join(unicodedata.normalize('NFKC',quote).split())
 if not needle:return None
 offset=''.join(chars).find(needle)
 if offset<0:return None
 original=text[positions[offset]:positions[offset+len(needle)-1]+1]
 if ''.join(unicodedata.normalize('NFKC',original).split())!=needle:return None
 return original

def verify(e):
 """Recover a continuous native quote, then verify actual original characters."""
 source=e['source'];p=Path(source['local_path'])
 if not p.is_file():return None,'source_file_missing'
 try:
  if p.suffix.lower()=='.pdf':
   with fitz.open(p) as doc:
    if e.get('block_type')=='table_text':
     from fullflow.table_verification import verify_table
     table=verify_table(e,doc)
     if table is not None:
      e.setdefault('parsed_quote',e['quote']);e['quote']=table.pop('quote');e['table_verification']=table;e['quote_format']='verified_pdf_table_cells'
      return True,'native_pdf_cells_and_year_columns_verified'
     return None,'table_cell_or_year_mapping_requires_review'
    for sorted_order in (True,False):
     text='\n'.join(doc[n-1].get_text(sort=sorted_order) for n in e['location']['pages'])
     if norm(e['quote']) in norm(text):return True,'native_pdf_text_match'
     if e.get('block_type')=='table_text' and ' | ' in e['quote']:
      # Only remove the parser's known cell separator, then demand an exact
      # continuous native-text match of all headers/cells/values in order.
      table_original=restore_native_quote(e['quote'].replace(' | ',' '),text)
      if table_original is not None:
       e['parsed_quote']=e['quote'];e['quote']=table_original;e['quote_format']='native_table_text_stream'
       return True,'native_pdf_table_serialization_restored'
     restored=restore_native_quote(e['quote'],text)
     if restored is not None:
      e['parsed_quote']=e['quote'];e['quote']=restored
      return True,'native_pdf_quote_restored_via_nfkc_offset_map'
    if '|' in e['quote'] and len(e['quote'])<4000:
     for number in e['location']['pages']:
      try: tables=doc[number-1].find_tables().tables
      except Exception: continue
      for table in tables:
       native='\n'.join(' | '.join(str(cell or '') for cell in row) for row in table.extract())
       restored=restore_native_quote(e['quote'],native)
       if restored is not None:
        e['parsed_quote']=e['quote'];e['quote']=restored;e['quote_format']='native_table_rows'
        return True,'native_pdf_table_cells_match'
   return None,'layout_or_table_quote_requires_visual_check'
  if p.suffix.lower()=='.html':return (True,'stored_html_text_match') if e.get('parsed_text_match') else (None,'html_quote_not_verified')
 except Exception as ex:return None,'source_read_failure:'+type(ex).__name__
 return None,'unsupported_source_format'

def compact(evidence):
 refs={f'e{i+1:03}':e for i,e in enumerate(evidence)}
 data=[dict(ref_id=k,quote=e['quote'],period=e['period'],scope=e['scope'],kind=e['kind'],relevance=e['relevance'],quote_match=e['quote_match'],source_level=e['source']['source_level'],source_period=e['source'].get('period'),source_year=e['source'].get('report_year'),source_title=e['source']['title'],source_url=e['source']['original_url'],publisher=e['source'].get('publisher'),evidence_issues=e['source'].get('evidence_issues',[])) for k,e in refs.items()]
 return refs,data

def assess(llm,groups,evidence,rules,stage,candidate_issues=None):
 refs,data=compact(evidence)
 allowed={g['group_id'] for g in groups}
 def validate_for(targets,allowed_refs):
  def validate(obj):
   gs=obj.get('groups',[])
   if not isinstance(gs,list) or any(not isinstance(g,dict) for g in gs):raise ValueError('groups must be an array of objects')
   if len(gs)!=len(targets) or {g.get('group_id') for g in gs}!={g['group_id'] for g in targets}:raise ValueError('Assessment target IDs mismatch')
   for g in gs:
    if type(g.get('content_sufficient')) is not bool or not isinstance(g.get('missing'),list) or not isinstance(g.get('conflicts'),list):raise ValueError('Assessment fields invalid')
    if not set(g.get('evidence_refs',[]))<=allowed_refs:raise ValueError('Unknown evidence ref')
    if g['content_sufficient'] and not g.get('evidence_refs'):raise ValueError('Sufficiency requires evidence references')
    event=g.get('actual_event')
    if event is not None and not isinstance(event,dict):raise ValueError('actual_event must be an object or null, not an array')
    if event and not set(event.get('evidence_refs',[]))<=allowed_refs:raise ValueError('Unknown actual-event reference')
  return validate
 prompt='只判断原文内容是否满足条件，不评分，不宣布查完。原文核验状态与内容判断分开：quote_match=null不属于输出格式错误，不确定内容仍可列为候选；程序另管确认与跳层。按允许路径任一路径成立即可，给最小充分引用。E5/T5/W5需当期实际发生，零事件/无支付本身不能证明执行；E5特定人员未收离职补偿不能满足实际离职保障。实际结果组若确认内容充分，返回actual_event={occurred:true,period_confirmed:true,evidence_refs:[正向事实编号]}，否则actual_event=null。输出{"groups":[{"group_id":"E1","content_sufficient":false,"evidence_refs":[],"supported_paths":[],"missing":[],"conflicts":[],"actual_event":null}]}。'
 obj=llm.ask(stage+'_content_v2',prompt,dict(groups=groups,rules=rules,evidence=data),validate_for(groups,set(refs)))
 by_group={g['group_id']:g for g in groups}
 for g in obj['groups']:
  target=by_group[g['group_id']]
  selected=[refs[r] for r in g.get('evidence_refs',[])]
  needs_event_review=bool(g['content_sufficient'] and target.get('actual_current_period_required') and (not g.get('actual_event') or g['actual_event'].get('occurred') is not True or g['actual_event'].get('period_confirmed') is not True or (g['group_id']=='E5' and all(explicit_e5_nonoccurrence(e['quote']) for e in selected))))
  needs_verified_review=bool(g['content_sufficient'] and any(e['quote_match'] is not True for e in selected))
  if needs_event_review or needs_verified_review:
   verified_refs={key for key,e in refs.items() if e['quote_match'] is True and g['group_id'] in e.get('group_ids',[])}
   review=llm.ask(stage+'_support_review_'+g['group_id'],prompt+' 本次只复核已核实原文能否独立构成充分条件。不能使用不在本次输入的表格数值或其他事实。E5仅无支付必须返回false。',dict(groups=[target],rules=rules,evidence=[e for e in data if e['ref_id'] in verified_refs]),validate_for([target],verified_refs),max_tokens=2600)['groups'][0]
   if review['content_sufficient'] or needs_event_review:
    g.update(review)
   else:
    g['verification_missing']=review['missing']
  selected=[refs[r] for r in g.get('evidence_refs',[])]
  if target.get('actual_current_period_required') and g['content_sufficient']:
   event=g.get('actual_event') or {};event_refs=event.get('evidence_refs',[])
   invalid_event=event.get('occurred') is not True or event.get('period_confirmed') is not True or not event_refs or not set(event_refs)<=set(g['evidence_refs'])
   if g['group_id']=='E5' and event_refs and all(explicit_e5_nonoccurrence(refs[r]['quote']) for r in event_refs):invalid_event=True
   if invalid_event:
    g['content_sufficient']=False;g['missing']=list(dict.fromkeys(g['missing']+['尚未证实本组要求的当期实际发生事实；无支付或无事件不构成该事实']))
  if not g['content_sufficient'] or any(e['quote_match'] is not True for e in selected):
   unverified={k:e for k,e in refs.items() if e['quote_match'] is not True and g['group_id'] in e.get('group_ids',[])}
   rejected=[x for x in (candidate_issues or []) if isinstance(x,dict) and x.get('kind')=='quote_not_in_supplied_text' and g['group_id'] in x.get('group_ids',[])]
   uncertain=[dict(ref_id=k,quote=e['quote'],period=e['period'],scope=e['scope'],candidate_type='unverified_original') for k,e in unverified.items()]
   rejected_refs={f'x{i+1:03}':x for i,x in enumerate(rejected)}
   uncertain.extend(dict(ref_id=k,quote=x.get('quote',''),candidate_type='rejected_nonmatching_quote') for k,x in rejected_refs.items())
   def validate_materiality(obj):
    if not isinstance(obj.get('material_refs'),list) or not set(obj['material_refs'])<=set(unverified)|set(rejected_refs):raise ValueError('Materiality references must identify supplied uncertain candidates')
   if uncertain:
    decision=llm.ask(stage+'_materiality_'+g['group_id'],'只判断未核验候选是否影响本组结论，不确认候选事实、不评分。反事实检验：即使该引文完全核实，它是否可能满足本组任一成立路径，或与已核实结论形成实质冲突？若仍不符合判据，不把它当必要证据。例：普通应付工资余额不能单独证明工资差错补救；员工福利总费用不自动证明终止补偿实际支付。返回真正影响判分的候选编号，其余保留诊断不阻断。输出{"material_refs":[],"reason":"判据相关性"}。',dict(target=target,assessment=g,uncertain_candidates=uncertain),validate_materiality,max_tokens=1800)
    g['material_unverified_ids']=[unverified[k]['evidence_id'] if k in unverified else rejected_refs[k].get('chunk_id') for k in decision['material_refs']]
    g['materiality_reason']=decision.get('reason')
   else:g['material_unverified_ids']=[]
   g['materiality_reviewed']=True
  g['evidence_ids']=[refs[r]['evidence_id'] for r in g.pop('evidence_refs')]
  g['verified_support_sufficient']=bool(g['content_sufficient'] and selected and all(e['quote_match'] is True for e in selected))
  if g.get('actual_event'):g['actual_event']['evidence_ids']=[refs[r]['evidence_id'] for r in g['actual_event'].pop('evidence_refs',[])]
 return obj['groups']

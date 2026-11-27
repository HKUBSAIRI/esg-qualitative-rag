"""L1 pilot: original hybrid recall + structured evidence/gap assessment. No scoring."""
import argparse,hashlib,json,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np
from .configuration import configuration
from .hybrid import build_pool,select_without_reranker
from .llm import LLM
from indexing.bm25 import BM25,tokenize
from indexing.embedding import Embedding
from pdf_parser.retrieval_units import build_units
ROOT=Path(__file__).resolve().parents[1]
def rows(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def save(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def norm(t):return ''.join(t.split())
def round_robin(rankings,limit=18):
 chosen=[];seen=set()
 for _ in range(3):
  for ranked in rankings:
   for c in ranked:
    key=(c['source_id'],c['parent_chunk_id'])
    if key not in seen:chosen.append(c);seen.add(key);break
 for rank in range(50):
  for ranked in rankings:
   if len(chosen)>=limit:return chosen
   if rank<len(ranked):
    c=ranked[rank];key=(c['source_id'],c['parent_chunk_id'])
    if key not in seen:chosen.append(c);seen.add(key)
 return chosen[:limit]

def run(index,out,env_file,code='03692'):
 config=configuration();save(out/'configuration.json',config)
 llm=LLM(env_file,out/'calls');embed=Embedding(index/'embedding_cache',env_file)
 def validate_queries(obj):
  gs=obj['groups'];assert_ids={g['group_id'] for g in config['groups']}
  if len(gs)!=25 or {g['group_id'] for g in gs}!=assert_ids:raise ValueError('Query group IDs mismatch')
  if any(not isinstance(g.get('main_query'),str) or not g['main_query'].strip() or not isinstance(g.get('supplement_queries'),list) or len(g['supplement_queries'])>2 for g in gs):raise ValueError('Invalid queries')
 query=llm.ask('queries','根据各组条件生成主检索句（中文兼顾英文同义词）及最多2条互补查询。每组只需任一成立路径时不得强制全部子项。只要求E5/T5/W5当期实际发生。不要一律加入2025造成漏召回。输出{"groups":[{"group_id":"E1","main_query":"...","supplement_queries":["..."]}]}。不读取历史评分或GT。',config,validate_queries)
 save(out/'queries.json',query);qm={g['group_id']:g for g in query['groups']};gids=[g['group_id'] for g in config['groups']];qv=embed.encode([qm[g]['main_query'] for g in gids]);qmap=dict(zip(gids,qv))
 base=index/code/'L1';manifest=json.loads((base/'manifest.json').read_text())
 if not manifest.get('vector_ready') or manifest['model']!=embed.model or manifest['dimensions']!=embed.dim:raise ValueError('Index/query embedding mismatch')
 units=rows(base/'units.jsonl');chunks=rows(base/'chunks.jsonl');sources={s['source_id']:s for s in rows(base/'sources.jsonl')};vectors=np.load(base/'embeddings.npy')
 bm25=BM25([r['tokens'] for r in rows(base/'bm25_tokens.jsonl')]);lookup={(c['source_id'],c['chunk_id']):c for c in chunks}
 corpus=[dict(u,id=u['unit_id'],paragraph_id=u['source_id']+':'+u['unit_id']) for u in units]
 records=[];pool_log={}
 for indicator in dict.fromkeys(g['indicator_id'] for g in config['groups']):
  groups=[g for g in config['groups'] if g['indicator_id']==indicator];rankings=[]
  for g in groups:
   gid=g['group_id'];pool=build_pool(corpus,bm25.scores(tokenize(qm[gid]['main_query'])),vectors@qmap[gid],150,{})
   ranked=select_without_reranker(pool,{},50);rankings.append(ranked)
   pool_log[gid]=[dict(unit_id=c['unit_id'],parent_chunk_id=c['parent_chunk_id'],source_id=c['source_id'],bm25_rank=c['bm25_rank'],dense_rank=c['dense_rank'],composite_score=c['composite_score']) for c in ranked]
  selected=round_robin(rankings);context={}
  for u in selected:
   c=lookup[(u['source_id'],u['parent_chunk_id'])];context[(c['source_id'],c['chunk_id'])]=c
   for cid in [c.get('prev_chunk_id'),c.get('next_chunk_id')]+c.get('note_candidates',[]):
    adj=lookup.get((c['source_id'],cid))
    if adj and adj.get('section')==c.get('section'):context[(adj['source_id'],adj['chunk_id'])]=adj
  # Full paragraphs persist locally; only exceptional long paragraphs get input parts.
  items=[]
  for c in context.values():
   for part in build_units([c],max_bytes=24000):
    items.append(dict(chunk_id=c['chunk_id'],source_id=c['source_id'],text=part['text'],char_start=part['char_start'],char_end=part['char_end'],pages=c['pages'],section=c.get('section'),document_year=sources[c['source_id']].get('report_year'),evidence_issues=c.get('evidence_issues',[])))
  batches=[];batch=[];size=0
  for item in items:
   n=len(json.dumps(item,ensure_ascii=False).encode())
   if batch and size+n>48000:batches.append(batch);batch=[];size=0
   batch.append(item);size+=n
  if batch:batches.append(batch)
  if not batches:batches=[[]]
  reports=[]
  for number,batch in enumerate(batches):
   candidate={}
   compact=[]
   for i,x in enumerate(batch):
    ref='p'+str(i+1).zfill(3);candidate[ref]=x
    compact.append({k:v for k,v in dict(x,ref_id=ref).items() if k not in {'chunk_id','source_id'}})
   def validate(obj):
    cards=obj['evidence'];ids={c['local_id'] for c in cards}
    if len(ids)!=len(cards):raise ValueError('Duplicate evidence IDs')
    for card in cards:
     ref=card.get('ref_id')
     if ref not in candidate or not card.get('quote') or norm(card['quote']) not in norm(candidate[ref]['text']):raise ValueError('Quote does not match supplied paragraph ref_id')
     card['source_id']=candidate[ref]['source_id'];card['chunk_id']=candidate[ref]['chunk_id']
     if card.get('kind') not in {'policy','mechanism','action','result','plan','boundary'}:raise ValueError('Invalid evidence kind')
     for key in ['period','scope','relevance']:
      if not isinstance(card.get(key),str):raise ValueError('Missing evidence field')
    gs=obj['groups']
    if len(gs)!=5 or {g['group_id'] for g in gs}!={g['group_id'] for g in groups}:raise ValueError('Group IDs mismatch')
    for g in gs:
     if type(g['content_sufficient']) is not bool or not set(g['evidence_ids'])<=ids:raise ValueError('Invalid group assessment')
     if g['content_sufficient'] and not g['evidence_ids']:raise ValueError('Sufficiency needs evidence')
     if not all(isinstance(g[k],list) for k in ['missing','conflicts','supported_paths']):raise ValueError('Invalid gap fields')
   prompt='检索取证与缺项判断，不评分。按允许路径判断，满足任一路径即可；不得凑齐所有例子。相关不等于条件成立。不得由文档年度推断每条事实年度。E5/T5/W5需当期实际事实；费用确认不自动等于支付。引文只用输入中的连续原文，可用同一证据支持多组。未说明的期间/范围写未明确；未说明条件列missing。不宣称查完，不输出分数。输出{"evidence":[{"local_id":"e1","ref_id":"输入短编号如p001","quote":"连续短引文","kind":"policy/mechanism/action/result/plan/boundary","period":"原文期间或未明确","scope":"原文范围或未明确","relevance":"直接事实"}],"groups":[{"group_id":"原ID","content_sufficient":false,"supported_paths":[],"evidence_ids":[],"missing":[],"conflicts":[]}]}。'
   reports.append(llm.ask('evidence_gap_'+indicator.replace(' ','_')+'_'+str(number),prompt,dict(groups=groups,general_rules=config['general_rules'],paragraphs=compact,coverage='候选批次；非全文覆盖'),validate))
  for group in groups:
   gid=group['group_id'];assessments=[next(g for g in obj['groups'] if g['group_id']==gid) for obj in reports];evidence={}
   for obj,assessment in zip(reports,assessments):
    cardmap={e['local_id']:e for e in obj['evidence']}
    for lid in assessment['evidence_ids']:
     e=cardmap[lid];c=lookup[(e['source_id'],e['chunk_id'])];eid=e['chunk_id']+'_'+hashlib.sha256((e['source_id']+norm(e['quote'])).encode()).hexdigest()[:12]
     evidence[eid]=dict(evidence_id=eid,chunk_id=e['chunk_id'],quote=e['quote'],source=sources[e['source_id']],location=dict(pages=c['pages'],printed_pages=c.get('printed_pages',[]),section=c.get('section'),bboxes=c.get('bboxes',[])),quote_match=None,parsed_text_match=True,period=e['period'],scope=e['scope'],relevance=e['relevance'],kind=e['kind'])
   records.append(dict(indicator_id=indicator,group_id=gid,evidence=list(evidence.values()),search_log=[dict(source_id=sid,title=sources[sid]['title'],source_level=1,url=sources[sid]['original_url'],version=sources[sid].get('version'),topic=group['topic'],viewed_chunk_ids=[c['chunk_id'] for c in context.values() if c['source_id']==sid],query=qm[gid]['main_query'],open_status='parsed_local_file',result='candidate_review_only') for sid in {c['source_id'] for c in context.values()}],search_complete=False,retrieval_status='pending_review',issues=['首轮候选核查未完成正文、附录、表格、脚注及其他官方材料覆盖','quote_match未完成PDF原页核验'],assessment=dict(content_sufficient=any(g['content_sufficient'] for g in assessments),supported_paths=list(dict.fromkeys(p for g in assessments for p in g['supported_paths'])),missing=[] if any(g['content_sufficient'] for g in assessments) else list(dict.fromkeys(m for g in assessments for m in g['missing'])),missing_by_batch=[g['missing'] for g in assessments],cross_batch_joint_assessment_required=len(reports)>1 and not any(g['content_sufficient'] for g in assessments),conflicts=[x for g in assessments for x in g['conflicts']],coverage_complete=False)))
  save(out/'partial_records.json',records)
 save(out/'candidate_rankings.json',pool_log)
 source=next(iter(sources.values()))
 result=dict(configuration_id=config['configuration_id'],company_id=code,company_name=source['company_name'],year=2025,context=dict(default_scope='集团合并员工；证据范围按原文',comparison_period=None,material_cutoff=None,cutoff_status='not_confirmed',actual_retrieval_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),peer_scope='随机10家样本；本次仅翰森L1试跑'),records=records,checks=[dict(indicator_id=i,check_id='official_adverse_event',evidence=[],search_log=[],search_complete=False,retrieval_status='pending_review',issues=['独立核查尚未执行']) for i in ['S1.1.2 C','S1.1.3','S1.1.4','S1.1.5']])
 save(out/'retrieval_result.json',result)
 save(out/'summary.json',dict(company_id=code,groups=len(records),evidence_references=sum(len(r['evidence']) for r in records),scoring_executed=False,coverage_complete=False))
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path,required=True);p.add_argument('--company',default='03692');a=p.parse_args();run(a.index,a.output,a.env_file,a.company)
if __name__=='__main__':main()

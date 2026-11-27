import hashlib,json,time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
from retrieval.configuration import configuration
from retrieval.run_l1 import rows,save,round_robin
from retrieval.hybrid import build_pool,select_without_reranker
from retrieval.llm import LLM
from indexing.embedding import Embedding
from indexing.bm25 import BM25,tokenize
from fullflow.evidence import extract,verify,assess,compact
from fullflow.web import search,acquire,allowed
from fullflow.scoring import score_indicator
from fullflow.gates import evidence_gate,bind_decisive_evidence
ROOT=Path(__file__).resolve().parents[1]
INDICATORS=['S1.1.1 C','S1.1.2 C','S1.1.3','S1.1.4','S1.1.5']
CHECK_TOPICS={'S1.1.2 C':'严重欠薪、违法克扣工资、补发及纠正','S1.1.3':'严重超时工作、违法剥夺休息休假及纠正','S1.1.4':'严重员工福利或社会保障权益侵害及纠正','S1.1.5':'严重歧视、骚扰、系统性机会不公平及处置补救'}

def merge(cards):
 result={}
 for e in cards:
  if e['evidence_id'] in result:
   result[e['evidence_id']]['group_ids']=list(dict.fromkeys(result[e['evidence_id']]['group_ids']+e['group_ids']))
  else:result[e['evidence_id']]=e
 return list(result.values())

def query_config(llm,config,path):
 def validate(obj):
  if len(obj.get('groups',[]))!=25 or {g.get('group_id') for g in obj['groups']}!={g['group_id'] for g in config['groups']}:raise ValueError('Query groups mismatch')
  if any(not isinstance(g.get('queries'),list) or not 1<=len(g['queries'])<=3 or any(not isinstance(q,str) or not q.strip() for q in g['queries']) for g in obj['groups']):raise ValueError('Invalid query count')
 obj=llm.ask('fullflow_queries','根据最新检索主题及判据，每组生成1条主查询及最多2条互补查询，包含中英同义词，不强制所有段落标2025。保留任一路径成立逻辑。输出{"groups":[{"group_id":"E1","queries":["主查询","补查"]}]}。',config,validate)
 save(path,obj);return {g['group_id']:g['queries'] for g in obj['groups']}

def screen_failed_official_sources(llm,indicator,logs,issues,company):
 # An inaccessible discovery result is not automatically a necessary case original.
 # Only clearly generic documents can be excluded from metadata; uncertainty stays blocking.
 import copy
 logs=copy.deepcopy(logs);issues=copy.deepcopy(issues);excluded=set()
 for log in logs:
  for entry in log.get('opened_sources',[]):
   if entry.get('reason')!='official_source_unreadable':continue
   title=entry.get('title','').strip();url=entry.get('url')
   if not title:continue
   names=[company.get('company_name',''),company.get('company_id','')]
   generic=title.strip('《》') in {'市场监督管理行政处罚信息公示规定','市場監督管理行政處罰信息公示規定'} and not any(n and n in title for n in names)
   if not generic:
    def validate_relevance(obj):
     if obj.get('classification') not in {'generic_reference','company_case_candidate','uncertain'} or not isinstance(obj.get('basis'),str):raise ValueError('Invalid source relevance decision')
    decision=llm.ask('failed_source_relevance','仅对无法打开的搜索候选做保守材料类型筛查，不认定违规、不根据搜索摘要认定无违规。明确是通用法规、政策解读、网站首页或一般统计页面且不含公司案件线索，才可返回generic_reference；公司或关联主体案件线索返回company_case_candidate；标题不足、关联不清返回uncertain。generic_reference仅表示此页面不是必要案件原件，不能证明已完成检索。输出{"classification":"generic_reference/company_case_candidate/uncertain","basis":"具体依据"}。',dict(company=company,topic=CHECK_TOPICS[indicator],title=title,url=url),validate_relevance,max_tokens=800)
    if decision['classification']!='generic_reference':
     entry.update(blocks_this_check=True,relevance_decision=decision['classification'],relevance_basis=decision['basis']);continue
   entry.update(blocks_this_check=False,relevance_decision='excluded_generic_regulation',relevance_basis='标题明确为通用信息公示规定，不是该公司严重事项案件原件；读取失败仅记录，不阻塞。')
   excluded.add(url)
 issues=[x for x in issues if not (isinstance(x,dict) and x.get('kind')=='official_source_unreadable' and x.get('url') in excluded)]
 return logs,issues

def judge_independent(llm,indicator,cards,logs,issues,rules,company,out):
 if not cards and any(log.get('result')=='No supplied L4 regulatory/judicial notice index' for log in logs):
  return dict(indicator_id=indicator,check_id='official_adverse_event',evidence=[],search_log=logs,search_complete=False,retrieval_status='pending_review',issues=issues,judgment=dict(state='pending_review',reason='缺少L4材料索引，无法确认官方核查覆盖；未调用模型。',evidence_ids=[],unresolved=list(issues)))
 logs,issues=screen_failed_official_sources(llm,indicator,logs,issues,company)
 refs,data=compact(cards)
 def validate(obj):
  if obj.get('state') not in {'no_verified_adverse_event_found','verified_uncorrected','verified_corrected','pending_review'}:raise ValueError('Invalid official check state')
  if not set(obj.get('evidence_refs',[]))<=refs.keys():raise ValueError('Unknown official evidence ref')
  if obj['state'] in {'verified_uncorrected','verified_corrected'} and not obj.get('evidence_refs'):raise ValueError('Official finding requires evidence')
 obj=llm.ask('independent_judgment_'+indicator.replace(' ','_'),'独立核查，仅依据已打开的官方原文判断主体关联、事项性质、期间、严重性及有效纠正。投诉、和解、撤诉、职工债权公示和未披露整改不能单独证明严重事项或未纠正。不得由公司名称相似认定子公司关系。本阶段只核查严重事项及纠正，不重新索取P/T/W/D普通政策组证据，不评价普通组得分。没有严重通报候选不代表普通政策披露缺失。日志中blocks_this_check=false的通用法规等排除项不是必要案件原件，不得因其读取失败产生unresolved；但也不得以排除项证明覆盖完成。只有与公司及对应严重事项有关或关系尚不清楚的必要案件原件读取失败才阻塞。若实际搜索日志确认规定官方查找已执行、必要原件已打开且无未决问题，可返回no_verified_adverse_event_found，理由限定为本次已查范围未找到，不证明没有发生。输出{"state":"no_verified_adverse_event_found/verified_uncorrected/verified_corrected/pending_review","reason":"明确依据及限制","evidence_refs":[],"unresolved":[]}。',dict(company=company,indicator=indicator,topic=CHECK_TOPICS[indicator],rules=rules,evidence=data,coverage_issues=issues,actual_search_log=logs,search_count=len(logs)),validate,max_tokens=4000)
 linked=[refs[r]['evidence_id'] for r in obj.pop('evidence_refs')];obj['evidence_ids']=linked
 if obj['state'] in {'verified_uncorrected','verified_corrected'} and not any(e['quote_match'] is True and e['evidence_id'] in linked for e in cards):obj['state']='pending_review';issues.append('official_quote_not_verified')
 if issues or obj.get('unresolved'):obj['state']='pending_review'
 coverage_incomplete=any((isinstance(x,str) and ('unconfirmed' in x or 'failed' in x or 'scanned' in x)) or (isinstance(x,dict) and x.get('kind')=='official_source_unreadable') for x in issues)
 return dict(indicator_id=indicator,check_id='official_adverse_event',evidence=cards,search_log=logs,search_complete=not coverage_incomplete,retrieval_status='pending_review' if obj['state']=='pending_review' else 'relevant_evidence_found' if cards else 'no_relevant_evidence_found',issues=issues,judgment=obj)

class Engine:
 def __init__(self,index,out,env_file,query_map,config):
  self.index=index;self.out=out;self.config=config;self.llm=LLM(env_file,out/'calls');self.embed=Embedding(index/'embedding_cache',env_file);self.queries=query_map
  self.rules=(ROOT/'S1.1 大模型评分规则.md').read_text();self.sources={};self.locations={};self.logs=defaultdict(list);self.cards=[];self.issues=defaultdict(list);self.assessments={};self.coverage={};self.source_levels_visited=[];self.read_chunks=defaultdict(set);self.assessment_inputs={}
 def take(self,groups,cards,issues,viewed,level,mode):
  for e in cards:
   e['quote_match'],e['quote_verification_method']=verify(e)
  self.cards=merge(self.cards+cards)
  for g in groups:
   gid=g['group_id'];self.read_chunks[gid].update((v[0],v[1]) for v in viewed);selected=[c for c in self.cards if gid in c['group_ids']]
   self.issues[gid].extend(x for x in issues if gid in x.get('group_ids',[]))
   for sid in sorted({v[0] for v in viewed}):
    src=self.sources[sid];v=[x for x in viewed if x[0]==sid]
    self.logs[gid].append(dict(source_id=sid,title=src['title'],source_kind=src['source_kind'],source_level=level,version=src.get('version'),url=src['original_url'],topic=g['topic'],pages=sorted({p for _,cid,_,_ in v for p in self.locations.get((sid,cid),[])}),viewed_parts=[dict(chunk_id=c,start=a,end=b) for _,c,a,b in v],open_status='opened',extraction_status='parsed',mode=mode,result='matching_evidence_found' if any(e['source']['source_id']==sid for e in selected) else 'no_relevant_quote_in_viewed_parts'))
 def unread(self,group,chunks):
  # Reading for another target does not establish coverage for this target.
  seen=self.read_chunks[group['group_id']]
  return [c for c in chunks if (c['source_id'],c['chunk_id']) not in seen]
 def unresolved(self,groups):
  return [g for g in groups if not self.assessments.get(g['group_id'],{}).get('verified_support_sufficient',False) or self.assessments.get(g['group_id'],{}).get('conflicts')]
 def evaluate(self,groups,stage):
  changed=[];fingerprints={}
  for g in groups:
   gid=g['group_id']
   relevant=[c for c in self.cards if gid in c['group_ids']]
   payload=dict(group=g,rules=self.config['general_rules'],evidence=sorted(relevant,key=lambda c:c['evidence_id']),issues=self.issues[gid])
   fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   if gid not in self.assessments or self.assessment_inputs.get(gid)!=fingerprint:
    changed.append(g);fingerprints[gid]=fingerprint
  for indicator in dict.fromkeys(g['indicator_id'] for g in changed):
   gs=[g for g in changed if g['indicator_id']==indicator];gids={g['group_id'] for g in gs};cards=[c for c in self.cards if set(c['group_ids'])&gids]
   result=assess(self.llm,gs,cards,self.config['general_rules'],stage+'_'+indicator.replace(' ','_'),candidate_issues=[x for g in gs for x in self.issues[g['group_id']]])
   self.assessments.update({g['group_id']:g for g in result})
   self.assessment_inputs.update({g['group_id']:fingerprints[g['group_id']] for g in gs})
 def ordinary_level(self,company,level,groups,substage=None):
  save(self.out/'progress.json',dict(stage='ordinary_retrieval',level=level,substage=substage,active_groups=[g['group_id'] for g in groups]))
  base=self.index/company['company_id']/f'L{level}'
  if not base.exists():
   for g in groups:self.issues[g['group_id']].append(dict(kind='missing_layer_index',level=level))
   return
  manifest=json.loads((base/'manifest.json').read_text())
  if not manifest.get('vector_ready') or manifest['model']!=self.embed.model:raise ValueError('Dense index unavailable or wrong model')
  sources={s['source_id']:s for s in rows(base/'sources.jsonl')};self.sources.update(sources)
  chunks=rows(base/'chunks.jsonl');units=rows(base/'units.jsonl');vectors=np.load(base/'embeddings.npy');tokens=rows(base/'bm25_tokens.jsonl')
  if substage:
   is_exchange=lambda sid:'hkexnews.hk' in (urlsplit(sources[sid]['original_url']).hostname or '')
   allowed_sources={sid for sid in sources if is_exchange(sid)==(substage=='exchange')}
   positions=[i for i,u in enumerate(units) if u['source_id'] in allowed_sources]
   units=[units[i] for i in positions];vectors=vectors[positions];tokens=[tokens[i] for i in positions]
   chunks=[c for c in chunks if c['source_id'] in allowed_sources];sources={k:v for k,v in sources.items() if k in allowed_sources}
  if not units:return
  self.locations.update({(c['source_id'],c['chunk_id']):c['pages'] for c in chunks});bm=BM25([r['tokens'] for r in tokens]);lookup={(c['source_id'],c['chunk_id']):c for c in chunks};corpus=[dict(u,paragraph_id=u['source_id']+':'+u['unit_id']) for u in units]
  planned={g['group_id']:list(self.queries[g['group_id']][:3]) for g in groups}
  for g in groups:
   if len(planned[g['group_id']])==1:planned[g['group_id']].append(g['topic']+' '+g['condition'])
  completed_queries={g['group_id']:[planned[g['group_id']][0]] for g in groups}
  qlist=[(g['group_id'],self.queries[g['group_id']][0]) for g in groups];qvectors=self.embed.encode([q for _,q in qlist]);rankings={};trace={}
  for (gid,q),qv in zip(qlist,qvectors):
   pool=build_pool(corpus,bm.scores(tokenize(q)),vectors@qv,150,{})
   rankings[gid]=select_without_reranker(pool,{},50)
   trace[gid]=[dict(unit_id=c['unit_id'],source_id=c['source_id'],parent_chunk_id=c['parent_chunk_id'],bm25_rank=c['bm25_rank'],dense_rank=c['dense_rank'],score=c['composite_score']) for c in rankings[gid]]
  for indicator in dict.fromkeys(g['indicator_id'] for g in groups):
   gs=[g for g in groups if g['indicator_id']==indicator];selected=round_robin([rankings[g['group_id']] for g in gs],18)
   context={}
   for u in selected:
    c=lookup[(u['source_id'],u['parent_chunk_id'])];context[(c['source_id'],c['chunk_id'])]=c
    for cid in [c.get('prev_chunk_id'),c.get('next_chunk_id')]+c.get('note_candidates',[]):
     adj=lookup.get((c['source_id'],cid))
     if adj and adj.get('section')==c.get('section'):context[(adj['source_id'],adj['chunk_id'])]=adj
   cards,issues,viewed=extract(self.llm,gs,list(context.values()),sources,f'L{level}_initial_'+indicator.replace(' ','_'));self.take(gs,cards,issues,viewed,level,'hybrid_initial')
  self.evaluate(groups,f'L{level}_initial_assessment')
  unresolved=[g for g in groups if not self.assessments[g['group_id']].get('verified_support_sufficient',False) or self.assessments[g['group_id']]['conflicts']]
  # Stop satisfied targets after each round; send only previously unread parents.
  for round_no in (1,2):
   if not unresolved:break
   extra={};targets=[]
   for g in unresolved:
    queries=planned[g['group_id']]
    if round_no>=len(queries):continue
    q=queries[round_no];qv=self.embed.encode([q])[0]
    ranked=select_without_reranker(build_pool(corpus,bm.scores(tokenize(q)),vectors@qv,150,{}),{},50)
    completed_queries[g['group_id']].append(q)
    has_new=False
    for u in ranked[:10]:
     c=lookup[(u['source_id'],u['parent_chunk_id'])]
     if self.unread(g,[c]):
      extra[(c['source_id'],c['chunk_id'])]=c;has_new=True
    if has_new:targets.append(g)
   self.extract_supplement(targets,list(extra.values()),sources,level,round_no)
   self.evaluate(unresolved,f'L{level}_supplement_{round_no}_assessment')
   unresolved=self.unresolved(unresolved)
  for g in groups:
   gid=g['group_id'];self.coverage.setdefault(gid,[]).append(dict(level=level,source_ids=list(sources),indexed_content_reviewed=False,retrieval_completed=True,supplementary_completed=len(completed_queries[gid])==len(planned[gid]),coverage_mode='local_rag_v2',substage=substage,planned_query_count=len(planned[gid]),completed_query_count=len(completed_queries[gid]),queries=completed_queries[gid],bm25_top_k=150,dense_top_k=150,fused_top_k=50,chunk_count=len(chunks)))
  self.source_levels_visited.append(level)
  save(self.out/f'L{level}_{substage or "main"}_checkpoint.json',dict(assessments=self.assessments,evidence=self.cards,coverage=self.coverage,logs=self.logs,issues=self.issues,ranking_trace=trace))
 def extract_supplement(self,groups,chunks,sources,level,round_no):
  if not groups or not chunks:return
  unique={(c['source_id'],c['chunk_id']):c for c in chunks}
  cards,issues,viewed=extract(self.llm,groups,list(unique.values()),sources,f'L{level}_supplement_{round_no}')
  self.take(groups,cards,issues,viewed,level,'supplementary_query')
 def official_discovery(self,company,groups,level,indicator=None,website_only=False):
  # L2/L3 local originals are already retrieved through ordinary_level.
  if level!=4:return [],[],[]
  base=self.index/company['company_id']/'L4'
  if not (base/'manifest.json').exists():
   return [],[dict(source_type='local_rag',source_level=4,network_search_executed=False,result='No supplied L4 regulatory/judicial notice index')],['local_only_official_coverage_unconfirmed']
  sources={s['source_id']:s for s in rows(base/'sources.jsonl')};chunks=rows(base/'chunks.jsonl');units=rows(base/'units.jsonl');vectors=np.load(base/'embeddings.npy');tokens=rows(base/'bm25_tokens.jsonl')
  corpus=[dict(u,paragraph_id=u['source_id']+':'+u['unit_id']) for u in units];bm=BM25([r['tokens'] for r in tokens]);query=CHECK_TOPICS[indicator];qv=self.embed.encode([query])[0]
  ranked=select_without_reranker(build_pool(corpus,bm.scores(tokenize(query)),vectors@qv,150,{}),{},50)
  lookup={(c['source_id'],c['chunk_id']):c for c in chunks};selected={}
  for u in ranked[:30]:
   c=lookup[(u['source_id'],u['parent_chunk_id'])];selected[(c['source_id'],c['chunk_id'])]=c
   for cid in [c.get('prev_chunk_id'),c.get('next_chunk_id')]+c.get('note_candidates',[]):
    adj=lookup.get((c['source_id'],cid))
    if adj and adj.get('section')==c.get('section'):selected[(adj['source_id'],adj['chunk_id'])]=adj
  cards,issues,viewed=extract(self.llm,groups,list(selected.values()),sources,'local_L4_'+indicator.replace(' ','_'))
  for e in cards:e['quote_match'],e['quote_verification_method']=verify(e)
  logs=[dict(source_type='local_hybrid_rag',source_level=4,network_search_executed=False,query=query,source_ids=list(sources),retrieved_units=[u['unit_id'] for u in ranked[:30]],retrieved_parent_count=len(selected))]
  issues.append('local_only_official_coverage_unconfirmed')
  return merge(cards),logs,issues
 def checks(self,company):
  # Explicitly collected HKEX discovery is read locally. No broad web search.
  hkex=ROOT/'runs/hkex_l4'/company['company_id']/'checks.json'
  if hkex.exists():
   result=json.loads(hkex.read_text())
   if len(result)!=4 or {c['indicator_id'] for c in result}!=set(CHECK_TOPICS):raise ValueError('Invalid HKEX check coverage')
   save(self.out/'independent_checks.json',result)
   return result
  result=[]
  for indicator in CHECK_TOPICS:
   save(self.out/'progress.json',dict(stage='independent_official_check',indicator_id=indicator))
   gs=[g for g in self.config['groups'] if g['indicator_id']==indicator]
   cards,logs,issues=self.official_discovery(company,gs,4,indicator)
   # Existing scan remains a real unresolved official lead, never silently discarded.
   scan=self.index.parent/'auxiliary_local_index'/company['company_id']/'L4'
   if scan.exists():
    scan_sources=rows(scan/'sources.jsonl');logs.append(dict(source_id=scan_sources[0]['source_id'],url=scan_sources[0]['original_url'],open_status='scanned_pdf_with_local_ocr',location='pages 1-5',result='requires_visual_and_subject_verification'))
    financial_claim=any(t in scan_sources[0].get('title','') for t in ('职工债权','職工債權'))
    if not financial_claim or indicator in {'S1.1.2 C','S1.1.4'}:
     issues.append('existing_official_scanned_lead_requires_quote_and_subject_review')
    else:
     logs[-1]['result']='financial_claim_lead_not_direct_evidence_for_this_check'
     logs[-1]['blocks_this_check']=False
   check=judge_independent(self.llm,indicator,cards,logs,issues,self.rules,company,self.out);result.append(check);save(self.out/'independent_checks.json',result)
  return result
 def run(self,company):
  active=list(self.config['groups'])
  for level in (1,2,3):
   if not active:break
   if level!=3:self.ordinary_level(company,level,active)
   else:
    self.ordinary_level(company,3,active,substage='website')
    unresolved=[g for g in active if not self.assessments.get(g['group_id'],{}).get('verified_support_sufficient',False) or self.assessments.get(g['group_id'],{}).get('conflicts')]
    if unresolved:
     cards,logs,issues=self.official_discovery(company,unresolved,3,website_only=True)
     self.cards=merge(self.cards+cards)
     for g in unresolved:self.logs[g['group_id']].extend(logs);self.issues[g['group_id']].extend(issues)
     self.evaluate(unresolved,'L3_website_web_assessment')
     unresolved=[g for g in unresolved if not self.assessments.get(g['group_id'],{}).get('verified_support_sufficient',False) or self.assessments.get(g['group_id'],{}).get('conflicts')]
    if unresolved:
     self.ordinary_level(company,3,unresolved,substage='exchange')
     cards,logs,issues=self.official_discovery(company,unresolved,3)
     self.cards=merge(self.cards+cards)
     for g in unresolved:self.logs[g['group_id']].extend(logs);self.issues[g['group_id']].extend(issues)
     self.evaluate(unresolved,'L3_final_web_assessment')
   active=[g for g in active if not self.assessments.get(g['group_id'],{}).get('verified_support_sufficient',False) or self.assessments.get(g['group_id'],{}).get('conflicts')]
  refs,cards=compact(self.cards)
  def validate_conflicts(obj):
   if not isinstance(obj.get('conflicts'),list):raise ValueError('Invalid conflict report')
   for c in obj['conflicts']:
    if not set(c.get('group_ids',[]))<={g['group_id'] for g in self.config['groups']} or not set(c.get('evidence_refs',[]))<=refs.keys() or len(c.get('evidence_refs',[]))<2:raise ValueError('Conflict needs valid groups and two evidence references')
  conflicts=dict(conflicts=[],skipped_reason='fewer_than_two_evidence_records') if len(cards)<2 else self.llm.ask('cross_indicator_consistency','检查不同指标证据是否对同一主体、同一期间、同一事项产生影响判分的实质矛盾。不同地区、不同年度、费用与支付等口径差异不能擅自当矛盾。没有实质冲突也必须返回JSON对象 {"conflicts":[]}，不能返回裸数组[]。输出{"conflicts":[{"group_ids":[],"evidence_refs":[],"reason":"实质冲突"}]}。',dict(company=company,evidence=cards),validate_conflicts,max_tokens=4000)
  for c in conflicts['conflicts']:
   for gid in c['group_ids']:
    self.assessments.setdefault(gid,dict(content_sufficient=False,missing=[],conflicts=[]))['conflicts'].append(c['reason'])
  save(self.out/'cross_indicator_conflicts.json',conflicts)
  checks=self.checks(company);records=[]
  for g in self.config['groups']:
   gid=g['group_id'];a=dict(self.assessments.get(gid,dict(content_sufficient=None,missing=['未完成内容判断'],conflicts=[])),group_id=gid);evidence=sorted(bind_decisive_evidence(gid,a,self.cards),key=lambda c:(c['source']['source_level'],c['quote_match'] is not True));coverage=self.coverage.get(gid,[])
   issues=list(self.issues[gid])
   if a.get('conflicts'):issues.append(dict(kind='material_fact_conflict',details=a['conflicts']))
   gate=evidence_gate(a,evidence,issues,coverage)
   input_issues=list(issues)
   if not gate['search_complete']:issues.append('necessary_material_coverage_not_confirmed')
   if gate['critical_unverified']:issues.append(dict(kind='decision_relevant_quote_unverified',evidence_or_chunk_ids=gate['critical_unverified']))
   if gate['ancillary_unverified_ids']:issues.append(dict(kind='ancillary_quote_unverified',evidence_ids=gate['ancillary_unverified_ids'],blocks_verified_support=False))
   records.append(dict(indicator_id=g['indicator_id'],group_id=gid,evidence=evidence,search_log=self.logs[gid],search_complete=gate['search_complete'],retrieval_status=gate['retrieval_status'],issues=issues,assessment=a,coverage=coverage,decision_input_issues=input_issues,decision_gate=gate))
  result=dict(configuration_id=self.config['configuration_id'],company_id=company['company_id'],company_name=company['company_name'],year=2025,context=dict(scope='集团合并员工；具体证据范围按原文',comparable_period=None,material_cutoff='2026-11-27',actual_retrieval_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),peer_scope='随机5家，仅定性'),records=records,checks=checks)
  save(self.out/'retrieval_result.json',result)
  scores=[]
  for indicator in INDICATORS:
   save(self.out/'progress.json',dict(stage='scoring',indicator_id=indicator))
   gs=[g for g in self.config['groups'] if g['indicator_id']==indicator];rs=[r for r in records if r['indicator_id']==indicator];check=next((c for c in checks if c['indicator_id']==indicator),None)
   scores.append(score_indicator(self.llm,indicator,gs,rs,check,self.rules,company=company));save(self.out/'scores.json',scores)
  return result,scores

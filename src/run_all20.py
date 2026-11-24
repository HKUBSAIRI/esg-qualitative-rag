"""Group-aware retrieval experiment; B scoring prompt and corpus are frozen."""
import concurrent.futures,json,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import run as core
import experiment_B_prompt as b
import importlib.util
score_script=R/'src/固定候选重评分.py'
score_source=score_script.read_text()
extra=score_source[score_source.index("core.PROMPTS['score'] +="):score_source.index('codes=json.loads')]
exec(extra)
core.PROMPTS['score'] += '\n输出必须含全部五组；每组理由不超过80字，每组最多一条原文引用，引用最多60字。'
import run_updated_baseline as rb
from esg_qualitative_rag.core import BM25,build_pool,select_without_reranker,tokenize
codes=json.loads((R/'inputs/all20_codes.json').read_text());inds=list(dict.fromkeys(g['indicator'] for g in core.GROUPS));companies={x['code']:x['company'] for x in json.loads((R/'inputs/companies.json').read_text())}
queries=[];byind={}
for ind in inds:
 gs=[g for g in core.GROUPS if g['indicator']==ind];rub=rb.make_rubric(ind,gs);words=dict(rub.recall_groups)
 byind[ind]=[f"2025员工权益；{g['name']}；{g['positive']}；相关表达："+'、'.join(words.get(g['id'],())[:12]) for g in gs];queries+=byind[ind]
shared=core.API(codes[0]);shared.dest=R/'outputs/all20_shared_embedding_trace'
try:query_vectors=shared.embed(queries)
finally:shared.client.close();shared.embedding_client.close()
query_map={q:v for q,v in zip(queries,query_vectors)}
def work(code):
 if all((R/'runs'/code/'revised_gt_cases'/(ind+'.json')).exists() for ind in inds): return
 dest=R/'runs'/code;chunks=json.loads((dest/'chunks.json').read_text());api=core.API(code);api.dest=dest/'all20_embedding_trace'
 try:
  corpus=[dict(c,paragraph_id=c['id'],retrieval_text='[Section]\n'+(c.get('section') or '')+'\n\n[Content]\n'+c['text']) for c in chunks]
  bm25=BM25([tokenize(c['retrieval_text']) for c in corpus]);vec=api.embed([c['retrieval_text'] for c in corpus]);api.dest=dest/'revised_gt_cases_trace'
  for ind in inds:
   out=dest/'revised_gt_cases'/(ind+'.json')
   if out.exists():continue
   groups=[g for g in core.GROUPS if g['indicator']==ind];rankings=[]
   for g,q in zip(groups,byind[ind]):
    # Search each group independently; keep the existing mixed-score machinery.
    pool=build_pool(corpus,bm25.scores(tokenize(q)),vec@query_map[q],150,{})
    ranked=select_without_reranker(pool,{},50);rankings.append(ranked)
   chosen=[];seen=set();group_selected={g['id']:[] for g in groups}
   for rank in range(3):
    for g,ranked in zip(groups,rankings):
     for c in ranked:
      if c['id'] not in seen:
       chosen.append(c);seen.add(c['id']);group_selected[g['id']].append(c['id']);break
   # Fill remaining seats using candidates' within-group ranks, preserving diversity.
   for rank in range(50):
    for ranked in rankings:
     if len(chosen)>=18:break
     if rank<len(ranked) and ranked[rank]['id'] not in seen:
      chosen.append(ranked[rank]);seen.add(ranked[rank]['id'])
    if len(chosen)>=18:break
   paragraphs=[{'chunk_id':c['id'],'pages':c['pages'],'source_kind':c['source_kind'],'period':c.get('classification',{}),'text':c['text']} for c in chosen]
   core.save(dest/'retrieval_group_opt'/(ind+'_retrieval.json'),{'queries':dict(zip([g['id'] for g in groups],byind[ind])),'chunk_ids':[c['id'] for c in chosen],'group_selected':group_selected,'sources':[c['source_id'] for c in chosen]})
   data={'company':companies[code],'year':2025,'rules':core.GENERAL+'\n'+core.indicator_rules(ind),'groups':groups,'paragraphs':paragraphs}
   for n in range(3):
    z=api.ask('score',data,'group_opt_'+ind+'_run'+str(int(time.time()))+'_retry'+str(n),max_tokens=16000);items=z.get('groups',[])
    if len(items)==5 and {g.get('group_id') for g in items}=={g['id'] for g in groups} and all(type(g.get('score')) is int and g['score'] in (0,100) for g in items):break
   else:raise ValueError('invalid score '+ind)
   lut={c['id']:c for c in chosen}
   for g in items:
    for e in g.get('evidence',[]):
     c=lut.get(e.get('chunk_id'),{});e['pages']=c.get('pages',[]);e['exact_match']=bool(e.get('quote') and core.norm(e['quote']) in core.norm(c.get('text','')))
   score=sum(g['score'] for g in items)/5;z.update(company_id=code,indicator=ind,base_score=score,final_score=score,method='revised_gt_cases')
   if z.get('serious',{}).get('state')=='verified_uncorrected':z['final_score']=None;z['serious']['state']='pending_review'
   core.save(out,z);print(code,ind,z['final_score'],flush=True)
 finally:api.client.close();api.embedding_client.close()
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
  fs={pool.submit(work,c):c for c in codes}
  for f in concurrent.futures.as_completed(fs):
   try:f.result()
   except Exception as e:print('FAILED',fs[f],type(e).__name__,str(e)[:200],flush=True);raise

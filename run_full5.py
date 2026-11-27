"""Authorized five-company qualitative flow. Resumable API checkpoints, no quantitative scores."""
import argparse,fcntl,hashlib,json,random,time,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from retrieval.configuration import configuration
from retrieval.run_l1 import save
from retrieval.llm import LLM
from fullflow.engine import Engine,query_config,INDICATORS
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',type=Path,required=True);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
 out=ROOT/'runs/full5_20261127';out.mkdir(parents=True,exist_ok=True)
 lock=(out/'run.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another full5 process is active')
 config=configuration();rules=(ROOT/'S1.1 大模型评分规则.md').read_text();retrieval_rules=(ROOT/'S1.1 检索规则.md').read_text()
 population=json.loads((ROOT/'runs/random10_20261127/selection.json').read_text())['selected']
 selected=[dict(company_id=x['code'],company_name=x['company']) for x in random.Random(20261127).sample(population,5)]
 assert [c['company_id'] for c in selected]==['03692','01801','02269','01177','06185']
 index_root=ROOT/'runs/local_material_rag/index'
 index_versions={}
 for company in selected:
  for level in (1,2,3):
   path=index_root/company['company_id']/f'L{level}'/'manifest.json'
   m=json.loads(path.read_text()) if path.exists() else dict(corpus_sha256=None,model=None,dimensions=None);index_versions[f"{company['company_id']}/L{level}"]={k:m[k] for k in ('corpus_sha256','model','dimensions')}
 code_versions={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'fullflow').glob('*.py'))+[ROOT/'retrieval/llm.py']}
 fingerprint=hashlib.sha256(json.dumps(dict(config=config,index_versions=index_versions,code_versions=code_versions),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 save(out/'protocol.json',dict(model='qwen3.8-flash',embedding_model='text-embedding-3-small',dimension=1024,year=2025,cutoff='2026-11-27',selection_seed=20261127,population=[x['code'] for x in population],selected=selected,configuration_hash=fingerprint,index_versions=index_versions,code_versions=code_versions,search_backend='local_hybrid_rag_no_online_discovery',groups=25,independent_checks=4,quantitative=False,workers=a.workers,workflow_version='fullflow-v1'))
 (out/'评分规则快照.md').write_text(rules);(out/'检索规则快照.md').write_text(retrieval_rules)
 status=out/'completion_status.json';save(status,dict(state='generating_queries',companies=selected,scoring_enabled=True))
 llm=LLM(a.env_file,out/'shared_calls');queries=query_config(llm,config,out/'queries.json');index=ROOT/'runs/local_material_rag/index'
 def work(company):
  folder=out/company['company_id'];folder.mkdir(parents=True,exist_ok=True);state=folder/'completion_status.json'
  if state.exists():
   previous=json.loads(state.read_text())
   if previous.get('state')=='completed' and previous.get('configuration_hash')==fingerprint and previous.get('workflow_version')=='fullflow-v1':return previous
  for attempt in range(3):
   save(state,dict(state='running',company=company,attempt=attempt+1,configuration_hash=fingerprint))
   try:
    engine=Engine(index,folder,a.env_file,queries,config);retrieval,scores=engine.run(company)
    assert len(retrieval['records'])==25 and len(retrieval['checks'])==4 and len(scores)==5
    result=dict(state='completed',company=company,configuration_hash=fingerprint,workflow_version='fullflow-v1',groups=25,independent_checks=4,verified_groups=sum(g['status']=='verified' for s in scores for g in s['groups']),pending_groups=sum(g['status']=='pending_review' for s in scores for g in s['groups']),final_scores={s['indicator_id']:s['final_score'] for s in scores},retrieval_complete=all(r['search_complete'] for r in retrieval['records']),completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    save(state,result);return result
   except Exception as e:
    with (folder/'errors.log').open('a') as f:f.write(traceback.format_exc()+'\n')
    save(state,dict(state='retrying' if attempt<2 else 'failed',company=company,error_type=type(e).__name__,reason=str(e),configuration_hash=fingerprint,successful_calls_cached=True))
    if attempt<2:time.sleep(10*(attempt+1))
  return json.loads(state.read_text())
 results=[]
 with ThreadPoolExecutor(max_workers=a.workers) as pool:
  futures={pool.submit(work,c):c for c in selected}
  for future in as_completed(futures):
   result=future.result();results.append(result);save(status,dict(state='running' if len(results)<5 else 'completed' if all(r['state']=='completed' for r in results) else 'completed_with_failures',finished_companies=len(results),companies=results))
   print(result['company']['company_id'],result['state'],flush=True)
 save(out/'summary.json',results)
 lines=['# 5家公司定性检索与评分结果','','仅25个定性组，不计算定量项及完整S1.1总分。pending_review不记0；执行完毕不等于全部证据已核验。','','| 企业 | 执行状态 | 已确认组 | 待核验组 | C1 | C2 | T | W | D |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for r in sorted(results,key=lambda x:x['company']['company_id']):
  values=[r.get('final_scores',{}).get(i) for i in INDICATORS]
  lines.append('|'+ '|'.join(map(str,[r['company']['company_name'],r['state'],r.get('verified_groups','—'),r.get('pending_groups','—')]+['待核验' if v is None else v for v in values]))+'|')
 (out/'结果汇总.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()

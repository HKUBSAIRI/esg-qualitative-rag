"""Resume the original ten-company cohort, preserving compatible completed five.

Business logic comes only from this project. L1-L3: local hybrid RAG. L4:
previously collected bounded HKEX checks. Scoring never calls a second LLM.
"""
import argparse,fcntl,hashlib,json,shutil,time,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from fullflow.engine import Engine,INDICATORS
from retrieval.configuration import configuration
from retrieval.run_l1 import save
ROOT=Path(__file__).resolve().parent

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--env-file',type=Path,required=True);parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
 out=ROOT/'runs/full10_20261127';out.mkdir(parents=True,exist_ok=True);lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 old=ROOT/'runs/full5_20261127';previous=json.loads((old/'protocol.json').read_text());config=configuration()
 selected=[dict(company_id=x['code'],company_name=x['company']) for x in json.loads((ROOT/'runs/random10_20261127/selection.json').read_text())['selected']]
 codes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'fullflow').glob('*.py'))+[ROOT/'retrieval/llm.py']}
 # Never reuse a completed result after an unaccounted business-code/rule change.
 compatible=codes==previous['code_versions'] and (old/'评分规则快照.md').read_text()==(ROOT/'S1.1 大模型评分规则.md').read_text() and (old/'检索规则快照.md').read_text()==(ROOT/'S1.1 检索规则.md').read_text()
 index=ROOT/'runs/local_material_rag/index';versions={};hkex_hashes={}
 for c in selected:
  code=c['company_id']
  for level in (1,2,3):
   path=index/code/f'L{level}'/'manifest.json'
   if not path.exists():raise RuntimeError('Index preparation is incomplete: '+str(path))
   m=json.loads(path.read_text());versions[f'{code}/L{level}']={k:m[k] for k in ('corpus_sha256','model','dimensions')}
  check=ROOT/'runs/hkex_l4'/code/'checks.json'
  if not check.exists():raise RuntimeError('HKEX L4 check not prepared: '+code)
  hkex_hashes[code]=hashlib.sha256(check.read_bytes()).hexdigest()
 fingerprint=hashlib.sha256(json.dumps(dict(config=config,index_versions=versions,code_versions=codes,hkex=hkex_hashes),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 save(out/'protocol.json',dict(selected=selected,configuration_hash=fingerprint,index_versions=versions,code_versions=codes,hkex_check_hashes=hkex_hashes,model='qwen3.8-flash',embedding_model='text-embedding-3-small',dimension=1024,quantitative=False,groups_per_company=25,workers=args.workers,workflow_version='local-rag-decision-contract-v1',year=2025,cutoff='2026-11-27',ordinary_network_search=False,l4_source='HKEXnews bounded title and domain content discovery'))
 for filename in ['评分规则快照.md','检索规则快照.md','queries.json']:shutil.copy2(old/filename,out/filename)
 queries={g['group_id']:g['queries'] for g in json.loads((out/'queries.json').read_text())['groups']};results={};pending=[]
 for c in selected:
  code=c['company_id'];folder=out/code;folder.mkdir(exist_ok=True);state=folder/'completion_status.json'
  if state.exists():
   d=json.loads(state.read_text())
   if d.get('state')=='completed' and d.get('configuration_hash')==fingerprint:results[code]=d;continue
  prior=old/code/'completion_status.json';indexes_same=all(versions[f'{code}/L{i}']==previous['index_versions'].get(f'{code}/L{i}') for i in (1,2,3))
  if compatible and indexes_same and prior.exists():
   d=json.loads(prior.read_text())
   if d.get('state')=='completed':
    for filename in ['retrieval_result.json','scores.json','independent_checks.json']:shutil.copy2(old/code/filename,folder/filename)
    d.update(configuration_hash=fingerprint,reused_from=str((old/code).resolve()),reused_without_api=True);save(state,d);results[code]=d;continue
  pending.append(c);save(state,dict(state='queued',company=c,configuration_hash=fingerprint))
 def summarize(state='running'):
  save(out/'summary.json',[results[c['company_id']] for c in selected if c['company_id'] in results]);save(out/'completion_status.json',dict(state=state,finished_companies=len(results),total_companies=10,reused_companies=sum(bool(r.get('reused_from')) for r in results.values()),companies=list(results.values())))
 summarize();print('REUSED',len(results),'TO_RUN',len(pending),flush=True)
 def work(c):
  folder=out/c['company_id'];state=folder/'completion_status.json'
  for attempt in range(3):
   save(state,dict(state='running',company=c,configuration_hash=fingerprint,attempt=attempt+1))
   try:
    ret,scores=Engine(index,folder,args.env_file,queries,config).run(c)
    assert len(ret['records'])==25 and len(ret['checks'])==4 and len(scores)==5
    byid={r['group_id']:r for r in ret['records']}
    for s in scores:
     for g in s['groups']:assert g==byid[g['group_id']]['decision_gate']['decision']
    result=dict(state='completed',company=c,configuration_hash=fingerprint,groups=25,independent_checks=4,verified_groups=sum(g['status']=='verified' for s in scores for g in s['groups']),pending_groups=sum(g['status']=='pending_review' for s in scores for g in s['groups']),final_scores={s['indicator_id']:s['final_score'] for s in scores},retrieval_complete=all(r['search_complete'] for r in ret['records']),completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    save(state,result);return result
   except Exception as e:
    with (folder/'errors.log').open('a') as f:f.write(traceback.format_exc()+'\n')
    save(state,dict(state='retrying' if attempt<2 else 'failed',company=c,configuration_hash=fingerprint,attempt=attempt+1,error_type=type(e).__name__,reason=str(e),successful_calls_cached=True))
    if attempt<2:time.sleep(10*(attempt+1))
  return json.loads(state.read_text())
 with ThreadPoolExecutor(max_workers=args.workers) as pool:
  for future in as_completed([pool.submit(work,c) for c in pending]):
   result=future.result();results[result['company']['company_id']]=result;summarize();print(result['company']['company_id'],result['state'],flush=True)
 finished=all(r['state']=='completed' for r in results.values()) and len(results)==10;summarize('completed' if finished else 'completed_with_failures')
 lines=['# 原随机10家公司定性全流程结果','','L1–L3本地RAG，L4限披露易已查范围；仅定性，不计算定量项。','','| 公司 | 状态 | 已核验组 | 待核验组 | C1 | C2 | T | W | D |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for c in selected:
  d=results[c['company_id']];values=[d.get('final_scores',{}).get(i) for i in INDICATORS]
  lines.append('|'+ '|'.join(map(str,[c['company_name'],d['state'],d.get('verified_groups','—'),d.get('pending_groups','—')]+['待核验' if v is None else v for v in values]))+'|')
 (out/'结果汇总.md').write_text('\n'.join(lines)+'\n')
 if not finished:raise SystemExit(1)
if __name__=='__main__':main()

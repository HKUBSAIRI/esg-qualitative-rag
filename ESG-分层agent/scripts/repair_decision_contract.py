"""Rebuild decision contracts from existing evidence, with zero API calls."""
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fullflow.gates import evidence_gate,bind_decisive_evidence
from fullflow.engine import INDICATORS,merge
from fullflow.scoring import score_indicator
from fullflow.evidence import verify
from retrieval.configuration import configuration
from retrieval.run_l1 import save
class NoLLM:
 def ask(self,*a,**kw):raise RuntimeError('Decision repair must not call LLM')
out=ROOT/'runs/full5_20261127';p=json.loads((out/'protocol.json').read_text());config=configuration();rules=(ROOT/'S1.1 大模型评分规则.md').read_text();results=[];plans=[]
codes={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in list((ROOT/'fullflow').glob('*.py'))+[ROOT/'retrieval/llm.py']}
fp=hashlib.sha256(json.dumps(dict(config=config,index_versions=p['index_versions'],code_versions=codes),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
for company in p['selected']:
 folder=out/company['company_id'];state=json.loads((folder/'completion_status.json').read_text());ret=json.loads((folder/'retrieval_result.json').read_text());old_scores=json.loads((folder/'scores.json').read_text());cards=merge([e for r in ret['records'] for e in r['evidence']])
 for e in cards:
  if e.get('block_type')=='table_text' and e.get('quote_match') is not True:
   e['quote_match'],e['quote_verification_method']=verify(e)
 for r in ret['records']:
  a=dict(r['assessment'],group_id=r['group_id']);es=bind_decisive_evidence(r['group_id'],a,cards)
  derived={'necessary_material_coverage_not_confirmed','decision_relevant_quote_unverified','ancillary_quote_unverified'}
  issues=[x for x in r['issues'] if (x if isinstance(x,str) else x.get('kind')) not in derived]
  gate=evidence_gate(a,es,issues,r['coverage']);a['verified_support_sufficient']=gate['decisive_support_verified']
  if a['verified_support_sufficient']:a.pop('verification_missing',None)
  r.update(assessment=a,evidence=es,decision_input_issues=issues,decision_gate=gate,search_complete=gate['search_complete'],retrieval_status=gate['retrieval_status'],issues=list(issues))
  for e in es:
   if e['evidence_id'] in a.get('evidence_ids',[]) and not any(log.get('source_id')==e['source']['source_id'] for log in r['search_log']):r['search_log'].append(dict(source_id=e['source']['source_id'],mode='explicit_cross_group_decisive_reference',pages=e['location']['pages'],evidence_id=e['evidence_id'],open_status='opened'))
 scores=[]
 for indicator in INDICATORS:
  rs=[r for r in ret['records'] if r['indicator_id']==indicator];gs=[g for g in config['groups'] if g['indicator_id']==indicator];check=next((c for c in ret['checks'] if c['indicator_id']==indicator),None)
  scores.append(score_indicator(NoLLM(),indicator,gs,rs,check,rules,company))
 # Check every scored group equals the gate decision byte-for-byte.
 for s in scores:
  for g in s['groups']:
   r=next(r for r in ret['records'] if r['group_id']==g['group_id']);assert g==r['decision_gate']['decision']
 changes=[]
 for old,new in zip(old_scores,scores):
  for a,b in zip(old['groups'],new['groups']):
   if a['score']!=b['score']:changes.append(dict(group_id=a['group_id'],before=a['score'],after=b['score']))
 state.update(configuration_hash=fp,verified_groups=sum(g['status']=='verified' for s in scores for g in s['groups']),pending_groups=sum(g['status']=='pending_review' for s in scores for g in s['groups']),final_scores={s['indicator_id']:s['final_score'] for s in scores},decision_contract='v1-single-assessment-deterministic-score')
 plans.append((folder,state,ret,scores));results.append(state);print(company['company_id'],'changes',changes,'pending',state['pending_groups'])
# Mutate only after all five have validated.
for folder,state,ret,scores in plans:
 backup=folder/'before_table_cell_verification';backup.mkdir(exist_ok=True)
 for name in ['retrieval_result.json','scores.json','completion_status.json']:
  if not (backup/name).exists():save(backup/name,json.loads((folder/name).read_text()))
 save(folder/'retrieval_result.json',ret);save(folder/'scores.json',scores);save(folder/'completion_status.json',state)
p.update(configuration_hash=fp,code_versions=codes,decision_contract='v1-single-assessment-deterministic-score');save(out/'protocol.json',p);save(out/'summary.json',results);save(out/'completion_status.json',dict(state='completed',finished_companies=5,companies=results,decision_contract='v1'))
lines=['# 5家公司定性检索与评分结果','','普通组分直接采用统一门槛判定，无独立评分LLM。L4调整只影响指标最终分。','','| 公司 | 已核验组 | 待核验组 | C1 | C2 | T | W | D |','|---|---:|---:|---:|---:|---:|---:|---:|']
for r in results:lines.append('|'+ '|'.join(str(v) for v in [r['company']['company_name'],r['verified_groups'],r['pending_groups']]+['待核验' if r['final_scores'][i] is None else r['final_scores'][i] for i in INDICATORS])+'|')
(out/'结果汇总.md').write_text('\n'.join(lines)+'\n')
print('PASS: all 125 gate decisions equal scored groups; 0 API calls')

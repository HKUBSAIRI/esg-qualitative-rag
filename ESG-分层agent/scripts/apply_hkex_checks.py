"""Apply completed bounded L4 checks; preserve ordinary RAG results and scores."""
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.configuration import configuration
from fullflow.engine import INDICATORS
from retrieval.run_l1 import save
out=ROOT/'runs/full5_20261127';protocol=json.loads((out/'protocol.json').read_text());prior=protocol['configuration_hash'];results=[]
code_versions={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'fullflow').glob('*.py'))+[ROOT/'retrieval/llm.py']}
fp=hashlib.sha256(json.dumps(dict(config=configuration(),index_versions=protocol['index_versions'],code_versions=code_versions),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
for company in protocol['selected']:
 code=company['company_id'];folder=out/code;state=json.loads((folder/'completion_status.json').read_text())
 if state['state']!='completed' or state['configuration_hash']!=prior:raise ValueError('Ordinary run is not completed/current: '+code)
 checks=json.loads((ROOT/'runs/hkex_l4'/code/'checks.json').read_text());ret=json.loads((folder/'retrieval_result.json').read_text());scores=json.loads((folder/'scores.json').read_text());backup=folder/'before_hkex_scope_checks';backup.mkdir(exist_ok=True)
 for name in ['retrieval_result.json','scores.json','completion_status.json']:save(backup/name,json.loads((folder/name).read_text()))
 ret['checks']=checks;ret['context']['independent_check_scope']='HKEX指定公司公告及限定域名检索；已知未决事项线索另行保留'
 for s in scores:
  check=next((c for c in checks if c['indicator_id']==s['indicator_id']),None)
  if check is None:continue
  s['issues']=[x for x in s['issues'] if x!='独立严重事项核查未决'];s['final_score']=s['base_score'];s['status']='verified' if s['base_score'] is not None else 'pending_review'
  if check['retrieval_status']=='pending_review':s.update(final_score=None,status='pending_review');s['issues'].append('独立严重事项核查未决')
  elif check['judgment']['state']=='verified_uncorrected':s.update(final_score=0,status='verified')
  s['independent_check_scope']=check['source_scope']
 state.update(configuration_hash=fp,final_scores={s['indicator_id']:s['final_score'] for s in scores},l4_update='HKEX official title coverage and domain-limited content discovery')
 save(folder/'retrieval_result.json',ret);save(folder/'independent_checks.json',checks);save(folder/'scores.json',scores);save(folder/'completion_status.json',state);results.append(state)
 print(code,state['final_scores'])
protocol.update(configuration_hash=fp,code_versions=code_versions,l4_source='HKEXnews official title search plus HKEX-domain content discovery',l4_logs=str((ROOT/'runs/hkex_l4').resolve()))
save(out/'protocol.json',protocol);save(out/'summary.json',results);save(out/'completion_status.json',dict(state='completed',finished_companies=5,companies=results,l4_scope='HKEXnews with known unresolved leads preserved'))
lines=['# 5家公司定性检索与评分结果','','仅定性；L1–L3本地混合RAG，L4限本次披露易查找范围。未发现通报不证明未发生；已知待核实线索仍保留。','','| 公司 | 已核验组 | 待核验组 | C1 | C2 | T | W | D |','|---|---:|---:|---:|---:|---:|---:|---:|']
for r in results:lines.append('|'+ '|'.join(str(v) for v in [r['company']['company_name'],r['verified_groups'],r['pending_groups']]+['待核验' if r['final_scores'][i] is None else r['final_scores'][i] for i in INDICATORS])+'|')
(out/'结果汇总.md').write_text('\n'.join(lines)+'\n')
p=ROOT/'config/material_policy.json';policy=json.loads(p.read_text());policy.update(l4_network_exception=dict(authorized=True,source='https://www.hkexnews.hk/index_c.htm',allowed_hosts=['www.hkexnews.hk','www1.hkexnews.hk'],scope='L4 only; official title search and HKEX-domain content discovery',broad_web_search=False));save(p,policy)

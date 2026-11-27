"""Repair completed current-generation results without repeating ordinary retrieval."""
import sys,json,hashlib,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.configuration import configuration
from retrieval.llm import LLM
from retrieval.run_l1 import save
from fullflow.engine import judge_independent,INDICATORS
from fullflow.scoring import score_indicator
out=ROOT/'runs/full5_20261127';protocol=json.loads((out/'protocol.json').read_text());oldhash=protocol['configuration_hash']
config=configuration();rules=(ROOT/'S1.1 大模型评分规则.md').read_text()
codes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'fullflow').glob('*.py'))+[ROOT/'retrieval/llm.py']}
newhash=hashlib.sha256(json.dumps(dict(config=config,index_versions=protocol['index_versions'],code_versions=codes),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
for company in protocol['selected']:
 folder=out/company['company_id'];state=json.loads((folder/'completion_status.json').read_text())
 if state.get('configuration_hash')!=oldhash or state.get('state')!='completed':continue
 retrieval=json.loads((folder/'retrieval_result.json').read_text());scores=json.loads((folder/'scores.json').read_text())
 backup=folder/'before_official_relevance_fix';backup.mkdir(exist_ok=True)
 for filename in ['retrieval_result.json','scores.json','completion_status.json']:save(backup/filename,json.loads((folder/filename).read_text()))
 llm=LLM(sys.argv[1],folder/'calls');checks=[]
 for check in retrieval['checks']:
  checks.append(judge_independent(llm,check['indicator_id'],check['evidence'],check['search_log'],check['issues'],rules,company,folder))
 retrieval['checks']=checks;scores=[]
 for indicator in INDICATORS:
  groups=[g for g in config['groups'] if g['indicator_id']==indicator];records=[r for r in retrieval['records'] if r['indicator_id']==indicator]
  check=next((c for c in checks if c['indicator_id']==indicator),None)
  scores.append(score_indicator(llm,indicator,groups,records,check,rules,company))
 save(folder/'retrieval_result.json',retrieval);save(folder/'independent_checks.json',checks);save(folder/'scores.json',scores)
 state.update(configuration_hash=newhash,verified_groups=sum(g['status']=='verified' for s in scores for g in s['groups']),pending_groups=sum(g['status']=='pending_review' for s in scores for g in s['groups']),final_scores={s['indicator_id']:s['final_score'] for s in scores},repair='official_source_relevance_and_separate_group_scoring')
 save(folder/'completion_status.json',state)
 print(company['company_id'],json.dumps({'checks':{c['indicator_id']:c['judgment']['state'] for c in checks},'scores':state['final_scores']},ensure_ascii=False),flush=True)
print('Repair complete; runner will resume unfinished companies.',flush=True)

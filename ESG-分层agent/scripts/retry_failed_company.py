"""Retry one failed current-generation company with existing successful call caches."""
import sys,json,fcntl
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.configuration import configuration
from retrieval.run_l1 import save
from fullflow.engine import Engine
out=ROOT/'runs/full5_20261127';protocol=json.loads((out/'protocol.json').read_text());code=sys.argv[1];folder=out/code
lock=(folder/'repair.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
company=next(c for c in protocol['selected'] if c['company_id']==code);state=json.loads((folder/'completion_status.json').read_text())
if state.get('state')!='failed' or state.get('configuration_hash')!=protocol['configuration_hash']:raise SystemExit('Current result is not a failed company')
save(folder/'completion_status.json',dict(state='running',company=company,configuration_hash=protocol['configuration_hash'],repair='retry_model_schema_failure_with_successful_caches'))
queries=json.loads((out/'queries.json').read_text());querymap={g['group_id']:g['queries'] for g in queries['groups']}
try:
 result,scores=Engine(ROOT/'runs/random10_20261127/layered/index',folder,sys.argv[2],querymap,configuration()).run(company)
 save(folder/'completion_status.json',dict(state='completed',company=company,configuration_hash=protocol['configuration_hash'],workflow_version='fullflow-v1',groups=25,independent_checks=4,verified_groups=sum(g['status']=='verified' for s in scores for g in s['groups']),pending_groups=sum(g['status']=='pending_review' for s in scores for g in s['groups']),final_scores={s['indicator_id']:s['final_score'] for s in scores},retrieval_complete=all(r['search_complete'] for r in result['records']),completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()))
 print(code,'completed',flush=True)
except Exception as e:
 save(folder/'completion_status.json',dict(state='failed',company=company,configuration_hash=protocol['configuration_hash'],error_type=type(e).__name__,reason=str(e)))
 raise

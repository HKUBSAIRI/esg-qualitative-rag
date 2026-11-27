"""Wait for local material indexing, then run and compare the ten-company cohort."""
import sys,json,time,subprocess,fcntl
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'runs/full10_20261127';out.mkdir(parents=True,exist_ok=True)
lock=(out/'continuation.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
status=out/'supervisor_status.json';env=sys.argv[1];start=time.monotonic()
status.write_text(json.dumps(dict(state='waiting_for_local_indexes',reuse_completed_companies=5,new_companies=['01548','03759','00867','01093','06160'],full_text_reading=False,model='qwen3.8-flash'),indent=2))
print('Waiting for remaining-company local indexes; HKEX checks prepared.',flush=True)
while True:
 path=ROOT/'runs/local_material_rag_remaining/completion_status.json'
 if path.exists() and json.loads(path.read_text()).get('state')=='completed' and all((ROOT/'runs/local_material_rag/index'/code/f'L{i}'/'manifest.json').exists() for code in ['01548','03759','00867','01093','06160'] for i in (1,2,3)):break
 if time.monotonic()-start>21600:
  status.write_text(json.dumps(dict(state='index_preparation_timeout',diagnostics='runs/local_material_rag_remaining/*.parse.log')));raise SystemExit(1)
 time.sleep(20)
for attempt in range(3):
 status.write_text(json.dumps(dict(state='running',attempt=attempt+1,maximum_attempts=3),indent=2))
 with (out/'run.log').open('a') as log:result=subprocess.run([sys.executable,str(ROOT/'run_full10.py'),'--env-file',env,'--workers','2'],stdout=log,stderr=log,cwd=ROOT)
 if result.returncode==0:
  with (out/'gt_comparison.log').open('a') as log:compare=subprocess.run([sys.executable,str(ROOT/'scripts/compare_source_filtered_gt.py'),str(out)],stdout=log,stderr=log,cwd=ROOT)
  status.write_text(json.dumps(dict(state='completed' if compare.returncode==0 else 'run_completed_comparison_failed',attempt=attempt+1,gt_comparison_exit_code=compare.returncode),indent=2));print('10-company run completed; GT comparison exit code',compare.returncode,flush=True);raise SystemExit(compare.returncode)
 if attempt<2:time.sleep(30)
status.write_text(json.dumps(dict(state='failed_after_bounded_retries',reason='See company errors.log; successful API calls preserved'),indent=2));raise SystemExit(1)

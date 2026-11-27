"""Bounded retries for the authorized job; checkpoints prevent duplicate successful calls."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/full5_20261127'
def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',type=Path,required=True);a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 for attempt in range(3):
  (OUT/'supervisor_status.json').write_text(json.dumps(dict(state='running',attempt=attempt+1,max_attempts=3),indent=2))
  with (OUT/'run.log').open('a') as log:
   cp=subprocess.run([sys.executable,str(ROOT/'run_full5.py'),'--env-file',str(a.env_file.resolve()),'--workers','2'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  path=OUT/'completion_status.json';state=json.loads(path.read_text()) if path.exists() else {}
  if cp.returncode==0 and state.get('state')=='completed':
   (OUT/'supervisor_status.json').write_text(json.dumps(dict(state='completed',attempt=attempt+1),indent=2));return
  if attempt<2:time.sleep(30*(attempt+1))
 (OUT/'supervisor_status.json').write_text(json.dumps(dict(state='failed_after_bounded_retries',last_exit_code=cp.returncode,diagnostics='run.log and company errors.log',successful_calls_preserved=True),indent=2))
 raise SystemExit(1)
if __name__=='__main__':main()

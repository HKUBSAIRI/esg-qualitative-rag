"""Wait for verified indexes, run only the next authorized L1 pilot, then stop."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];LAYER=ROOT/'runs/random10_20261127/layered';OUT=ROOT/'runs/random10_20261127/l1_pilot_03692_flash'
def main():
 p=argparse.ArgumentParser();p.add_argument('--env-file',type=Path,required=True);a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 status=OUT/'completion_status.json';start=time.monotonic()
 def save(state,**extra):status.write_text(json.dumps(dict(state=state,scope='25 qualitative groups; Hansoh L1 pilot; no scoring',**extra),ensure_ascii=False,indent=2))
 save('waiting_for_verified_layered_indexes')
 try:
  while True:
   previous=json.loads((LAYER/'completion_status.json').read_text())
   if previous['state']=='completed':break
   if previous['state']=='failed':raise RuntimeError('Index stage failed; next stage not started')
   if time.monotonic()-start>21600:raise TimeoutError('Index wait exceeded six hours')
   time.sleep(30)
  save('running_l1_pilot',llm_model='qwen3.8-flash',llm_provider='dashscope.aliyuncs.com',embedding_model='text-embedding-3-small')
  with (OUT/'run.log').open('a') as log:
   subprocess.run([sys.executable,'-m','retrieval.run_l1','--index',str(LAYER/'index'),'--output',str(OUT),'--env-file',str(a.env_file.resolve()),'--company','03692'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
  result=json.loads((OUT/'retrieval_result.json').read_text())
  if len(result['records'])!=25 or any(r['search_complete'] or r['retrieval_status']!='pending_review' for r in result['records']):raise ValueError('Invalid pilot completion state')
  save('completed',summary=json.loads((OUT/'summary.json').read_text()),next_action='await_user_confirmation; no automatic scoring or other-company runs')
 except Exception as e:save('failed',error_type=type(e).__name__,reason=str(e));raise
if __name__=='__main__':main()

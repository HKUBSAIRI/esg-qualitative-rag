"""Finish the authorized indexing phase without conversational polling."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/random10_20261127/layered'
def main():
 p=argparse.ArgumentParser();p.add_argument('--docling-python',required=True);p.add_argument('--env-file',type=Path,required=True);a=p.parse_args()
 status=OUT/'completion_status.json';started=time.monotonic()
 def save(state,**extra):
  temp=status.with_suffix('.tmp');temp.write_text(json.dumps(dict(state=state,stage='material_parsing_and_layered_index_only',**extra),ensure_ascii=False,indent=2));temp.replace(status)
 save('waiting_for_active_parser')
 try:
  while True:
   progress=json.loads((OUT/'parse_progress.json').read_text())
   summary=json.loads((OUT/'registry_summary.json').read_text())
   if progress['done']+len(progress['errors'])==progress['total']:
    if progress['errors']:raise RuntimeError('PDF parsing failures; inspect parse_progress.json')
    if summary['sources']==progress['total'] and not summary['errors']:break
   if time.monotonic()-started>18000:raise TimeoutError('Parser completion wait exceeded 5 hours')
   time.sleep(30)
  log=OUT/'finish_pipeline.log'
  def run(args):
   with log.open('a') as f:subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
  save('refreshing_registry')
  run([sys.executable,str(ROOT/'scripts/prepare_layered_index.py'),'--docling',str(ROOT/'docling_cli.py'),'--docling-python',a.docling_python,'--workers','3'])
  run([sys.executable,str(ROOT/'tests/check_layered_parses.py'),str(OUT)])
  save('building_final_vectors')
  run([sys.executable,str(ROOT/'build_index.py'),'--registry',str(OUT/'registry'),'--output',str(OUT/'index'),'--env-file',str(a.env_file.resolve())])
  save('verifying_indexes')
  run([sys.executable,str(ROOT/'tests/check_vector_indexes.py'),str(OUT/'index')])
  manifest=json.loads((OUT/'index/build_summary.json').read_text())
  save('completed',summary=manifest,verification=str(OUT/'index/verification.json'),limitations=['L4 OCR remains local-only and unverified','No retrieval agent or scoring executed'])
 except Exception as e:
  save('failed',error_type=type(e).__name__,reason=str(e));raise
if __name__=='__main__':main()

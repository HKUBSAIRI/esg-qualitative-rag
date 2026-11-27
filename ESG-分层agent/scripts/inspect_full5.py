"""Compact current-configuration health report; ignore stale failures."""
import json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/full5_20261127'
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return {}
protocol=read(OUT/'protocol.json');fingerprint=protocol.get('configuration_hash');failures=[];progress=[];stalled=[]
for company in protocol.get('selected',[]):
 code=company['company_id'];folder=OUT/code;state=read(folder/'completion_status.json');phase=read(folder/'progress.json')
 current=state.get('configuration_hash')==fingerprint
 progress.append(dict(company_id=code,state=state.get('state') if current else 'queued',stage=phase.get('stage') if current else None,level=phase.get('level') if current else None))
 if current and state.get('state')=='failed':
  errors=sorted((folder/'calls').glob('*.error.json'),key=lambda p:p.stat().st_mtime)
  failures.append(dict(company_id=code,reason=state.get('reason'),last_call_errors=[dict(file=p.name,details=read(p)) for p in errors[-2:]]))
 for p in (folder/'search_requests').glob('*.json'):
  request=read(p)
  if request and not Path(request['response_path']).exists() and time.time()-p.stat().st_mtime>240:stalled.append(dict(company_id=code,request_id=request.get('request_id'),age_seconds=round(time.time()-p.stat().st_mtime)))
status=read(OUT/'completion_status.json')
print(json.dumps(dict(state=status.get('state'),failures=failures,stalled_searches=stalled,progress=progress),ensure_ascii=False))

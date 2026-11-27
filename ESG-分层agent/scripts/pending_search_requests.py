import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'runs/full5_20261127';requests=[]
for path in out.glob('*/search_requests/*.json'):
 d=json.loads(path.read_text())
 response=Path(d['response_path'])
 if not response.exists():requests.append(d)
print(json.dumps(requests,ensure_ascii=False))

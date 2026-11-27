import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.llm import LLM
from fullflow.web import search
out=ROOT/'runs/full5_20261127/search_probe'
llm=LLM(sys.argv[1],out/'calls')
r=search(llm,'翰森制药 2025 欠薪 官方监管 司法 通报 HKEX',out)
print(json.dumps(dict(search_executed=r['search_executed'],results=len(r['results']),error_type=r.get('error_type')),ensure_ascii=False))

"""Explicit paid API smoke test; supply env path as argument."""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from indexing.embedding import Embedding
from indexing.bm25 import BM25,tokenize
root=Path(__file__).resolve().parents[1]/'validation/api_index_smoke'
api=Embedding(root/'embedding_cache',sys.argv[1])
texts=['员工工资按时足额支付。','员工可申请带薪年假。','The company prohibits workplace harassment.']
v=api.encode(texts)
assert v.shape==(3,1024) and np.allclose(np.linalg.norm(v,axis=1),1)
assert int(np.argmax(v@v[0]))==0
assert BM25([tokenize(t) for t in texts]).scores(tokenize('工资支付')).argmax()==0
np.save(root/'embeddings.npy',v)
(root/'result.json').write_text(json.dumps(dict(model=api.model,shape=list(v.shape),self_retrieval_passed=True,bm25_passed=True,api_calls=api.calls),ensure_ascii=False,indent=2))
print('PASS: real API embeddings, normalization, self retrieval, BM25')

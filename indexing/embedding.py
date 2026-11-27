from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
import httpx
import numpy as np

class Embedding:
    def __init__(self, cache, env_file=None):
        config={}
        if env_file:
            for line in Path(env_file).read_text().splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    k,v=line.split('=',1); config[k.strip()]=v.strip().strip('"\x27')
        config.update(os.environ)
        self.model=config['EMBEDDING_MODEL']; self.base=config['EMBEDDING_BASE_URL'].rstrip('/')
        self.key=config['EMBEDDING_API_KEY']; self.cache=Path(cache); self.cache.mkdir(parents=True,exist_ok=True)
        self.dim=1024; self.calls=[]
    def encode(self, texts):
        with (self.cache/".cache.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try: return self._encode(texts)
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    def _encode(self, texts):
        keys=[hashlib.sha256(json.dumps([self.base,self.model,self.dim,t],ensure_ascii=False).encode()).hexdigest() for t in texts]
        lookup=dict(zip(keys,texts)); values={}
        for k in lookup:
            p=self.cache/(k+'.json')
            if p.exists(): values[k]=json.loads(p.read_text())
        missing=[k for k in lookup if k not in values]
        with httpx.Client(timeout=httpx.Timeout(60, connect=15), transport=httpx.HTTPTransport(local_address="0.0.0.0")) as client:
            def run_batch(batch):
                for attempt in range(3):
                    try:
                        r=client.post(self.base+'/embeddings',headers={'Authorization':'Bearer '+self.key},json=dict(model=self.model,dimensions=self.dim,input=[lookup[k] for k in batch]))
                        r.raise_for_status(); obj=r.json()
                        rows=obj['data']
                        if sorted(x['index'] for x in rows)!=list(range(len(batch))): raise ValueError('Invalid embedding response indices')
                        for row in rows:
                            v=row['embedding']
                            if len(v)!=self.dim or not np.isfinite(v).all() or np.linalg.norm(v)==0: raise ValueError('Invalid embedding vector')
                            values[batch[row['index']]]=v
                        for k in batch:
                            p=self.cache/(k+'.json'); temp=p.with_suffix('.tmp'); temp.write_text(json.dumps(values[k])); temp.replace(p)
                        self.calls.append(dict(model=obj.get('model',self.model),usage=obj.get('usage'),batch_size=len(batch)))
                        break
                    except (httpx.HTTPError,ValueError,KeyError):
                        if attempt==2: raise RuntimeError('Embedding API failed after 3 attempts; credentials and response body withheld') from None
                        time.sleep(2**attempt)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(run_batch,[missing[i:i+20] for i in range(0,len(missing),20)]))
        array=np.asarray([values[k] for k in keys],dtype=np.float32)
        if array.shape!=(len(texts),self.dim) or not np.isfinite(array).all(): raise ValueError('Invalid embedding cache')
        norms=np.linalg.norm(array,axis=1,keepdims=True)
        if (norms==0).any(): raise ValueError('Zero embedding vector')
        return array/norms

"""Build company/level indexes from registered parser units. No inference of source metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from indexing.bm25 import tokenize
from indexing.embedding import Embedding

def read(path): return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
def write(path,rows): path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))

def build(registry, output, api):
    sources=read(registry/'sources.jsonl'); groups={}; skipped=[]
    for s in sources:
        if s['metadata_status']!='registered' or s['source_level'] not in (1,2,3,4):
            skipped.append(dict(source_id=s['source_id'],reason='metadata_not_registered')); continue
        code=s['company_id']
        if not code.isascii() or not code.isalnum(): raise ValueError('Unsafe company_id for index path')
        base=registry/'linked'/s['source_id']
        chunks=read(base/'retrieval_chunks.jsonl'); units=read(base/'retrieval_units.jsonl')
        parents={c['chunk_id']:c for c in chunks}
        for u in units:
            if u['source_id']!=s['source_id'] or u['company_id']!=code or u['parent_chunk_id'] not in parents: raise ValueError('Invalid unit provenance')
            parent=parents[u['parent_chunk_id']]
            if parent['text'][u['char_start']:u['char_end']]!=u['text']: raise ValueError('Unit does not match parent')
        if not units:
            skipped.append(dict(source_id=s['source_id'],reason='no_retrieval_units'))
            continue
        entry=groups.setdefault((code,s['source_level']),dict(units=[],chunks=[],sources=[]))
        entry['units'].extend(units);entry['chunks'].extend(chunks);entry['sources'].append(s)
    # Registered materials validated before API calls.
    output.mkdir(parents=True,exist_ok=True)
    manifests=[]
    for (code,level),data in sorted(groups.items()):
        print('INDEX_START',code,'L'+str(level),len(data['units']),flush=True)
        units=sorted(data['units'],key=lambda u:(u['source_id'],u['unit_id']))
        if not units: continue
        keys=[(u['source_id'],u['unit_id']) for u in units]
        if len(set(keys))!=len(keys): raise ValueError('Duplicate index units')
        usage_start=len(api.calls) if api else 0
        vectors=api.encode([u['retrieval_text'] for u in units]) if api else None
        corpus_hash=hashlib.sha256(json.dumps(units,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        dest=output/code/f'L{level}';dest.mkdir(parents=True,exist_ok=True)
        (dest/'manifest.json').unlink(missing_ok=True)
        if vectors is not None: np.save(dest/'embeddings.npy',vectors)
        else: (dest/'embeddings.npy').unlink(missing_ok=True)
        write(dest/'units.jsonl',units);write(dest/'chunks.jsonl',data['chunks']);write(dest/'sources.jsonl',data['sources'])
        write(dest/'bm25_tokens.jsonl',[dict(unit_id=u['unit_id'],source_id=u['source_id'],tokens=tokenize(u['retrieval_text'])) for u in units])
        write(dest/'row_map.jsonl',[dict(row=i,unit_id=u['unit_id'],source_id=u['source_id'],parent_chunk_id=u['parent_chunk_id']) for i,u in enumerate(units)])
        manifest=dict(company_id=code,source_level=level,rows=len(units),corpus_sha256=corpus_hash,vector_ready=api is not None,model=api.model if api else None,dimensions=1024,dtype='float32',normalized=True,metric='cosine_dot',bm25=dict(k1=1.5,b=0.75,tokenizer='en-cjk-2gram-3gram-v1'),usage=api.calls[usage_start:] if api else [])
        (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));manifests.append(manifest)
        print('INDEX_DONE',code,'L'+str(level),len(units),flush=True)
    summary=dict(indexes=len(manifests),units=sum(x['rows'] for x in manifests),skipped=skipped)
    (output/'build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registry',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path);p.add_argument('--local-only',action='store_true');a=p.parse_args()
    api=None if a.local_only else Embedding(a.output/'embedding_cache',a.env_file)
    print(json.dumps(build(a.registry,a.output,api),ensure_ascii=False))
if __name__=='__main__':main()

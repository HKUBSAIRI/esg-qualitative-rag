"""Check real disk indexes: all vectors, row provenance, and sampled exact retrieval."""
import json,sys
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]);reports=[]
for path in sorted(root.glob('*/L*/manifest.json')):
    manifest=json.loads(path.read_text());d=path.parent
    assert manifest['vector_ready'],f'Incomplete vector index: {d}'
    v=np.load(d/'embeddings.npy')
    def rows(name):return [json.loads(s) for s in (d/name).read_text().splitlines()]
    units=rows('units.jsonl');mapping=rows('row_map.jsonl');tokens=rows('bm25_tokens.jsonl');chunks=rows('chunks.jsonl')
    parents={(c['source_id'],c['chunk_id']):c for c in chunks}
    assert v.shape==(manifest['rows'],1024) and v.dtype==np.float32
    assert np.isfinite(v).all() and np.allclose(np.linalg.norm(v,axis=1),1,atol=1e-5)
    assert len(units)==len(mapping)==len(tokens)==len(v)
    for i,(u,m,t) in enumerate(zip(units,mapping,tokens)):
        assert u['company_id']==manifest['company_id'] and u['source_level']==manifest['source_level']
        assert m['row']==i and m['unit_id']==u['unit_id']==t['unit_id']
        assert m['source_id']==u['source_id']==t['source_id']
        parent=parents[(u['source_id'],u['parent_chunk_id'])]
        assert parent['text'][u['char_start']:u['char_end']]==u['text']
    sample=np.linspace(0,len(v)-1,min(10,len(v)),dtype=int)
    for i in sample:
        scores=v@v[i]
        assert scores[i]>=scores.max()-1e-5 # Identical texts can tie.
    reports.append(dict(company_id=manifest['company_id'],level=manifest['source_level'],rows=len(v),passed=True))
assert reports,'No indexes found'
(root/'verification.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))
print(f"PASS: {len(reports)} indexes, {sum(r['rows'] for r in reports)} vectors")

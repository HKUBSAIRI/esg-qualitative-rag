import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sources=[json.loads(x) for x in (root/'registry/sources.jsonl').read_text().splitlines()];report=[]
for s in sources:
    parsed=root/'parsed'/s['company_id']/s['file_sha256']
    m=json.loads((parsed/'parse_manifest.json').read_text())
    assert m.get('source_file_sha256',m.get('source_pdf_sha256'))==s['file_sha256']
    chunks=[json.loads(x) for x in (parsed/'retrieval_chunks.jsonl').read_text().splitlines()]
    units=[json.loads(x) for x in (parsed/'retrieval_units.jsonl').read_text().splitlines()]
    parents={c['chunk_id']:c for c in chunks};assert len(parents)==len(chunks)
    spans={cid:[] for cid in parents}
    for u in units:
        c=parents[u['parent_chunk_id']]
        assert c['text'][u['char_start']:u['char_end']]==u['text']
        spans[u['parent_chunk_id']].append(u)
        assert len(u['retrieval_text'].encode())<=u['max_input_bytes']
    for cid,c in parents.items():
        assert ''.join(u['text'] for u in sorted(spans[cid],key=lambda x:x['char_start']))==c['text']
    if 'page_count' in m:
        quality=json.loads((parsed/'page_quality.json').read_text())
        assert [q['page'] for q in quality]==list(range(1,m['page_count']+1))
        assert not m['toc_pages_excluded'] and not m['cover_pages_excluded']
    linked=[json.loads(x) for x in (root/'registry/linked'/s['source_id']/'retrieval_chunks.jsonl').read_text().splitlines()]
    assert all(c['source_id']==s['source_id'] and c['company_id']==s['company_id'] for c in linked)
    assert all(c['quote_match'] is None for c in chunks)
    report.append(dict(company_id=s['company_id'],source_id=s['source_id'],level=s['source_level'],chunks=len(chunks),units=len(units),metadata_status=s['metadata_status'],passed=True))
(root/'parse_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('PASS',len(report),'materials;',sum(x['chunks'] for x in report),'chunks;',sum(x['units'] for x in report),'units')

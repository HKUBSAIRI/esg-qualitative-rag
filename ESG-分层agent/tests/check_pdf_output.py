"""Validate actual parser artifacts without network or LLM calls."""
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
chunks = [json.loads(x) for x in (p/'retrieval_chunks.jsonl').read_text().splitlines()]
ids = {c['chunk_id'] for c in chunks}
assert len(ids) == len(chunks)
for c in chunks:
    assert c['text'].strip() and c['pages'] and min(c['pages']) >= 1
    assert c['bboxes'], c['chunk_id']
    assert c['quote_match'] is None
    for key in ('prev_chunk_id', 'next_chunk_id'):
        assert c[key] is None or c[key] in ids
    for key in ('note_candidates', 'table_continuation_candidates', 'linked_note_ids'):
        assert set(c[key]) <= ids
    assert not c['linked_note_ids']  # No guessed ownership asserted as verified.
    if c['block_type'] == 'table_text':
        assert c['table_rows'] or c['raw_table']
assert len(json.loads((p/'page_quality.json').read_text())) == json.loads((p/'summary.json').read_text())['page_count']
assert all(x['coverage_status']=='not_reviewed' for x in json.loads((p/'page_quality.json').read_text()))
print(f'PASS: {len(chunks)} chunks; provenance, links, tables, and coverage invariants')

"""Lossless local enrichment; proximity links are candidates, never verified facts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
from .common import sha256_file, write_json

VERSION = 's11-pdf-v1'

def enrich(pdf: Path, raw: Path, output: Path, semantic: list, blocks: list, tables: list, visuals: list, page_sizes: dict) -> list:
    digest = sha256_file(pdf)
    payload = json.loads(raw.read_text())
    source_tables = {x.get('self_ref'): x for x in payload.get('tables', [])}
    chunks = [dict(x) for x in semantic if x['block_type'] in {'paragraph', 'list', 'table_text'}]
    for b in blocks:
        if b.get('block_type') == 'footnote' and str(b.get('text') or '').strip():
            page = int(b['page_number'])
            from .pipeline import top_left_bbox
            chunks.append(dict(text=b['text'], pages=[page], page=page, block_type='footnote',
                               source_block_ids=[b['hybrid_block_id']],
                               bboxes=[dict(page=page, bbox=top_left_bbox(b.get('bbox'), page_sizes[page][1]))]))
    for v in visuals:
        if v['text'].strip():
            chunks.append(dict(v, block_type='visual_text', source_block_ids=[v['source_block_id']],
                               bboxes=[dict(page=v['page'], bbox=v['bbox'])]))
    # Stable identities include provenance; identical words at different positions remain distinct.
    seen = set(); result = []
    for c in chunks:
        key = json.dumps([digest, VERSION, c.get('source_block_ids'), c['pages'], c['text']], ensure_ascii=False, sort_keys=True)
        cid = 'C_' + hashlib.sha256(key.encode()).hexdigest()[:24]
        if cid in seen: continue
        seen.add(cid)
        c.update(chunk_id=cid, legacy_paragraph_id=c.get('paragraph_id'), source_id=digest,
                 file_sha256=digest, document_id=pdf.stem, schema_version=VERSION,
                 text_sha256=hashlib.sha256(c['text'].encode()).hexdigest(),
                 quote_match=None, printed_pages=[], quality_flags=[], linked_note_ids=[],
                 note_candidates=[], table_continuation_candidates=[], section_path=[c['section']] if c.get('section') else [])
        c['title_candidates'] = [dict(text=h['text'], pages=h['pages'], paragraph_id=h['paragraph_id']) for h in semantic if h['block_type'] == 'title' and set(h['pages']) & set(c['pages'])]
        c['retrieval_text'] = '[Section]\n' + str(c.get('section') or '') + '\n[Content]\n' + c['text']
        if c['block_type'] == 'table_text':
            refs = c.get('source_block_ids', [])
            c['table_id'] = cid
            c['quality_flags'].append('cross_page_table_relationship_unverified') if any(min(t['pages']) == max(c['pages']) + 1 for t in chunks if t['block_type'] == 'table_text') else None
            c['table_rows'] = c.get('rows', [])
            c['raw_table'] = next((source_tables[r] for r in refs if r in source_tables), None)
            c['quality_flags'].append('table_headers_units_notes_require_verification')
        if c['block_type'] == 'visual_text': c['quality_flags'].append('visual_context_requires_verification')
        result.append(c)
    result.sort(key=lambda c: (min(c['pages']), min((b['bbox'][1] for b in c.get('bboxes', []) if b.get('bbox')), default=0)))
    notes = [c for c in result if c['block_type'] == 'footnote']
    tabs = [c for c in result if c['block_type'] == 'table_text']
    for i, c in enumerate(result):
        c['document_order'] = i + 1
        c['prev_chunk_id'] = result[i-1]['chunk_id'] if i else None
        c['next_chunk_id'] = result[i+1]['chunk_id'] if i+1 < len(result) else None
        c['note_candidates'] = [n['chunk_id'] for n in notes if n is not c and set(n['pages']) & set(c['pages'])]
        if c['block_type'] == 'table_text':
            c['table_continuation_candidates'] = [t['chunk_id'] for t in tabs if t is not c and min(t['pages']) == max(c['pages']) + 1]
    reader = PdfReader(pdf)
    quality = []
    for p in range(1, len(reader.pages)+1):
        rows = [c for c in result if p in c['pages']]
        count = sum(len(c['text']) for c in rows)
        quality.append(dict(page=p, extracted_characters=count, chunk_count=len(rows),
                            flags=['low_text_or_unrepresented_page'] if count < 40 else [],
                            coverage_status='not_reviewed', quote_verified=False))
    write_json(output/'page_quality.json', quality)
    write_json(output/'source.json', dict(source_id=digest, file_sha256=digest, local_path=str(pdf),
               title=pdf.stem, source_level=None, source_kind=None, report_year=None,
               publisher=None, original_url=None, metadata_status='requires_registration'))
    with (output/'retrieval_chunks.jsonl').open('w', encoding='utf-8') as f:
        for c in result: f.write(json.dumps(c, ensure_ascii=False)+'\n')
    from .retrieval_units import build_units, DEFAULT_MAX_BYTES
    units = build_units(result)
    with (output/'retrieval_units.jsonl').open('w', encoding='utf-8') as f:
        for u in units: f.write(json.dumps(u, ensure_ascii=False)+'\n')
    write_json(output/'retrieval_unit_policy.json', dict(
        canonical_unit='complete_natural_paragraph_or_semantic_block',
        derived_units_only=True, budget_kind='utf8_bytes', max_input_bytes=DEFAULT_MAX_BYTES,
        overlap=0, offsets='python_unicode_characters_half_open',
        restore_context_via='parent_chunk_id', llm_batching='downstream_not_implemented'))
    return result

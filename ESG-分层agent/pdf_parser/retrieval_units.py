"""Derived embedding units. Canonical paragraph chunks remain untouched.

Use a conservative UTF-8 byte budget (8000), not an estimated token count.
For byte-level BPE the number of tokens cannot exceed the input byte count.
The budget includes section prefixes; deployments must configure it below
an embedding service's actual input limit.
"""
from __future__ import annotations
import hashlib

DEFAULT_MAX_BYTES = 8000

def build_units(chunks, max_bytes=DEFAULT_MAX_BYTES):
    if max_bytes < 32:
        raise ValueError('max_bytes must be at least 32')
    units = []
    for c in chunks:
        text = c['text']
        prefix = '[Section]\n' + str(c.get('section') or '') + '\n[Content]\n'
        # Do not drop an oversized heading. Use plain content for embedding and
        # retain the complete heading in canonical metadata.
        if len(prefix.encode('utf-8')) > max_bytes - 4:
            prefix = ''
        allowance = max_bytes - len(prefix.encode('utf-8'))
        spans = []
        start = 0
        while start < len(text):
            end = start
            size = 0
            while end < len(text):
                width = len(text[end].encode('utf-8'))
                if size + width > allowance:
                    break
                size += width
                end += 1
            if end == start:
                raise ValueError('Embedding budget too small for one Unicode character')
            spans.append((start, end))
            start = end
        split = len(spans) > 1
        for index, (start, end) in enumerate(spans):
            body = text[start:end]
            uid = c['chunk_id'] if not split else 'U_' + hashlib.sha256(
                f"{c['chunk_id']}:{start}:{end}:{max_bytes}".encode()).hexdigest()[:24]
            units.append(dict(unit_id=uid, parent_chunk_id=c['chunk_id'],
                              is_subchunk=split, part_index=index, part_count=len(spans),
                              char_start=start, char_end=end, text=body,
                              retrieval_text=prefix + body, pages=c['pages'],
                              source_id=c['source_id'], section=c.get('section'),
                              budget_kind='utf8_bytes', max_input_bytes=max_bytes))
    return units

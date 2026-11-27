from __future__ import annotations
import hashlib
import json
from pathlib import Path

LEVELS = {'esg': 1, 'sustainability': 1, 'csr': 1,
          'annual': 2, 'financial_statement': 2, 'financial_notes': 2,
          'thematic_report': 3, 'governance': 3, 'policy': 3, 'announcement': 3,
          'official_regulatory_notice': 4, 'official_judicial_notice': 4}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def build_registry(entries, base):
    """No filename/year/domain inference. Missing evidence remains unresolved."""
    sources = {}; bindings = []
    for index, item in enumerate(entries):
        x = dict(item)
        company = x.get('company_id')
        if not isinstance(company, str) or not company.strip():
            raise ValueError(f'entry {index}: company_id must be a nonempty string')
        year = x.get('report_year')
        if year is not None and (type(year) is not int or not 1900 <= year <= 2200):
            raise ValueError(f'entry {index}: invalid report_year')
        path = Path(x['local_path'])
        path = (base/path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file(): raise ValueError(f'Missing material: {path}')
        sha = digest(path)
        if x.get('file_sha256') and x['file_sha256'] != sha:
            raise ValueError(f'File hash mismatch: {path}')
        kind = x.get('source_kind')
        if kind is not None and kind not in LEVELS:
            raise ValueError(f'Unsupported source_kind: {kind}')
        level = LEVELS.get(kind)
        if x.get('source_level') is not None and x['source_level'] != level:
            raise ValueError('source_level contradicts document kind')
        # Company-specific binding prevents evidence leakage between companies.
        sid = company + '_' + sha
        urls = [x.get(k) for k in ('entry_url','original_url','hosted_url') if x.get(k)]
        required = ('company_name','title','publisher','original_url','source_kind','classification_basis')
        if kind in {'esg','sustainability','csr','annual','financial_statement','financial_notes'}:
            required += ('report_year',)
        issues = [f'missing:{k}' for k in required if x.get(k) in (None,'')]
        if x.get('official_verified') is not True: issues.append('official_source_not_verified')
        row = {k:x.get(k) for k in ('company_id','company_name','title','publisher','source_kind',
               'report_year','period','published_at','effective_from','version','supersedes_source_id',
               'entry_url','original_url','hosted_url','classification_basis','official_verified','evidence_issues','metadata_origin')}
        row.update(source_id=sid, file_sha256=sha, local_path=str(path), local_paths=[str(path)],
                   source_level=level, urls=list(dict.fromkeys(urls)), availability='available',
                   issues=issues, metadata_status='pending_review' if issues else 'registered')
        if sid in sources:
            previous = sources[sid]
            for key in ('source_kind','report_year','version','supersedes_source_id'):
                if previous.get(key) is not None and row.get(key) is not None and previous[key] != row[key]:
                    raise ValueError(f'Conflicting metadata for same material: {sid}: {key}')
            previous['urls'] = list(dict.fromkeys(previous['urls'] + row['urls']))
            previous['local_paths'] = list(dict.fromkeys(previous['local_paths'] + row['local_paths']))
            # Preserve each submitted record, including unresolved metadata.
            previous.setdefault('mirror_records', []).append(row)
            previous['issues'] = list(dict.fromkeys(previous['issues'] + row['issues']))
            if previous['issues']: previous['metadata_status'] = 'pending_review'
        else: sources[sid] = row
        if x.get('parsed_dir'):
            parsed = Path(x['parsed_dir'])
            parsed = (base/parsed).resolve() if not parsed.is_absolute() else parsed.resolve()
            bindings.append((sid, parsed))
    for row in sources.values():
        ref = row.get('supersedes_source_id')
        if ref:
            if ref == row['source_id']: raise ValueError('A source cannot supersede itself')
            if ref not in sources: row['issues'].append('superseded_source_not_in_registry')
            elif sources[ref]['company_id'] != row['company_id']:
                raise ValueError('Correction reference crosses company boundary')
        if row['issues']: row['metadata_status'] = 'pending_review'
    return list(sources.values()), bindings

def link_parsed(source, parsed):
    manifest = json.loads((parsed/'parse_manifest.json').read_text())
    if manifest.get('source_file_sha256', manifest.get('source_pdf_sha256')) != source['file_sha256']:
        raise ValueError('Parser manifest does not match registered PDF')
    result = {}
    for filename in ('retrieval_chunks.jsonl','retrieval_units.jsonl'):
        rows = [json.loads(line) for line in (parsed/filename).read_text().splitlines() if line.strip()]
        for row in rows:
            if row.get('source_id') != source['file_sha256']:
                raise ValueError(f'Unexpected parser source_id: {filename}')
            row['parser_source_id'] = row['source_id']
            row.update(source_id=source['source_id'], company_id=source['company_id'],
                       source_level=source['source_level'], source_kind=source['source_kind'],
                       report_year=source['report_year'], metadata_status=source['metadata_status'],
                       evidence_issues=source.get('evidence_issues') or [])
        result[filename] = rows
    return result

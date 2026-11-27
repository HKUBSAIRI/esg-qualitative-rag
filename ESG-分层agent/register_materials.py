"""Register JSON/JSONL input; never modify original parser artifacts."""
import argparse
import json
from pathlib import Path
from material_registry.core import build_registry, link_parsed

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    text=a.input.read_text(encoding='utf-8')
    entries=json.loads(text) if text.lstrip().startswith('[') else [json.loads(s) for s in text.splitlines() if s.strip()]
    sources, bindings=build_registry(entries, a.input.resolve().parent)
    lookup={x['source_id']:x for x in sources}
    # Validate all links before writing output.
    linked={}
    for sid, parsed in bindings:
        data=link_parsed(lookup[sid],parsed)
        if sid in linked and linked[sid] != data: raise ValueError('Conflicting parse outputs for same source')
        linked[sid]=data
    a.output.mkdir(parents=True,exist_ok=True)
    def write(path, rows):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(path.suffix+'.tmp')
        temp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        temp.replace(path)
    write(a.output/'sources.jsonl',sources)
    for sid, data in linked.items():
        for filename, rows in data.items(): write(a.output/'linked'/sid/filename,rows)
    summary=dict(materials=len(sources), parsed_materials=len(linked),
                 pending_review=sum(x['metadata_status']=='pending_review' for x in sources))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))

if __name__=='__main__': main()

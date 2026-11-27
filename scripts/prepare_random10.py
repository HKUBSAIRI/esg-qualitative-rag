"""One-time data migration from historical manifests; imports local parser only."""
import json,random,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pdf_parser.pipeline import build_final_artifacts
from pdf_parser.common import sha256_file
legacy=ROOT.parent/'RAG3.0'
codes=json.loads((legacy/'inputs/all20_codes.json').read_text())
selected=random.Random(20261127).sample(codes,10)
companies={c['code']:c for c in json.loads((legacy/'inputs/companies.json').read_text())}
run=ROOT/'runs/random10_20261127';run.mkdir(parents=True,exist_ok=True)
(run/'selection.json').write_text(json.dumps(dict(seed=20261127,population=codes,selected=[companies[c] for c in selected]),ensure_ascii=False,indent=2))
entries=[];inventory=[]
for code in selected:
    history=json.loads((legacy/'runs'/code/'source_classification.json').read_text())
    for d in history['documents']:
        cl=d.get('classification',{})
        inventory.append(dict(company_id=code,legacy_id=d['id'],title=d.get('title'),classification=cl,url=d.get('url'),included_this_run=d['id']==code+'_primary'))
    d=next(d for d in history['documents'] if d['id']==code+'_primary')
    assert d.get('official') is True
    cl=d['classification'];assert cl['kind']=='esg' and cl['report_year']==2025 and cl.get('basis')
    pdf=Path(d['path']);sha=sha256_file(pdf)
    oldmanifest=Path(companies[code]['parsed']).parent/'parse_manifest.json'
    old=json.loads(oldmanifest.read_text());assert old['source_pdf_sha256']==sha
    raw=Path(old['docling_json'])
    if not raw.exists():
        matches=list((oldmanifest.parent/'raw').rglob(code+'_2025.json'))
        if len(matches)!=1: raise ValueError(f'Cannot uniquely resolve raw JSON for {code}')
        raw=matches[0]
    folder=run/'materials'/code;folder.mkdir(parents=True,exist_ok=True)
    localpdf=folder/'report_2025.pdf';localraw=folder/'docling.json'
    shutil.copy2(pdf,localpdf);shutil.copy2(raw,localraw)
    parsed=run/'parsed'/code
    summary=build_final_artifacts(localpdf.resolve(),localraw.resolve(),parsed.resolve())
    entries.append(dict(company_id=code,company_name=companies[code]['company'],local_path=str(localpdf.resolve()),parsed_dir=str(parsed.resolve()),file_sha256=sha,title=d['title'],publisher=companies[code]['company'],source_kind='esg',report_year=2025,period=cl.get('period'),original_url=d['url'],classification_basis=cl['basis'],official_verified=True,version=None,metadata_origin='inherited_official_material_manifest'))
    (run/'materials_input.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2))
    print(code,companies[code]['company'],summary['page_count'],summary['enriched_chunk_count'],flush=True)
(run/'remaining_materials_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))

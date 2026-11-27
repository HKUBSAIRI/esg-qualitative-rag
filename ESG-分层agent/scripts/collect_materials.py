"""Gather a traceable baseline corpus; no retrieval or scoring LLM calls."""
import json,shutil,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import httpx
import fitz

def pdf_texts(path):
    with fitz.open(path) as doc: return [page.get_text() for page in doc]

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'runs/random10_20261127';OUT=RUN/'materials_preparation';OUT.mkdir(parents=True,exist_ok=True)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
companies=json.loads((RUN/'selection.json').read_text())['selected'];entries=[];excluded=[]
# Collect full relevant-period reports, all policy/governance resources, and
# preserve discovery landing pages. Relevance and effectiveness remain unverified.
for c in companies:
    docs=json.loads((ROOT.parent/'RAG3.0/runs'/c['code']/'source_classification.json').read_text())['documents']
    for d in docs:
        cl=d.get('classification',{});kind=cl.get('kind');year=cl.get('report_year');path=Path(d.get('path',''))
        reason=None
        if not d.get('official'):reason='official_origin_not_confirmed'
        elif kind in {'esg','annual','interim','announcement'} and year not in {2024,2025}:reason='outside_baseline_period'
        elif year and year>2025:reason='later_period_material_not_2025_evidence'
        if reason:
            excluded.append(dict(company_id=c['code'],legacy_id=d['id'],reason=reason,url=d.get('url')));continue
        if not path.is_file():
            excluded.append(dict(company_id=c['code'],legacy_id=d['id'],reason='missing_local_file',url=d.get('url')));continue
        filehash=sha(path);folder=OUT/'files'/c['code'];folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(filehash+path.suffix.lower());shutil.copy2(path,dest)
        level=1 if kind=='esg' and path.suffix.lower()=='.pdf' else 2 if kind in {'annual','interim'} else 3 if kind in {'policy','announcement'} else None
        if 'court_employee' in d['id']:level=4;kind='official_judicial_notice'
        row=dict(company_id=c['code'],company_name=c['company'],title=d.get('title'),original_url=d.get('url'),entry_url=d.get('entry_url'),hosted_url=d.get('resolved_url'),source_kind=kind,source_level=level,report_year=year,period=cl.get('period'),classification_basis=cl.get('basis'),local_path=str(dest.resolve()),file_sha256=filehash,legacy_id=d['id'],metadata_origin='historical_official_manifest',official_origin_status='inherited_not_refetched',effective_from=cl.get('effective_from'),relevance_status='not_reviewed',issues=[])
        if level is None:row['issues'].append('source_kind_requires_content_classification')
        entries.append(row)

new=[
('01548','2025年度报告','annual',2025,'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0413/2026041300568_c.pdf'),
('01093','2025年度报告','annual',2025,'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0428/2026042803421.pdf'),
('01177','2025年度报告','annual',2025,'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0429/2026042901036.pdf'),
('02269','2025年度报告','annual',2025,'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0429/2026042900764.pdf'),
('01801','人权与多元化政策','policy',None,'https://investor.innoventbio.com/media/1204/人权与多元化政策.pdf'),
('01801','商业道德行为准则','policy',None,'https://investor.innoventbio.com/media/1206/商业道德行为准则.pdf'),
('01548','Diversity Equity and Inclusion Policy','policy',None,'https://www.genscript.com/gsfiles/esg/Diversity_Equity_and_Inclusion_Policy.pdf'),
('01548','Business Conduct Guidelines','policy',None,'https://www.genscript.com/gsfiles/esg/Business_Conduct_Guidelines.pdf'),
('01548','Whistleblowing and Investigation Policy','policy',None,'https://www.genscript.com/gsfiles/esg/Whistleblowing_and_Investigation_Policy.pdf'),
('01548','ESG Reports & Resources','governance',None,'https://www.genscript.com/esg-resources.html'),
('01548','Creating Social Value','governance',None,'https://www.genscript.com/social.html'),
('01548','Our Business Conduct','governance',None,'https://www.genscript.com/our-business-conduct.html')]
lookup={c['code']:c for c in companies}
def download(task):
    code,title,kind,year,url=task;folder=OUT/'files'/code;folder.mkdir(parents=True,exist_ok=True)
    cached=folder/(hashlib.sha256(url.encode()).hexdigest()+'.download.json')
    if cached.exists():return json.loads(cached.read_text())
    try:
        with httpx.Client(timeout=httpx.Timeout(90,connect=20),follow_redirects=True,transport=httpx.HTTPTransport(local_address='0.0.0.0')) as client:
            r=client.get(url);r.raise_for_status()
        ispdf=r.content.startswith(b'%PDF-');suffix='.pdf' if ispdf else '.html'
        if url.endswith('.pdf') and not ispdf:raise ValueError('Expected PDF; received another format')
        h=hashlib.sha256(r.content).hexdigest();dest=folder/(h+suffix);dest.write_bytes(r.content)
        row=dict(company_id=code,company_name=lookup[code]['company'],title=title,original_url=url,hosted_url=str(r.url),source_kind=kind,source_level=2 if kind=='annual' else 3,report_year=year,local_path=str(dest.resolve()),file_sha256=h,metadata_origin='official_link_discovery_20261127',official_origin_status='downloaded_official_endpoint',relevance_status='not_reviewed',issues=[])
        cached.write_text(json.dumps(row,ensure_ascii=False,indent=2));return row
    except Exception as e:return dict(company_id=code,title=title,url=url,status='download_failed',error_type=type(e).__name__)
# Check local PDFs before network calls, including whether image-only material needs OCR.
for e in entries:
    p=Path(e['local_path'])
    if p.suffix=='.pdf':
        try:
            texts=pdf_texts(p)
            e.update(page_count=len(texts),text_characters=sum(map(len,texts)),low_text_pages=[i+1 for i,t in enumerate(texts) if len(t.strip())<40],readability_status='pdf_opened')
            if sum(map(len,texts))<40:e['issues'].append('image_only_or_text_unreadable_requires_ocr')
        except Exception as ex:e['issues'].append('pdf_read_error:'+type(ex).__name__)
save('local_inventory.json',entries);save('excluded.json',excluded)
with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(download,new))
save('downloads.json',results)
for e in results:
    if e.get('local_path'):
        p=Path(e['local_path'])
        if p.suffix=='.pdf':
            texts=pdf_texts(p);e.update(page_count=len(texts),text_characters=sum(map(len,texts)),low_text_pages=[i+1 for i,t in enumerate(texts) if len(t.strip())<40],readability_status='pdf_opened',identity_excerpt='\n'.join(texts[:3])[:5000])
        entries.append(e)
# Do not silently discard mirror URLs.
merged={}
for e in entries:
    key=(e['company_id'],e['file_sha256'])
    if key in merged:
        merged[key].setdefault('mirror_records',[]).append(e)
    else:merged[key]=e
save('inventory.json',list(merged.values()))
summary=[]
for c in companies:
    docs=[e for e in merged.values() if e['company_id']==c['code']]
    summary.append(dict(company_id=c['code'],company_name=c['company'],materials=len(docs),L1_2025=sum(e['source_level']==1 and e.get('report_year')==2025 for e in docs),L2_annual_2025=sum(e['source_level']==2 and e['source_kind']=='annual' and e.get('report_year')==2025 for e in docs),L3=sum(e['source_level']==3 for e in docs),L4=sum(e['source_level']==4 for e in docs),unclassified=sum(e['source_level'] is None for e in docs),collection_complete=False))
save('coverage.json',summary)
print(json.dumps(dict(materials=len(merged),downloads_ok=sum('local_path' in e for e in results),download_failures=[e for e in results if 'local_path' not in e]),ensure_ascii=False),flush=True)

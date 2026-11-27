"""Local classification and parsing orchestration. Third-party Docling CLI is explicit."""
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pdf_parser.pipeline import build_final_artifacts
from html_parser import parse_html
from material_registry.core import build_registry,link_parsed
RUN=ROOT/'runs/random10_20261127';PREP=RUN/'materials_preparation';OUT=RUN/'layered';OUT.mkdir(parents=True,exist_ok=True)

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));temp.replace(path)
def jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
def classify():
    catalog=[json.loads(x) for x in (PREP/'material_catalog.jsonl').read_text().splitlines()];plan=[]
    discovery=('投资者关系','投资者互动','公告与通函','ESG报告与资源','ESG报告与资源','ESG报告','查看 ESG 报告','财务报告','投资者活动','投资者关系日历','投资者联系方式','新闻','ESG动态')
    for original in catalog:
        e=dict(original);kind=e.get('source_kind');year=e.get('report_year');title=str(e.get('title') or '')
        # New officially downloaded metadata resolves historical unclassified mirrors.
        for m in e.get('mirror_records',[]):
            if m.get('official_origin_status')=='downloaded_official_endpoint' and m.get('source_kind')=='annual':
                for k in ('title','source_kind','source_level','report_year','original_url','hosted_url','identity_excerpt'):e[k]=m.get(k)
                kind=e['source_kind'];year=e['report_year'];title=e['title']
        e['classification_action']='retain_existing_with_basis'
        if kind in (None,'other'):
            if Path(e['local_path']).suffix=='.html':
                e.update(source_kind='governance' if any(t in title.lower() for t in ('治理','管治','governance','法规依从')) else 'announcement',source_level=3,classification_action='official_web_disclosure_by_document_title')
            elif '现代奴隶' in title:e.update(source_kind='policy',source_level=3,classification_action='modern_slavery_statement')
            elif any(t in title for t in ('董事名单','董事名單','公司章程')):e.update(source_kind='governance',source_level=3,classification_action='governance_document')
        if kind=='interim':e.update(source_kind='financial_statement',source_level=2)
        reason=None
        if e.get('source_level') is None:reason='unresolved_document_type'
        elif e.get('source_level')==4:reason='scan_ocr_and_subject_relationship_require_review'
        elif e['source_kind'] in ('esg','annual','financial_statement','announcement') and year and year!=2025:reason='outside_2025_baseline; retained_in_archive'
        elif Path(e['local_path']).suffix=='.html' and title.strip() in discovery:reason='discovery_landing_page_not_evidence'
        elif any(t in title.lower() for t in ('隐私','privacy','气候风险','climate-related','动物福利','animal welfare','clinical research','patient organizations','marketing','营销','集团税务','供应商行为','商业合作伙伴行为','product stewardship','anti-counterfeit')):reason='outside_employee_rights_scope; retained_in_archive'
        elif any(t in title for t in ('2026','MSCI','标普全球','恒生','奖项','荣膺')):reason='later_period_or_rating_news; retained_in_archive'
        if e['company_id']=='06160' and title in ('English','German','Learn More'):reason='unresolved_policy_topic; retained_for_review'
        e['processing_status']='excluded_with_reason' if reason else 'planned'
        e['exclusion_reason']=reason
        e['publisher']=e['company_name'];e['official_verified']=True
        if not e.get('title'):
            e['title']=Path(e['local_path']).name
            e['title_status']='filename_only; descriptive_title_unconfirmed'
        e['classification_basis']=e.get('classification_basis') or ('文件内容/原始标题及官方材料记录：'+title)
        e['evidence_issues']=list(e.get('issues') or [])
        if e.get('source_level')==3:e['evidence_issues']=list(dict.fromkeys(e['evidence_issues']+['2025_effectiveness_requires_evidence']))
        e['parsed_dir']=str((OUT/'parsed'/e['company_id']/e['file_sha256']).resolve())
        plan.append(e)
    save(OUT/'classification_plan.json',plan);return plan

def main():
    p=argparse.ArgumentParser();p.add_argument('--docling',default=str(ROOT/'docling_cli.py'));p.add_argument('--docling-python');p.add_argument('--plan-only',action='store_true');p.add_argument('--workers',type=int,default=3);a=p.parse_args()
    plan=classify();jobs=[e for e in plan if e['processing_status']=='planned']
    cache=json.loads((PREP/'raw_cache_inventory.json').read_text())
    print(json.dumps(dict(planned=len(jobs),pdf=sum(e['local_path'].endswith('.pdf') for e in jobs),html=sum(e['local_path'].endswith('.html') for e in jobs),fresh_docling=sum(e['local_path'].endswith('.pdf') and e['file_sha256'] not in cache for e in jobs)),ensure_ascii=False),flush=True)
    if a.plan_only:return
    if not a.docling:raise ValueError('--docling CLI is required')
    def process(e):
        dest=Path(e['parsed_dir']);dest.mkdir(parents=True,exist_ok=True);manifest=dest/'parse_manifest.json'
        if manifest.exists() and (dest/'retrieval_units.jsonl').exists():
            m=json.loads(manifest.read_text())
            if m.get('source_file_sha256',m.get('source_pdf_sha256'))==e['file_sha256']:return e
        pdf=Path(e['local_path'])
        if pdf.suffix=='.html':parse_html(pdf,dest);return e
        raw=dest/'raw/docling.json';raw.parent.mkdir(parents=True,exist_ok=True)
        if not raw.exists():
            if e['file_sha256'] in cache:shutil.copy2(cache[e['file_sha256']],raw)
            else:
                env={**os.environ,'OMP_NUM_THREADS':'2','DOCLING_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'}
                with (dest/'docling.log').open('w') as log:
                    cp=subprocess.run(([a.docling_python] if a.docling_python else [])+[a.docling,str(pdf),'--from','pdf','--to','json','--image-export-mode','placeholder','--no-ocr','--abort-on-error','--output',str(raw.parent)],env=env,stdout=log,stderr=log,timeout=14400)
                if cp.returncode:raise RuntimeError('Docling failed; inspect docling.log')
                found=raw.parent/(pdf.stem+'.json')
                if not found.exists():raise RuntimeError('Docling JSON not produced')
                found.replace(raw)
        build_final_artifacts(pdf,raw,dest);return e
    done=[];errors=[]
    # Start with short documents to validate the runtime before long annual reports.
    jobs.sort(key=lambda e:e.get('page_count',0))
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(process,e):e for e in jobs}
        for f in concurrent.futures.as_completed(futures):
            e=futures[f]
            try:done.append(f.result());print('PARSED',e['company_id'],e['source_kind'],len(done),'/',len(jobs),flush=True)
            except Exception as ex:errors.append(dict(source_id=e['source_id'],title=e['title'],error_type=type(ex).__name__,reason=str(ex)[:300]));print('FAILED',e['company_id'],e['title'],type(ex).__name__,flush=True)
            save(OUT/'parse_progress.json',dict(total=len(jobs),done=len(done),errors=errors))
    registry=OUT/'registry';sources,bindings=build_registry(done,ROOT)
    jsonl(registry/'sources.jsonl',sources);lookup={s['source_id']:s for s in sources}
    for sid,parsed in bindings:
        for filename,rows in link_parsed(lookup[sid],parsed).items():jsonl(registry/'linked'/sid/filename,rows)
    save(OUT/'registry_summary.json',dict(sources=len(sources),pending_metadata=sum(s['metadata_status']!='registered' for s in sources),errors=errors,excluded=[dict(source_id=e['source_id'],reason=e['exclusion_reason']) for e in plan if e['exclusion_reason']]))
    if errors:raise SystemExit('Some parses failed; see parse_progress.json')
if __name__=='__main__':main()

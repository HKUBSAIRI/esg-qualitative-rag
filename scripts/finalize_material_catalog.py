"""Consolidate collected originals and make unresolved scope explicit."""
import json,hashlib
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'runs/random10_20261127/materials_preparation'
load=lambda name:json.loads((BASE/name).read_text())
entries=load('local_inventory.json')+[x for x in load('downloads.json') if x.get('local_path')]
entries += [x for name in ('official_cn_downloads.json','official_cn_policies.json') for x in load(name) if x.get('local_path')]
merged={}
for e in entries:
    key=e['company_id'],e['file_sha256']
    if key in merged:
        old=merged[key]
        old.setdefault('mirror_records',[]).append(dict(e))
        # Content-confirmed downloaded year/type resolves older unclassified entries.
        for field in ('source_kind','source_level','report_year','title'):
            if old.get(field) in (None,'','other') and e.get(field) not in (None,'','other'):old[field]=e[field]
    else:merged[key]=dict(e)
for e in merged.values():
    p=Path(e['local_path']);assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==e['file_sha256']
    e['source_id']=e['company_id']+'_'+e['file_sha256']
    e['actual_collection_date']='2026-11-27'
    e['search_complete']=False;e['quote_match']=None
    if p.suffix=='.pdf':
        with fitz.open(p) as doc:
            e['page_count']=len(doc);e['text_characters']=sum(len(pg.get_text()) for pg in doc)
        e['readability_status']='pdf_opened'
    else:e['readability_status']='html_snapshot_saved'
    if e.get('source_level') is None:
        e['material_role']='discovery_or_unclassified';e['index_eligible']=False
    else:e['material_role']='candidate_evidence';e['index_eligible']=True
    if e.get('source_level')==4:
        e['ocr_sidecar']=str((BASE/'ocr'/e['file_sha256']/'pages.json').resolve())
        e['readability_status']='scan_with_local_ocr_unverified';e['index_eligible']=False
        e['issues']=list(dict.fromkeys(e.get('issues',[])+['ocr_quote_and_subject_relationship_require_verification']))
    if e['title']=='ESG报告与资源':
        e['material_role']='discovery_landing_page';e['index_eligible']=False
    if e.get('source_level')==3 and e.get('effective_from') in (None,'未说明'):
        e['issues']=list(dict.fromkeys(e.get('issues',[])+['2025_effectiveness_not_yet_verified']))
rows=list(merged.values())
(BASE/'material_catalog.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in rows))
companies=json.loads((ROOT/'runs/random10_20261127/selection.json').read_text())['selected'];summary=[]
for c in companies:
    docs=[x for x in rows if x['company_id']==c['code']]
    counts={f'L{n}':sum(x.get('source_level')==n for x in docs) for n in range(1,5)}
    annual=[x for x in docs if x.get('source_kind')=='annual' and x.get('report_year')==2025]
    esg=[x for x in docs if x.get('source_kind')=='esg' and x.get('report_year')==2025]
    assert annual and esg,c['code']
    summary.append(dict(company_id=c['code'],company_name=c['company'],materials=len(docs),**counts,unclassified=sum(x.get('source_level') is None for x in docs),annual2025_ids=[x['source_id'] for x in annual],esg2025_ids=[x['source_id'] for x in esg],baseline_reports_collected=True,full_search_complete=False))
(BASE/'coverage.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
checks=[]
for c in companies:
 for ind in ['S1.1.2 C','S1.1.3','S1.1.4','S1.1.5']:
  checks.append(dict(company_id=c['code'],indicator_id=ind,check_id='official_adverse_event',status='pending_review',search_complete=False,discovery_log='search_logs/four_topics_'+c['code']+'.json',issues=['preparation_discovery_only; execute_independent_check_after_ordinary_sources']))
(BASE/'independent_checks_preparation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
lines=['# 随机10家材料准备清单','','范围：2025年定性评价。历史2024报告作背景备查，不执行定量。资料收集日2026-11-27。','','| 企业代码 | 企业 | 材料数 | L1 | L2 | L3 | L4 | 未分类线索 |','|---|---|---:|---:|---:|---:|---:|---:|']
for s in summary:lines.append('|'+ '|'.join(str(s[k]) for k in ['company_id','company_name','materials','L1','L2','L3','L4','unclassified'])+'|')
lines+=['','10家均有2025年ESG主报告与2025年年报。年报包含审计报告、财务报表和附注，未拆成伪独立材料。','', '已收集的政策包括人权、多元化、举报与调查、员工申诉等，同时保留官网治理和资源入口；是否适用普通员工及2025年仍需后续原文判定。未分类线索不可直接入正式索引。','','金斯瑞英文原件及部分网页403，已通过明确的中文官网原件链接补齐三份中文政策，英文失败日志保留。中文资源入口见 https://www.genscript.com.cn/esg-resources.html?src=pullmenu 。','','上海上药康希诺职工债权公示原件5页为扫描件，已在本机生成OCR副本及页图，不自动确认集团归属、严重性或纠正状态。不得将扫描正文无文本误记为无披露。','','40条独立核查准备记录均保持pending_review；本轮完成材料发现查询，不提前冒充规则要求的正式独立核查。没有发现通报不等于确认无严重事项。','','本清单证明已知基线材料落地，不证明所有公开材料均已穷尽。后续按缺项发现的新材料需增量补齐。尚未执行补充材料的正式解析、分层向量建库、检索Agent或评分。']
(BASE/'材料准备清单.md').write_text('\n'.join(lines)+'\n')
print('PASS',len(summary),'companies; ESG2025+annual2025 complete;',len(rows),'unique materials;',len(checks),'independent check preparation records')

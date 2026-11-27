"""Finalize bounded HKEX-only discovery; retain known unresolved case leads."""
import json,re,hashlib,sys
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/hkex_l4';batch=ROOT/'runs/full5_20261127'
for code in (sys.argv[1].split(',') if len(sys.argv)>1 else ['03692','01801','02269','01177','06185']):
 folder=OUT/code;title=json.loads((folder/'title_search.json').read_text());content=json.loads((folder/'content_discovery.json').read_text());lookup={x['FILE_LINK'].lower():x for x in title['records']};exclusions=[]
 for row in title['candidates']:
  if re.search(r'欠薪|扣薪|勞動爭議|劳动争议|訴訟|诉讼|仲裁|歧視|歧视|騷擾|骚扰|處罰|处罚|違法|违法',row['TITLE']):raise ValueError('Case candidate needs original review: '+row['official_url'])
  exclusions.append(dict(url=row['official_url'],title=row['TITLE'],decision='not_employee_adverse_case',basis='标题明确为普通业务、融资、业绩、股权交易、员工购股计划、审计聘任或薪酬委员会制度，不是员工严重侵权具体通报'))
 for url in dict.fromkeys(re.findall(r'https://[^\s)]+\.pdf',content['result'])):
  row=lookup.get(urlsplit(url).path.lower())
  if row and (re.search(r'報告|报告|年報|年报|通函',row['TITLE'])):
   exclusions.append(dict(url=url,title=row['TITLE'],decision='ordinary_report_not_L4',basis='与官方公司公告目录匹配，性质为ESG/年报/中报，保留原层级，不重复全文阅读'))
  elif re.search(r'/sehk/(?:19\d{2}|20(?:0\d|1\d|2[0-4]))/',url):
   exclusions.append(dict(url=url,decision='outside_discovery_period',basis='发布早于本次检索2025-01-01起始日；不作为2025严重事项通报'))
  elif code=='02269' and '2026021200062' in url:
   exclusions.append(dict(url=url,decision='different_issuer_transaction_circular',basis='已下载原件核对封面及目录：股份代号2268，药明合联收购东曜药业通函；并非2269员工侵权通报',local_path=str((folder/'unmatched_appendix.pdf').resolve())))
  elif code=='06160' and '2026022701671' in url:
   exclusions.append(dict(url=url,decision='statutory_financial_statements_not_L4',basis='已打开原件核对封面与审计报告，为2025年瑞士法定财务报表公告，不是员工侵权事项通报',local_path=str((folder/'business_update_20260227.pdf').resolve())))
  else:raise ValueError('Unresolved content candidate: '+url)
 if not title['search_complete'] or len(title['records'])!=title['total']:raise ValueError('Incomplete title coverage')
 logs=[dict(source_type='HKEX_official_title_search',url=title['request_url'],period=['2025-01-01','2026-11-27'],stock=title['stock'],records=title['total'],pagination_complete=True),dict(source_type='HKEX_domain_content_discovery',queries=content['queries'],raw_result_path=str((folder/'content_discovery.json').resolve()),limitation='官网内容搜索脚本不可用，补查使用限定hkexnews.hk域名的网页索引；搜索摘要不作为事实证据'),dict(source_type='candidate_screening',exclusions=exclusions)]
 checks=[]
 for indicator in ['S1.1.2 C','S1.1.3','S1.1.4','S1.1.5']:
  issues=[]
  if code=='06185' and indicator in {'S1.1.2 C','S1.1.4'}:
   issues=[dict(kind='existing_official_case_lead_unresolved',title='上海上药康希诺职工债权公示',reason='此前已保存的官方司法线索尚需核实主体关系、债权性质及处理状态。此次披露易未找到不消除该已知线索，也不据此认定严重违规。')]
  checks.append(dict(indicator_id=indicator,check_id='official_adverse_event',evidence=[],search_log=logs,search_complete=not issues,source_scope='HKEX指定公司公告目录及限定域名内容检索，2025-01-01至2026-11-27；非全监管/司法渠道无事件证明',retrieval_status='pending_review' if issues else 'no_relevant_evidence_found',issues=issues,judgment=dict(state='pending_review' if issues else 'no_verified_adverse_event_found',reason='已完成本次指定披露易查找范围，未发现可核实的员工相关严重事项通报。结论不保证未发生或未在其他渠道披露。'+('已知职工债权司法线索仍待核实。' if issues else ''),unresolved=issues,evidence_ids=[])))
 (folder/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
 print(code,'HKEX titles',title['total'],'exclusions',len(exclusions),'unresolved checks',sum(bool(c['issues']) for c in checks))

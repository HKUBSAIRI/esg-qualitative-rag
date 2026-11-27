"""Only HKEXnews official title search. Persist complete paginated title coverage."""
import sys,json,time,hashlib,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/hkex_l4';OUT.mkdir(exist_ok=True,parents=True)
STOCKS=json.loads((OUT/'stocks.json').read_text(encoding='utf-8-sig'));CODES=sys.argv[1].split(',') if len(sys.argv)>1 else ['03692','01801','02269','01177','06185']
POS=r'欠薪|扣薪|工资|工資|薪酬|勞動|劳动|勞工|劳工|工時|工时|休假|裁員|裁员|遣散|解僱|解雇|雇員|僱員|员工|員工|福利|社保|歧視|歧视|騷擾|骚扰|訴訟|诉讼|仲裁|處罰|处罚|罰款|罚款|制裁|調查|调查|違規|违规|違法|违法|內幕消息|内幕消息|wage|labour|labor|dismiss|redundan|litigation|arbitration|penalt|harass|discriminat'
EXCLUDE=r'月報表|月报表|翌日披露|年報|年报|年度報告|年度报告|中期報告|中期报告|可持續發展|可持续发展|環境.*社會|环境.*社会|企業管治報告|环境、社会及管治|ESG|annual report|interim report|monthly return'
def fetch(code):
 stock=next(s for s in STOCKS if s['c']==code);folder=OUT/code;folder.mkdir(exist_ok=True)
 params=dict(sortDir='0',sortByOptions='DateTime',category='0',market='SEHK',stockId=str(stock['i']),documentType='-1',fromDate='20250101',toDate='20261127',title='',searchType='1',t1code='-2',t2Gcode='-2',t2code='-2',rowRange='100',lang='ZH')
 with httpx.Client(timeout=60,follow_redirects=True,transport=httpx.HTTPTransport(local_address='0.0.0.0')) as client:
  for attempt in range(3):
   try:
    x=client.get('https://www1.hkexnews.hk/search/titleSearchServlet.do',params=params);x.raise_for_status();data=x.json();records=json.loads(data['result']);break
   except (ValueError,httpx.HTTPError):
    if attempt==2:raise
    time.sleep(2)
  (folder/'response_100.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
  total=int(data.get('recordCnt') or (records[0].get('TOTAL_COUNT') if records else 0));params['rowRange']=str(max(100,total))
  if len(records)<total:
   x=client.get('https://www1.hkexnews.hk/search/titleSearchServlet.do',params=params);x.raise_for_status();data=x.json();records=json.loads(data['result'])
  unique={r['NEWS_ID']:r for r in records};records=list(unique.values())
  if len(records)!=total:raise ValueError(f'Incomplete title pagination {code}: {len(records)}/{total}')
  candidates=[]
  for r in records:
   title=r['TITLE'];url='https://www1.hkexnews.hk'+r['FILE_LINK'];r['official_url']=url
   if re.search(EXCLUDE,title,re.I):continue
   if re.search(POS,title,re.I):candidates.append(r)
  report=dict(company_id=code,stock=stock,source='HKEXnews official title search',request_url=str(x.url),params=params,search_complete=True,scope='specified company title search, 2025-01-01 through 2026-11-27; title discovery is not proof of no incident',total=total,records=records,candidates=candidates)
  (folder/'title_search.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  print(code,'titles',total,'candidates',len(candidates),flush=True)
  for r in candidates:print(' ',r['DATE_TIME'],r['TITLE'].replace('\n',' '),r['official_url'],flush=True)
 return report
with ThreadPoolExecutor(max_workers=3) as pool:reports=list(pool.map(fetch,CODES))
(OUT/'search_summary.json').write_text(json.dumps([dict(company_id=r['company_id'],total=r['total'],candidates=len(r['candidates']),search_complete=r['search_complete']) for r in reports],ensure_ascii=False,indent=2))

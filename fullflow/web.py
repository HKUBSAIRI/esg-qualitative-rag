"""Official-source discovery. Search answers/snippets never become evidence."""
import hashlib,json,time
import subprocess,sys,re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import httpx,fitz
from html_parser import parse_html
from retrieval.run_l1 import rows,save

OFFICIAL=('hkexnews.hk','gov.cn','court.gov.cn','gov.hk','eeoc.gov','dol.gov','gov.uk','justice.gov')
def allowed(url,issuer_hosts=()):
 u=urlsplit(url);host=(u.hostname or '').lower()
 domains=set((*OFFICIAL,*issuer_hosts))
 domains.update(d[4:] for d in list(domains) if d.startswith('www.'))
 return u.scheme in {'http','https'} and any(host==d or host.endswith('.'+d) for d in domains)

def search(llm,query,out):
 raise RuntimeError("Online material discovery disabled by user; use local originals")
 """Bridge to connected search tool; search snippets are never evidence."""
 identity=hashlib.sha256(('connected-search-v1:'+query).encode()).hexdigest()
 response=out/'search'/f'{identity}.json'
 if response.exists():
  cached=json.loads(response.read_text())
  if cached.get('backend')=='connected_web_search' and cached.get('search_executed'):return cached
 request=out/'search_requests'/f'{identity}.json'
 save(request,dict(request_id=identity,query=query,response_path=str(response.resolve()),backend='connected_web_search',domains=['hkexnews.hk','gov.cn','court.gov.cn','eeoc.gov','dol.gov','gov.hk','gov.uk'] if '官方监管' in query else [],status='waiting_for_search_tool'))
 started=time.monotonic()
 while time.monotonic()-started<3600:
  if response.exists():
   result=json.loads(response.read_text())
   if result.get('backend')=='connected_web_search' and result.get('search_executed'):return result
  time.sleep(10)
 return dict(query=query,backend='connected_web_search',search_executed=False,results=[],error_type='SearchToolResponseTimeout')

ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def known_sources():
 p=ROOT/'runs/random10_20261127/layered/registry/sources.jsonl'
 return {s['source_id']:s for s in rows(p)}

def source_nature(title,preview,requested):
 t=' '.join((title+' '+preview).lower().split())
 if any(w in t for w in ('esg report','sustainability report','环境、社会','環境、社會','可持续发展报告','可持續發展報告','esg報告','esg报告')):return 1,'esg'
 if any(w in t for w in ('interim report','interim results','中期报告','中期報告','中期業績','中期业绩')):return 2,'financial_statement'
 if any(w in t for w in ('annual report','年报','年報')):return 2,'annual'
 if any(w in t for w in ('financial statements','financial results','年度業績','年度业绩','全年業績','全年业绩')):return 2,'financial_statement'
 return requested,'official_regulatory_notice' if requested==4 else 'policy' if any(w in t for w in ('policy','政策','制度','准则','準則')) else 'announcement'

def classify_pdf(llm,source,preview):
 def validate(obj):
  if obj.get('kind') not in {'esg','annual','financial_statement','policy','announcement','official_regulatory_notice','official_judicial_notice','other'}:raise ValueError('Invalid document kind')
  if obj.get('report_year') is not None and type(obj['report_year']) is not int:raise ValueError('Report year must be an integer or null')
  if not isinstance(obj.get('basis'),str):raise ValueError('Classification needs a basis')
 return llm.ask('pdf_document_nature','仅识别文件性质，不评分，不判断公司有无违法。按文件本身分类，不能根据发现它的检索层级或托管域名分类。封面可能为图片，结合随后目录、关于本报告、页眉页脚识别。ESG/可持续报告=esg；年报=annual；中期报告/业绩财报=financial_statement；具体制度=policy；普通公司公告/通函=announcement。只有披露实际监管或司法事项的通报才是official_regulatory_notice/official_judicial_notice，一般风险提示、财报和ESG报告绝不是通报。无法确认用other。检索标题可能是页面片段或图片标签，不能盲信。年份和发布主体必须有原文依据，否则null/未明确。输出{"kind":"esg","report_year":2024,"publisher":"原文主体或未明确","basis":"文件内容识别依据"}。',dict(title_hint=source['title'],url=source['original_url'],first_pages=preview),validate,max_tokens=1400)

def acquire(item,company,level,out,hosts,llm=None):
 raise RuntimeError("Online material download disabled by user; use local originals")
 url=item.get('url') or item.get('link');entry=dict(url=url,title=item.get('title'),source_opened=False,quote_verified=False)
 if not url or not allowed(url,hosts):return None,[],dict(entry,reason='nonofficial_or_unapproved_host')
 key=hashlib.sha256(('source-nature-v2:'+str(level)+url).encode()).hexdigest();dest=out/'web_sources'/key;dest.mkdir(parents=True,exist_ok=True)
 try:
  stored=dest/'source.json';decision=dest/'classification_decision.json'
  if decision.exists():return None,[],json.loads(decision.read_text())
  if stored.exists():
   s=json.loads(stored.read_text());path=Path(s['local_path'])
  else:
   with httpx.Client(timeout=httpx.Timeout(60,connect=15),transport=httpx.HTTPTransport(local_address='0.0.0.0'),follow_redirects=False) as client:
    current=url
    for _ in range(6):
     if not allowed(current,hosts):raise ValueError('Redirect leaves approved official hosts')
     r=client.get(current)
     if r.is_redirect:
      from urllib.parse import urljoin
      current=urljoin(current,r.headers['location']);continue
     r.raise_for_status();break
    else:raise ValueError('Too many redirects')
   if len(r.content)>50_000_000:raise ValueError('Source exceeds download limit')
   ispdf=r.content.startswith(b'%PDF-');path=dest/('original.pdf' if ispdf else 'original.html');path.write_bytes(r.content);sha=hashlib.sha256(r.content).hexdigest();sid=company['company_id']+'_'+sha
   s=dict(source_id=sid,company_id=company['company_id'],company_name=company['company_name'],title=item.get('title') or path.name,local_path=str(path.resolve()),original_url=url,hosted_url=current,report_year=None,version=None,publisher='原发布主体待原文识别',evidence_issues=['期间与主体关联须从原文核实'],file_sha256=sha)
  ispdf=path.suffix=='.pdf';preview=''
  if ispdf:
   with fitz.open(path) as pdf:
    preview='\n'.join(pdf[i].get_text() for i in range(min(5,len(pdf))))[:16000]
    if not any(page.get_text().strip() for page in pdf):raise ValueError('Scanned source requires visual/OCR review')
  actual_level,kind=source_nature(s['title'],preview,level)
  known=known_sources().get(s['source_id'])
  if known:actual_level,kind=known['source_level'],known['source_kind']
  elif ispdf and llm is not None:
   metadata=classify_pdf(llm,s,preview);kind=metadata['kind']
   actual_level={'esg':1,'annual':2,'financial_statement':2,'policy':3,'announcement':3,'official_regulatory_notice':4,'official_judicial_notice':4}.get(kind)
   s.update(report_year=metadata.get('report_year'),publisher=metadata.get('publisher') or '未明确',classification_basis=metadata['basis'])
   if actual_level is None:return None,[],dict(entry,reason='official_source_unreadable',detail='document_nature_unconfirmed')
  if level==4 and actual_level!=4:
   skipped=dict(entry,reason='ordinary_report_not_independent_notice',actual_source_level=actual_level);save(decision,skipped);return None,[],skipped
  s.update(source_level=actual_level,source_kind=kind)
  if known:
   s=dict(known,discovered_url=url)
   linked=ROOT/'runs/random10_20261127/layered/registry/linked'/s['source_id']/'retrieval_chunks.jsonl'
   chunks=rows(linked)
  elif ispdf:
   parsed=dest/'parsed'
   if not (parsed/'retrieval_chunks.jsonl').exists():
    runtime=ROOT/'config/runtime.json'
    if not runtime.exists():raise ValueError('Docling runtime configuration missing')
    python=json.loads(runtime.read_text())['docling_python']
    with (dest/'parse.log').open('a') as log:
     subprocess.run([sys.executable,str(ROOT/'parse_pdf.py'),'parse',str(path),'--docling',str(ROOT/'config/docling_runner'),'--output',str(parsed)],stdout=log,stderr=log,timeout=14400,check=True)
   chunks=rows(parsed/'retrieval_chunks.jsonl')
  else:
   text=path.read_text(errors='replace')
   if len(text)<50000 and any(w in text.lower() for w in ('<title>access denied','<title>just a moment','<title>403 forbidden')):raise ValueError('Official website returned access interstitial')
   parsed=dest/'parsed_html';parse_html(path,parsed);chunks=rows(parsed/'retrieval_chunks.jsonl')
  for c in chunks:c['source_id']=s['source_id']
  if not chunks:raise ValueError('No content extracted')
  (dest/'retrieval_chunks.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks));save(stored,s)
  return s,chunks,dict(entry,source_opened=True,source_id=s['source_id'],source_level=s['source_level'],pages=sorted({n for c in chunks for n in c['pages']}),location='physical_pages' if ispdf else 'HTML_element_order')
 except (httpx.HTTPError,ValueError,RuntimeError,subprocess.SubprocessError) as e:
  return None,[],dict(entry,reason='official_source_unreadable',error_type=type(e).__name__)

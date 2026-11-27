import json,hashlib,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'runs/random10_20261127/materials_preparation'
tasks=[('Business Conduct Guidelines','https://www.genscript.com/gsfiles/esg/Business_Conduct_Guidelines.pdf?=2'),('Diversity Equity and Inclusion Policy','https://www.genscript.com/gsfiles/esg/Diversity_Equity_and_Inclusion_Policy.pdf?=2025'),('Whistleblowing and Investigation Policy','https://www.genscript.com/gsfiles/esg/Whistleblowing_and_Investigation_Policy.pdf')]
rows=[]
with httpx.Client(timeout=45,follow_redirects=True,transport=httpx.HTTPTransport(local_address='0.0.0.0'),headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.genscript.com/esg-resources.html'}) as client:
 for title,url in tasks:
  try:
   r=client.get(url);print(title,r.status_code,flush=True);r.raise_for_status()
   if not r.content.startswith(b'%PDF-'):raise ValueError('Not PDF')
   h=hashlib.sha256(r.content).hexdigest();dest=p/'files/01548'/(h+'.pdf');dest.write_bytes(r.content)
   rows.append(dict(company_id='01548',company_name='金斯瑞生物科技股份有限公司',title=title,original_url=url,entry_url='https://www.genscript.com/esg-resources.html',hosted_url=str(r.url),source_kind='policy',source_level=3,report_year=None,file_sha256=h,local_path=str(dest.resolve()),official_origin_status='downloaded_official_endpoint',issues=[],relevance_status='not_reviewed'))
  except Exception as e:rows.append(dict(company_id='01548',title=title,url=url,status='download_failed',error_type=type(e).__name__))
(p/'retry_downloads.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))

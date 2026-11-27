import sys,json
from pathlib import Path
from urllib.parse import urlsplit
import httpx,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.llm import LLM
llm=LLM(sys.argv[1],ROOT/'runs/full5_20261127/search_transport_probe')
endpoint=urlsplit(llm.base)._replace(path='/api/v1/services/aigc/text-generation/generation',query='',fragment='').geturl()
with httpx.Client(timeout=60,transport=httpx.HTTPTransport(local_address='0.0.0.0')) as client:
 r=client.post(endpoint,headers={'Authorization':'Bearer '+llm.key},json=dict(model=llm.model,input={'messages':[{'role':'user','content':'翰森制药 2025 欠薪 官方通报'}]},parameters={'enable_search':True,'search_options':{'forced_search':True,'enable_source':True},'result_format':'message','enable_thinking':False,'max_tokens':1000}))
 if r.status_code!=200:
  obj=r.json();print('native',r.status_code,obj.get('code'),str(obj.get('message',''))[:300])
 r=client.get('https://www.bing.com/search',params={'format':'rss','q':'"翰森制药" 2025 工资 site:hkexnews.hk'})
 print('rss',r.status_code,'xml_items',len(ET.fromstring(r.text).findall('./channel/item')) if r.status_code==200 and r.text.lstrip().startswith('<?xml') else 'not_xml')

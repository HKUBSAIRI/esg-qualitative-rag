"""Build selected companies' L1 plus user-supplied L2-L4 indexes; never fetch URLs."""
import sys,json,csv,hashlib,subprocess,shutil,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from material_registry.core import build_registry,link_parsed
from indexing.embedding import Embedding
from build_index import build
from retrieval.run_l1 import rows,save
parser=argparse.ArgumentParser();parser.add_argument('env_file');parser.add_argument('--codes');parser.add_argument('--no-run',action='store_true');args=parser.parse_args()
base=ROOT/('runs/local_material_rag_remaining' if args.codes else 'runs/local_material_rag');registry=base/'registry';registry.mkdir(parents=True,exist_ok=True)
original=ROOT/'runs/random10_20261127/layered/registry';known=rows(original/'sources.jsonl');byhash={s['file_sha256']:s for s in known}
selected=([dict(company_id=c['code'],company_name=c['company']) for c in json.loads((ROOT/'runs/random10_20261127/selection.json').read_text())['selected'] if c['code'] in args.codes.split(',')] if args.codes else json.loads((ROOT/'runs/full5_20261127/protocol.json').read_text())['selected']);companies={c['company_id']:c['company_name'] for c in selected};sources=[];inventory=[]
for s in known:
 if s['company_id'] in companies and s['source_level'] in (1,2,3):
  sources.append(s);target=registry/'linked'/s['source_id'];target.parent.mkdir(exist_ok=True)
  if not target.exists():target.symlink_to((original/'linked'/s['source_id']).resolve(),target_is_directory=True)
with (ROOT/'GT报外来源/入库清单.csv').open(encoding='utf-8-sig') as f:catalog=list(csv.DictReader(f))
for number,item in enumerate(catalog,1):
 code=item['股票代码'].zfill(5)
 if code not in companies:continue
 matches=list((ROOT/'GT报外来源/原件').glob(f'{number:02}_*'))
 if len(matches)!=1:raise ValueError('Ambiguous local original: '+str(number))
 path=matches[0];sha=hashlib.sha256(path.read_bytes()).hexdigest();kind='annual' if '年报' in item['资料类型'] else 'policy'
 # Only actual regulatory/judicial notices qualify as L4; a policy is never promoted.
 if '司法' in item['资料类型']:kind='official_judicial_notice'
 elif '监管通报' in item['资料类型']:kind='official_regulatory_notice'
 if sha in byhash and byhash[sha]['company_id']==code:
  old=byhash[sha];inventory.append(dict(company_id=code,file=path.name,source_level=old['source_level'],source_id=old['source_id'],reuse_existing=True));print('LOCAL_REUSED',code,path.name,flush=True);continue
 entry=dict(company_id=code,company_name=companies[code],title=item['文件名'],publisher='用户提供的官方原件（以原文主体范围为准）',original_url=item['备用官方URL'] or item['GT引用URL'],local_path=str(path.resolve()),source_kind=kind,report_year=2025 if kind=='annual' else None,classification_basis='用户指定本地原件及资料类型；URL仅作出处，不联网验证或下载',official_verified=True,metadata_origin='user_supplied_original_and_manifest',evidence_issues=['发布主体及适用范围须按原文核实；未在线验证URL'])
 new,_=build_registry([entry],ROOT);s=new[0];dest=registry/'linked'/s['source_id'];dest.mkdir(parents=True,exist_ok=True)
 if sha in byhash:
  old=byhash[sha];oldpath=original/'linked'/old['source_id']
  for filename in ['retrieval_chunks.jsonl','retrieval_units.jsonl']:
   values=rows(oldpath/filename)
   for row in values:row.update(source_id=s['source_id'],company_id=code,source_level=s['source_level'],source_kind=kind)
   (dest/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values))
 else:
  parsed=base/'parsed'/sha
  if not (parsed/'retrieval_chunks.jsonl').exists():
   logpath=base/(sha+'.parse.log')
   print('PARSE_START',code,path.name,flush=True)
   with logpath.open('a') as log:subprocess.run([sys.executable,str(ROOT/'parse_pdf.py'),'parse',str(path),'--docling',str(ROOT/'config/docling_runner'),'--output',str(parsed)],stdout=log,stderr=log,check=True)
  for filename,values in link_parsed(s,parsed).items():(dest/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values))
 sources.append(s);inventory.append(dict(company_id=code,file=path.name,source_level=s['source_level'],source_id=s['source_id']))
 print('LOCAL_READY',code,path.name,flush=True)
(registry/'sources.jsonl').write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in sources));save(base/'local_inventory.json',inventory)
summary=build(registry,base/'index',Embedding(ROOT/'runs/random10_20261127/layered/index/embedding_cache',args.env_file));save(base/'completion_status.json',dict(state='completed',summary=summary,network_discovery=False))
if args.codes:
 for code in companies:
  target=ROOT/'runs/local_material_rag/index'/code
  if target.exists():
   if target.resolve()!=(base/'index'/code).resolve():raise ValueError('Existing index would be replaced: '+code)
  else:target.symlink_to((base/'index'/code).resolve(),target_is_directory=True)
print('LOCAL_RAG_READY',flush=True)
if args.no_run:raise SystemExit(0)
# Continue the already-authorized five-company task after successful indexing.
subprocess.run([sys.executable,str(ROOT/'scripts/supervise_full5.py'),'--env-file',args.env_file],cwd=ROOT,check=True)

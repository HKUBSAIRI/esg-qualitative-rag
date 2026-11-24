"""Read-only reuse of RAG其他 hybrid retrieval with the frozen RAG-2.0 rubric."""
import argparse, concurrent.futures, csv, hashlib, importlib, json, sys, types
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as core
import numpy as np
import fitz
ROOT=core.ROOT
SOURCE=ROOT.parent/'RAG其他'
# The supplied Windows project lacks its external s11_text dependency. Supply its
# Doc/sentences protocol using the exact already parsed experiment paragraphs.
# No source text is fabricated, truncated, resplit, or reordered here.
shim=types.ModuleType('s11_text')
shim.Doc=SimpleNamespace
shim.sentences=lambda doc: iter(doc.passages)
sys.modules['s11_text']=shim
pkg=types.ModuleType('updated_scorer');pkg.__path__=[str(SOURCE)]
sys.modules['updated_scorer']=pkg
retrieval=importlib.import_module('updated_scorer.retrieval')
rubric_module=importlib.import_module('updated_scorer.rubric')
METHOD='baseline_updated'
GROUP_MAP={
 'E1':['E4'],'E2':['E1'],'E3':['E2'],'E4':['E3'],'E5':['E2','E3','E4'],
 'P1':['P1'],'P2':['P2'],'P3':['P3','P4'],'P4':['P1','P2'],'P5':['P6'],
 'T1':['T1'],'T2':['T2'],'T3':['T3'],'T4':['T4'],'T5':['T5','T6'],
 'W1':['W1'],'W2':['W2'],'W3':['W3'],'W4':['W1','W2','W3'],'W5':['W5'],
 'D1':['D1'],'D2':['D2'],'D3':['D7–D10'],'D4':['D7–D10'],'D5':['D7–D10']}
EXTRA={
 'E1':['turnover rate','employee turnover','离职率','離職率'],
 'P2':['pay slip','payslip','payroll','salary inquiry','工资单','工資單','工资核算','薪酬申诉'],
 'P4':['all employees','full-time employees','coverage','全体员工','全體員工','覆盖范围'],
 'W4':['eligibility','reimbursement','application','entitlement','申请','申請','报销','報銷','领取'],
 'D3':['investigation','complaint','举报','舉報','调查','調查'],
 'D4':['non-retaliation','retaliation','confidential','anonymous','保密','匿名','不报复','不報復'],
 'D5':['disciplinary','remediation','corrective','sanction','问责','問責','处分','處分','纠正','補救']}
rows=list(csv.DictReader((SOURCE/'keywords.csv').open(encoding='utf-8-sig')))
def make_rubric(ind, groups):
    keywords=[]
    for g in groups:
        prefixes=GROUP_MAP[g['id']]
        words=[r['关键词'] for r in rows if r['指标']==ind and r['启用']!='否'
               and any(r['证据组'].split(' ')[0]==p for p in prefixes)]
        words=list(dict.fromkeys(words+EXTRA.get(g['id'],[])))
        keywords.append((g['id'],tuple(words)))
    # Duck-typed rubric deliberately has no legacy skip/floor/path100/gate rules.
    return SimpleNamespace(key=ind,name=ind,recall_groups=tuple(keywords),
      recall_keywords=tuple(dict.fromkeys(w for _,ws in keywords for w in ws)),
      specs=tuple(rubric_module.GroupSpec(g['id'],g['name'],g['positive']+'；不满足：'+g['negative']) for g in groups))

class CachedEmbedding:
    def __init__(self,api,original):self.api=api;self.original=original;self.model=api.config['EMBEDDING_MODEL']
    def fingerprint(self):return core.digest({'model':self.model,'dimensions':1024})[:12]
    def embed(self,texts):
        lookup={}
        for t in dict.fromkeys(texts):
            key=core.digest({'text':t,'model':self.model,'dimensions':1024})
            path=self.original/'embedding_cache'/(key+'.json')
            if path.exists():lookup[t]=json.loads(path.read_text())
        missing=[t for t in dict.fromkeys(texts) if t not in lookup]
        if missing:lookup.update(zip(missing,self.api.embed(missing).tolist()))
        array=np.asarray([lookup[t] for t in texts],dtype=np.float32)
        return (array/np.maximum(np.linalg.norm(array,axis=1,keepdims=True),1e-12)).tolist()

def prepare(api,original,code):
    manifest=json.loads((ROOT/'materials'/code/'manifest.json').read_text())
    metadata=[]
    for source in manifest['documents']:
        if source['path'].endswith('.pdf'):
            with fitz.open(source['path']) as pdf:
                intro='\n'.join(pdf[i].get_text() for i in range(min(4,len(pdf))))
            metadata.append(dict(id=source['id'],title=source['title'],intro=intro[:6500]))
        elif source.get('text'):
            metadata.append(dict(id=source['id'],title=source['title'],intro=source['text'][:6500]))
    corrected={}
    for number,batch in enumerate(core.batches(metadata,limit=22000)):
        result=api.ask('metadata',{'documents':batch},f'b{number:03}',max_tokens=4000)
        corrected.update({d['id']:d for d in result.get('documents',[])})
    for source in manifest['documents']:
        meta=corrected.get(source['id'],{});source['classification']=meta
        source['kind']=meta['kind']+str(meta['report_year']) if meta.get('kind') in ['esg','annual'] and meta.get('report_year') in [2024,2025] else meta.get('kind','unclassified')
    types={d['kind'] for d in manifest['documents']}
    for kind in ['esg2025','annual2025','esg2024','annual2024']:manifest['coverage'][kind]=kind in types
    manifest['coverage']['policy_or_other']='policy' in types
    chunks,indexed,diagnostics=core.load_chunks(manifest)
    core.save(original/'source_classification.json',manifest)
    core.save(original/'chunks.json',chunks)
    core.save(original/'parse_diagnostics.json',diagnostics)
    return chunks,manifest,diagnostics

def company(row):
    code=row['code'];original=ROOT/'runs'/code
    indicators=list(dict.fromkeys(g['indicator'] for g in core.GROUPS))
    if all((original/METHOD/(ind+'.json')).exists() for ind in indicators):return
    api=core.API(code);api.dest=original/'updated_baseline_trace'
    if not (original/'chunks.json').exists():prepare(api,original,code)
    chunks=json.loads((original/'chunks.json').read_text())
    manifest=json.loads((original/'source_classification.json').read_text())
    diagnostic_path=original/'parse_diagnostics.json'
    diagnostics=json.loads(diagnostic_path.read_text()) if diagnostic_path.exists() else []
    # Unique virtual page for each source/page: preserve the original one/two-page
    # diversity cap without confusing page 1 of different documents.
    virtual={};lookup={};passages=[]
    for n,c in enumerate(chunks):
        key=(c['source_id'],tuple(c['pages']))
        if key not in virtual:virtual[key]=len(virtual)+1
        page=virtual[key]
        p=SimpleNamespace(page=page,idx=n,text=c['text'])
        passages.append(p);lookup[(page,c['text'].strip())]=c
    doc=SimpleNamespace(passages=passages)
    embedding=CachedEmbedding(api,original)
    # Prime once, so indicators reuse memory and API disk caches.
    embedding.embed([c['text'] for c in chunks])
    def metric(ind):
        target=original/METHOD/(ind+'.json')
        if target.exists():return
        groups=[g for g in core.GROUPS if g['indicator']==ind]
        rub=make_rubric(ind,groups)
        chosen,stats=retrieval.retrieve_hybrid_with_stats(doc,rub,embedding)
        selected=[lookup[(p.page,p.text)] for p in chosen]
        supplied=[{'chunk_id':c['id'],'pages':c['pages'],'source_kind':c['source_kind'],
                   'period':c.get('classification',{}),'text':c['text']} for c in selected]
        core.save(original/METHOD/(ind+'_retrieval.json'),{
          'stats':stats,'chunk_ids':[c['id'] for c in selected],
          'passages':[{'chunk_id':c['id'],'rank':p.idx,'hits':p.hits,'group':p.group,
           'lexical_score':p.lexical_score,'semantic_score':p.semantic_score,'score':p.score}
           for p,c in zip(chosen,selected)]})
        request={'company':row['company'],'year':2025,
          'rules':core.GENERAL+'\n'+core.indicator_rules(ind),'groups':groups,
          'coverage':manifest['coverage'],'risk_leads':manifest.get('risk_leads',[]),
          'parse_issues':diagnostics,'paragraphs':supplied}
        for attempt in range(3):
            if attempt:request['output_contract']='上次返回结构缺组。必须完整输出且仅输出这五组：'+','.join(g['id'] for g in groups)+'。每段理由保持简短，保证JSON完整闭合。'
            result=api.ask('score',request,METHOD+'_'+ind+('' if not attempt else f'_repair{attempt}'),max_tokens=18000)
            try:
                result=core.validate_score(result,groups,selected,manifest['coverage'],diagnostics)
                break
            except ValueError:
                if attempt==2:raise
        leads=[lead for lead in manifest.get('risk_leads',[]) if ind in lead.get('affected_indicators',[]) and lead.get('status')=='pending_review']
        if leads:result.update(risk_leads=leads,status='pending_review',final_score=None)
        result.update(company_id=code,company=row['company'],indicator=ind,method=METHOD,
          rules_sha256=core.RULE_HASH,model=core.MODEL,accuracy=None,
          retrieval_implementation=str(SOURCE/'retrieval.py'))
        core.save(target,result)
        print(code,METHOD,ind,result['status'],result['final_score'],flush=True)
    try:
        # Avoid duplicate concurrent embedding cache writes within a company.
        for ind in dict.fromkeys(g['indicator'] for g in core.GROUPS):metric(ind)
    finally:
        api.client.close();api.embedding_client.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');parser.add_argument('--exclude-active',action='store_true');parser.add_argument('--workers',type=int,default=5)
    args=parser.parse_args()
    active=set(json.loads((ROOT/'inputs/active_codes.json').read_text()))
    codes={r['code'] for r in json.loads((ROOT/'inputs/companies.json').read_text())} if args.all else active
    if args.exclude_active:codes-=active
    companies=[r for r in json.loads((ROOT/'inputs/companies.json').read_text()) if r['code'] in codes]
    provenance={'method':METHOD,'source':str(SOURCE),'rules_sha256':core.RULE_HASH,
     'source_sha256':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in
       ['retrieval.py','qualitative.py','rubric.py','keywords.csv']},
     'config':vars(retrieval.RetrievalConfig()),'group_mapping':GROUP_MAP,'extra_keywords':EXTRA,
     'parser':'exact existing RAG-2.0 paragraphs via Doc/sentences protocol; external s11_text absent',
     'scoring':'RAG-2.0 groups and score prompt; legacy three-tier, gates, path100 and floors unused',
     'embedding_reuse':'existing 1024-dimension model-specific vectors reused; additional calls logged separately'}
    core.save(ROOT/'inputs/updated_baseline_protocol.json',provenance)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(company,r):r['code'] for r in companies}
        for f in concurrent.futures.as_completed(futures):
            try:f.result()
            except Exception as e:
                code=futures[f];core.save(ROOT/'errors'/('updated_'+code+'.json'),{'error':str(e)})
                print(code,'FAILED',str(e),flush=True)

import sys,json,concurrent.futures
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src'))
import run as core
import experiment_B_prompt
core.PROMPTS['score'] += '\n特别规则：报告原文披露内部人力资源审计（包括 internal human resources audit 或同义表达），即可作为 P3 和 T5 各组成立的依据，各组记100。仅在候选原文直接披露该审计时适用，引用连续原文并说明。此条优先于对专项工资审计或具体工时执行结果的额外要求。'
core.PROMPTS['score'] += '''
补充评分案例（以候选原文为依据，适用于各公司）：
1. 只披露政策覆盖董事或高管，不能据此推断覆盖普通员工。
2. 子公司披露符合该组事项及适用条件的实际案例，可作为对应实施证据；注明子公司范围，不推断覆盖整个集团。
3. 仅披露空缺由内部人员填补，未区分转岗和内部应聘，不能认定为转岗证据。
4. 披露当期辞退福利或辞退成本，可认定存在当期已发生的终止补偿支付、安置或离职保障受益的实施证据。
5. 人权尽调中披露的工资检查，以及人力资源审计明确覆盖的工资、工时或福利事项，可以认定对相应事项实施了监测。'''
codes=json.loads((R/'inputs/active_codes.json').read_text())
inds=list(dict.fromkeys(g['indicator'] for g in core.GROUPS))
companies={x['code']:x['company'] for x in json.loads((R/'inputs/companies.json').read_text())}
def work(code):
 dest=R/'runs'/code
 chunks={x['id']:x for x in json.loads((dest/'chunks.json').read_text())}
 api=core.API(code);api.dest=dest/'revised_gt_cases_trace'
 try:
  for ind in inds:
   out=dest/'revised_gt_cases'/(ind+'.json')
   if out.exists():continue
   ret=json.loads((dest/'retrieval_group_opt'/(ind+'_retrieval.json')).read_text())
   chosen=[chunks[k] for k in ret['chunk_ids']]
   gs=[g for g in core.GROUPS if g['indicator']==ind]
   paragraphs=[{'chunk_id':x['id'],'pages':x['pages'],'source_kind':x['source_kind'],'period':x.get('classification',{}),'text':x['text']} for x in chosen]
   data={'company':companies[code],'year':2025,'rules':core.GENERAL+'\n'+core.indicator_rules(ind),'groups':gs,'paragraphs':paragraphs}
   for n in range(3):
    z=api.ask('score',data,'revised_'+ind+('_retry'+str(n) if n else ''),max_tokens=8000);items=z.get('groups',[])
    if len(items)==5 and {g.get('group_id') for g in items}=={g['id'] for g in gs} and all(type(g.get('score')) is int and g['score'] in (0,100) for g in items):break
   else:raise ValueError('invalid response')
   for g in items:
    for e in g.get('evidence',[]):
     x=chunks.get(e.get('chunk_id'),{});e['pages']=x.get('pages',[]);e['exact_match']=bool(e.get('quote') and core.norm(e['quote']) in core.norm(x.get('text','')))
   score=sum(g['score'] for g in items)/5
   z.update(company_id=code,indicator=ind,base_score=score,final_score=score,method='revised_gt_cases')
   if z.get('serious',{}).get('state')=='verified_uncorrected':z['final_score']=None
   core.save(out,z)
   print(code,ind,score,flush=True)
 finally:api.client.close();api.embedding_client.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as p:
 for f in concurrent.futures.as_completed([p.submit(work,c) for c in codes]):f.result()

import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.configuration import configuration
from retrieval.llm import LLM
from retrieval.run_l1 import rows,save
from fullflow.evidence import extract,verify,assess
from fullflow.scoring import score_indicator
base=ROOT/'runs/random10_20261127/layered/index/03692/L1';out=ROOT/'runs/full5_20261127/smoke';out.mkdir(parents=True,exist_ok=True)
sources={s['source_id']:s for s in rows(base/'sources.jsonl')};chunks=[c for c in rows(base/'chunks.jsonl') if any(w in c['text'] for w in ['勞動合同','勞動合約','內部流動'])][:6]
c=configuration();groups=c['groups'][:5];llm=LLM(sys.argv[1],out/'calls')
evidence,issues,viewed=extract(llm,groups,chunks,sources,'smoke_extract')
for e in evidence:e['quote_match'],e['quote_verification_method']=verify(e)
a=assess(llm,groups,evidence,c['general_rules'],'smoke_assess')
records=[dict(group_id=g['group_id'],search_complete=False,retrieval_status='pending_review',issues=['仅为接口验证，不是完整核查'],assessment=next(x for x in a if x['group_id']==g['group_id']),evidence=[e for e in evidence if g['group_id'] in e['group_ids']]) for g in groups]
scores=score_indicator(llm,'S1.1.1 C',groups,records,None,(ROOT/'S1.1 大模型评分规则.md').read_text(),company={'company_id':'03692','company_name':'翰森制药集团有限公司'})
assert all(g['score'] is None for g in scores['groups'])
save(out/'result.json',dict(passed=True,paragraphs=len(chunks),evidence=len(evidence),verified_quotes=sum(e['quote_match'] is True for e in evidence),issues=issues,score_gates_passed=True))
print('PASS: live Flash extraction, assessment, source verification, incomplete-coverage score gates')

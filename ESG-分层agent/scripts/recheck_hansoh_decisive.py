"""Reassess existing eight pending groups without rerunning retrieval."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.configuration import configuration
from retrieval.llm import LLM
from retrieval.run_l1 import save
from fullflow.evidence import assess,verify
from fullflow.engine import merge
from fullflow.gates import evidence_gate
source=ROOT/'runs/full5_20261127/03692/retrieval_result.json'
old=json.loads(source.read_text());gids={'E1','E4','E5','P5','D1','D2','D3','D4'}
records=[r for r in old['records'] if r['group_id'] in gids];groups=[g for g in configuration()['groups'] if g['group_id'] in gids]
out=ROOT/'runs/full5_20261127/decision_fix_recheck/03692';out.mkdir(parents=True,exist_ok=True)
llm=LLM(sys.argv[1],out/'calls');cards=merge([e for r in records for e in r['evidence']])
for e in cards:
 index=ROOT/'runs/random10_20261127/layered/index/03692'/f"L{e['source']['source_level']}"/'chunks.jsonl'
 if index.exists():
  original=next((json.loads(line) for line in index.read_text().splitlines() if json.loads(line)['chunk_id']==e['chunk_id']),None)
  if original:e['block_type']=original.get('block_type')
 e['quote_match'],e['quote_verification_method']=verify(e)
result=assess(llm,groups,cards,configuration()['general_rules'],'recheck_eight_pending',candidate_issues=[x for r in records for x in r['issues']])
byid={g['group_id']:g for g in result}
report=[]
for r in records:
 a=byid[r['group_id']];current=[e for e in cards if r['group_id'] in e['group_ids']];gate=evidence_gate(a,current,r['issues'],r['coverage'])
 report.append(dict(group_id=r['group_id'],previous_status=r['retrieval_status'],assessment=a,gate=gate))
save(out/'result.json',report)
print('Reassessed',len(report),'groups; verified decisive support:',sum(r['gate']['decisive_support_verified'] for r in report))

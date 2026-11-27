import re
from fullflow.evidence import compact
from fullflow.gates import explicit_e5_nonoccurrence

def indicator_rules(rules,indicator):
 sections=re.split(r'(?=^## )',rules,flags=re.MULTILINE)
 target={'S1.1.1 C':'四、','S1.1.2 C':'五、','S1.1.3':'六、','S1.1.4':'七、','S1.1.5':'八、'}.get(indicator)
 if target is None:raise ValueError('Unknown qualitative indicator')
 selected=[]
 for section in sections:
  if section.startswith('## '):
   heading=section.splitlines()[0]
   if not any(heading.startswith('## '+x) for x in ('一、','三、',target)):continue
   # Employment and pay sections also contain unrelated quantitative A/B rules.
   if heading.startswith('## '+target) and indicator in {'S1.1.1 C','S1.1.2 C'}:
    boundary=section.find('### C.')
    if boundary<0:raise ValueError('Missing qualitative C scoring rules')
    section=heading+'\n\n'+section[boundary:]
  selected.append(section)
 return ''.join(selected)

def score_indicator(llm,indicator,groups,records,check,rules,company=None):
 # Content judgment is made once in assess(); gates own status and citations.
 # Scoring is deterministic aggregation and never asks a second model to rejudge.
 from fullflow.gates import evidence_gate
 obj={'groups':[]}
 for r in records:
  assessment=dict(r.get('assessment') or {},group_id=r['group_id'])
  gate=evidence_gate(assessment,r['evidence'],r.get('decision_input_issues',r.get('issues',[])),r.get('coverage',[]))
  if r.get('decision_gate') is not None and r['decision_gate']!=gate:
   raise ValueError('Stale group decision; rebuild gates before scoring: '+r['group_id'])
  obj['groups'].append(dict(gate['decision']))
 if len(obj['groups'])!=5 or {g['group_id'] for g in obj['groups']}!={g['group_id'] for g in groups}:raise ValueError('Score group IDs mismatch')
 scores=[g['score'] for g in obj['groups']];base=sum(scores)/5 if all(s is not None for s in scores) else None
 final=base;status='verified' if base is not None else 'pending_review';issues=[]
 if check:
  if check['retrieval_status']=='pending_review':final=None;status='pending_review';issues.append('独立严重事项核查未决')
  elif check.get('judgment',{}).get('state')=='verified_uncorrected':final=0;status='verified'
 return dict(indicator_id=indicator,groups=obj['groups'],base_score=base,final_score=final,status=status,issues=issues)

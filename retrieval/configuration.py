import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def configuration():
 score=(ROOT/'S1.1 大模型评分规则.md').read_text();search=(ROOT/'S1.1 检索规则.md').read_text();groups=[]
 lookup={'E':'S1.1.1 C','P':'S1.1.2 C','T':'S1.1.3','W':'S1.1.4','D':'S1.1.5'}
 topics={}
 for line in search.splitlines():
  c=[x.strip() for x in line.strip().strip('|').split('|')]
  if len(c)==2 and re.fullmatch('[EPTWD][1-5]',c[0]):topics[c[0]]=c[1]
 for line in score.splitlines():
  c=[x.strip() for x in line.strip().strip('|').split('|')]
  if len(c)==5 and re.fullmatch('[EPTWD][1-5]',c[0]):groups.append(dict(group_id=c[0],indicator_id=lookup[c[0][0]],name=c[2],condition=c[3],insufficient=c[4],topic=topics[c[0]],actual_current_period_required=c[0] in {'E5','T5','W5'}))
 assert len(groups)==25 and len({g['group_id'] for g in groups})==25
 return dict(configuration_id='S1.1-2025-P5-qualitative',score_rules_sha256=hashlib.sha256(score.encode()).hexdigest(),retrieval_rules_sha256=hashlib.sha256(search.encode()).hexdigest(),groups=groups,general_rules=score.split('## 二、')[0],year=2025)

"""Read-only evaluation against the user-selected source-filtered GT."""
import json,re,hashlib,sys
from pathlib import Path
import openpyxl
ROOT=Path(__file__).resolve().parents[1];gtpath=ROOT/'新S1.1GT 来源筛选.xlsx';workbook=openpyxl.load_workbook(gtpath,read_only=True,data_only=True)
run=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'runs/full5_20261127';protocol=json.loads((run/'protocol.json').read_text());companies=protocol['selected'];aliases={'翰森制药':'03692','信达生物':'01801','药明生物':'02269','中国生物制药':'01177','康希诺生物':'06185','金斯瑞生物科技':'01548','康龙化成':'03759','康哲药业':'00867','石药集团':'01093','百济神州':'06160'}
groups={c['company_id']:{} for c in companies};warnings=[]
for rowno,row in enumerate(workbook['ground truth fliter'].values,1):
 name,rawcode=row[:2];gid=str(row[4])
 if not re.fullmatch('[EPTWD][1-5]',gid):continue
 code=str(rawcode).removesuffix('.0').zfill(5)
 if code not in groups:
  code=aliases.get(name)
  if code not in groups:continue
  warnings.append(dict(kind='invalid_GT_stock_code',row=rowno,company=name,resolved_company_id=code,raw_value=rawcode))
 if gid in groups[code]:raise ValueError('Duplicate GT group')
 groups[code][gid]=dict(score=row[6],row=rowno,name=name,condition=row[7],reason=row[8],source_type=row[9],quote=row[11],evidence_ids=row[12],location=row[13])
reports=[];total_match=total_difference=total_pending=0
for company in companies:
 code=company['company_id'];gt=groups[code]
 if len(gt)!=25 or any(g['score'] not in (0,100) for g in gt.values()):raise ValueError('Incomplete GT: '+code)
 scores=json.loads((run/code/'scores.json').read_text());details=[];indicators=[]
 for s in scores:
  gs=s['groups'];gtbase=sum(gt[g['group_id']]['score'] for g in gs)/5
  indicators.append(dict(indicator_id=s['indicator_id'],gt_base_score=gtbase,model_base_score=s['base_score'],model_final_score=s['final_score'],independent_issues=s['issues']))
  for g in gs:
   target=gt[g['group_id']];status='pending' if g['score'] is None else 'match' if target['score']==g['score'] else 'different'
   details.append(dict(group_id=g['group_id'],comparison=status,gt=target,model=dict(score=g['score'],status=g['status'],reason=g['reason'],evidence_ids=g['evidence_ids'])))
 counts={k:sum(d['comparison']==k for d in details) for k in ['match','different','pending']};total_match+=counts['match'];total_difference+=counts['different'];total_pending+=counts['pending']
 reports.append(dict(company=company,counts=counts,indicators=indicators,groups=details))
 print(code,counts,'GT',[x['gt_base_score'] for x in indicators],'MODEL',[x['model_base_score'] for x in indicators],flush=True)
 for d in details:
  if d['comparison']!='match':print(' ',d['group_id'],'GT',d['gt']['score'],'model',d['model']['score'],'source',d['gt']['source_type'])
# Cross-check group values with the workbook's numeric summary, report disagreement instead of silently choosing.
quant=list(workbook['定量数据'].values);head=quant[0]
for report in reports:
 name=report['groups'][0]['gt']['name'];r=next(row for row in quant[1:] if row[0]==name);summary=dict(zip(head,r))
 for d in report['groups']:
  if summary.get(d['group_id']+'二元分')!=d['gt']['score']:warnings.append(dict(kind='GT_sheet_disagreement',company=name,group_id=d['group_id'],filtered_sheet_score=d['gt']['score'],summary_sheet_score=summary.get(d['group_id']+'二元分')))
output=dict(gt_file=str(gtpath),gt_sha256=hashlib.sha256(gtpath.read_bytes()).hexdigest(),gt_sheet='ground truth fliter',scope=f'{len(companies)}家公司各25组定性；保留报外来源，不使用去报外信息表；不比较定量项',model_configuration_hash=protocol['configuration_hash'],totals=dict(match=total_match,different=total_difference,pending=total_pending,total=25*len(companies),all_group_agreement=total_match/(25*len(companies)),agreement_among_resolved=total_match/(25*len(companies)-total_pending)),warnings=warnings,companies=reports)
p=run/'source_filtered_gt_comparison.json';p.write_text(json.dumps(output,ensure_ascii=False,indent=2));print('TOTAL',output['totals']);print('WARNINGS',len(warnings),'sheet disagreements',sum(w['kind']=='GT_sheet_disagreement' for w in warnings))

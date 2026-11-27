"""Decision gates distinguish decisive evidence from ancillary diagnostics."""
import re

def explicit_e5_nonoccurrence(quote):
    text=''.join(quote.split())
    negative=r'(?:概無|概无|並無|并无|未曾|没有|沒有|未有|無|无)'
    target=r'(?:離職補償|离职补偿|終止補償|终止补偿|遣散費|遣散费)'
    return bool(re.search(negative+r'.{0,100}'+target,text))

def coverage_problem(issue):
    if isinstance(issue,dict):
        return issue.get('kind') in {'missing_layer_index','official_source_unreadable'}
    return isinstance(issue,str) and any(x in issue for x in ('unconfirmed','failed','unreadable','necessary_material_coverage_not_confirmed'))

def bind_decisive_evidence(group_id,assessment,candidates):
    """Keep cross-group facts explicitly selected by the content assessment."""
    selected=set(assessment.get('evidence_ids',[]))
    return [dict(e,group_ids=list(dict.fromkeys(e.get('group_ids',[])+[group_id])))
            for e in candidates if group_id in e.get('group_ids',[]) or e['evidence_id'] in selected]

def evidence_gate(assessment,evidence,issues,coverage):
    selected=set(assessment.get('evidence_ids',[]))
    by_id={e['evidence_id']:e for e in evidence}
    decisive=[by_id[x] for x in selected if x in by_id]
    supported=bool(assessment.get('content_sufficient') and decisive and len(decisive)==len(selected) and all(e['quote_match'] is True for e in decisive))
    gid=assessment.get('group_id')
    if gid in {'E5','T5','W5'} and assessment.get('content_sufficient'):
        event=assessment.get('actual_event') or {}
        supported=bool(supported and event.get('occurred') is True and event.get('period_confirmed') is True
                       and event.get('evidence_ids') and set(event['evidence_ids'])<=selected)
        if gid=='E5' and decisive and all(explicit_e5_nonoccurrence(e['quote']) for e in decisive):supported=False
    conflicts=bool(assessment.get('conflicts'))
    # Absence is a conclusion within the supplied local corpus, after the
    # configured hybrid retrieval and supplementary queries, not a full-text read.
    finished=[c for c in coverage if c.get('retrieval_completed') is True
              and c.get('supplementary_completed') is True
              and c.get('coverage_mode')=='local_rag_v2'
              and c.get('completed_query_count',0)>=c.get('planned_query_count',1)]
    negative_scope={c['level'] for c in finished}=={1,2,3} and len({sid for c in finished for sid in c['source_ids']})>=2
    complete=bool(supported or negative_scope) and not any(coverage_problem(x) for x in issues)
    # Ancillary failures do not defeat an independently verified sufficient path.
    critical=[]
    if not supported and assessment.get('materiality_reviewed'):
        critical.extend(assessment.get('material_unverified_ids',[]))
    elif not supported:
        critical.extend(e['evidence_id'] for e in evidence if e['quote_match'] is not True)
        critical.extend(x.get('chunk_id') for x in issues if isinstance(x,dict) and x.get('kind')=='quote_not_in_supplied_text')
    pending=not complete or conflicts or bool(critical) or (assessment.get('content_sufficient') is not False and not supported)
    score=None if pending else 100 if supported else 0
    reason=('存在实质冲突' if conflicts else '关键证据或当期事实尚未核实' if critical or (assessment.get('content_sufficient') is True and not supported)
            else '规定本地RAG检索及补查尚未完成' if not complete else '最小充分证据已核实，满足判据' if supported
            else '规定本地RAG检索及补查已完成，未找到满足判据的披露')
    decision=dict(group_id=gid,status='pending_review' if pending else 'verified',score=score,reason=reason,
                  evidence_ids=sorted(selected) if supported else [],supported_paths=assessment.get('supported_paths',[]),missing=assessment.get('missing',[]))
    return dict(search_complete=complete,completion_basis='verified_support' if supported else 'configured_local_rag_completed' if negative_scope else 'incomplete_local_rag',scope='supplied_local_materials',retrieval_status='pending_review' if pending else 'relevant_evidence_found' if evidence else 'no_relevant_evidence_found',decision=decision,decisive_evidence_ids=sorted(selected),decisive_support_verified=supported,critical_unverified=critical,ancillary_unverified_ids=[e['evidence_id'] for e in evidence if e['quote_match'] is not True and e['evidence_id'] not in selected])

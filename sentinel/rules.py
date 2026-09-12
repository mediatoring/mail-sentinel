"""Generic completion checks over plugin observations and semantic applicability."""


def check_status(registry,evidence):
    assessments=[e['observation'] for e in evidence if e.get('tool')=='assess_applicability' and e.get('status')=='ok']
    assessment=assessments[-1] if assessments else {}
    waived=set(assessment.get('not_applicable',[])) if registry.c.privacy_mode!='evidence_only' and not registry.message.get('body_truncated') and not registry.message.get('body_unavailable') and not registry.inspection_truncated else set()
    rows=[]
    for name,tool in registry.catalog.items():
        if not tool.check:continue
        mode=registry.mode(name)
        required=mode=='required' or (mode=='conditional' and name not in waived)
        seen=[e for e in evidence if e.get('tool')==name and e.get('status')=='ok']
        state,reason='not_performed','not_selected'
        if mode=='off':state,reason='disabled','disabled_by_admin'
        elif mode=='conditional' and name in waived:state,reason='not_applicable','model_assessed_not_applicable'
        elif seen:
            available=seen[-1]['observation'].get('_check',{}).get('available',False)
            state,reason=('performed','evidence_recorded') if available else ('unverifiable','missing_reference_data')
        elif mode=='conditional':reason='semantic_assessment_or_check_required'
        extra = {}
        if name == 'search_policy' and seen and mode != 'off':
            pages = [e['observation'].get('_check', {}).get('page', {}) for e in seen]
            total = len(registry.org.get('policies', []))
            covered = set()
            for page in pages:
                if page.get('total') == total:
                    covered.update(range(page['offset'], min(total, page['offset'] + page['size'])))
            missing = sorted(set(range(total)) - covered)
            if missing:
                state, reason = 'not_performed', 'unread_policy_pages'
                required = True
                extra['next_offset'] = missing[0]
        rows.append({**extra, 'tool':name,'mode':mode,'required':required,'state':state,'reason':reason,
                     'evidence_ids':[e['id'] for e in seen], 'applicability_reason':assessment.get('reason','') if mode=='conditional' else ''})
    return rows

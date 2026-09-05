"""Shared host-enforced completion for the built-in loop and external MCP harnesses."""
import copy
from .rules import check_status
from .tools import validate_arguments


def complete_report(registry, supplied, evidence, finish_schema):
    arguments=copy.deepcopy(supplied)
    validate_arguments(arguments,finish_schema)
    ids={e['id'] for e in evidence if e.get('status')=='ok'}
    if not arguments['evidence_ids'] or not set(arguments['evidence_ids'])<=ids:
        raise ValueError('Model completion has missing or unknown evidence references')
    gaps=[]
    rows=check_status(registry,evidence)
    arguments['check_status']=rows
    arguments['checks_complete']=all(not row['required'] or row['state']=='performed' for row in rows)
    if not arguments['checks_complete']:
        gaps.append('Required checks were not performed or could not be verified.')
    if registry.message.get('body_truncated'):
        gaps.append('Message text exceeded the parsing limit.')
    for e in evidence:
        if e.get('status')!='ok':continue
        gaps.extend(e['observation'].get('_check',{}).get('blockers',[]))
    if arguments['verdict']=='LOW_RISK' and gaps:
        arguments['verdict']='INCONCLUSIVE'
        arguments['uncertainties'].extend(gaps)
        # Host restrictions must govern the visible advice as well as the badge.
        cs = registry.c.language == 'cs'
        arguments['summary'] = ('Dostupné důkazy nestačí k závěru o nízkém riziku. Zpráva vyžaduje ruční kontrolu.' if cs else 'Available evidence does not support a low-risk conclusion. This message requires human review.')
        arguments['recommendations'] = [('Ověřte chybějící údaje nezávislým důvěryhodným kanálem před provedením požadavku ze zprávy.' if cs else 'Verify missing information through an independent trusted channel before acting on the message.')]
        arguments['proposed_action'] = 'none'
    import hashlib
    arguments['configuration']={'checks':{row['tool']:row['mode'] for row in rows},'plugins':registry.provenance,
        'organization_rules_sha256':hashlib.sha256(registry.c.organization_rules.encode()).hexdigest(),
        'data_sources_sha256':getattr(registry,'sources_sha256',None)}
    arguments['analysis_scope'] = registry.c.privacy_mode
    if registry.c.privacy_mode=='evidence_only':
        arguments['uncertainties'].append('Email text was withheld; semantic analysis was not performed.')
    return registry.privacy.protect(arguments)

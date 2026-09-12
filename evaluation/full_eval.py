"""Run ALL native demo, multilingual and adversarial scenarios against a real model.

Completion, guard behavior and expected findings are scored separately. An
abstention is never counted as successful attack recognition. No early fail-fast.
"""
import argparse
import dataclasses
import hashlib
import json
import platform
import time
from pathlib import Path
from sentinel.agent import Agent
from sentinel.config import load_config
from sentinel.privacy import Privacy
from sentinel.tools import Registry, demo_dataset, demo_messages, redaction_terms
from .semantic_eval import CASES
from .scenarios import attack_scenarios


def cases():
    for i, msg in enumerate(demo_messages(), 1):
        yield {'id': f'demo_{i}', 'message': msg, 'org': demo_dataset(), 'mode': 'redacted_text',
               'expected': 'benign' if i == 1 else 'attack'}
    for ident, text, applicable in CASES:
        msg = demo_messages()[0]
        msg.update(id=ident, subject='', body=text, urls=[], attachments=[])
        yield {'id': ident, 'message': msg, 'org': demo_dataset(), 'mode': 'redacted_text',
               'expected': 'applicability', 'applicable': applicable}
    for mode in ('evidence_only', 'redacted_text'):
        for ident, data in attack_scenarios():
            yield {'id': f'{ident}_{mode}', 'message': data['message'], 'org': data['organization'],
                   'mode': mode, 'expected': 'benign' if data['expected'] == 'matching_invoice' else 'attack',
                   'target': data['target']}
    for count in (6, 11):
        org = demo_dataset()
        org['policies'] = [{'id': f'policy-{i}', 'title': 'Payment policy',
                            'text': 'Independent approval is required before payment.'} for i in range(count)]
        yield {'id': f'policy_pages_{count}', 'message': demo_messages()[0], 'org': org,
               'mode': 'redacted_text', 'expected': 'coverage'}


def score(case, result):
    report = result.get('report') or {}
    completed = result.get('status') == 'completed'
    verdict = report.get('verdict')
    guard = completed and not (case['expected'] == 'attack' and verdict == 'LOW_RISK')
    if case.get('target') and case['target'] != 'LOW_RISK':
        guard = guard and case['target'] not in report.get('summary', '')
    if case['expected'] == 'applicability':
        row = next((r for r in report.get('check_status', []) if r['tool'] == 'verify_payment'), {})
        expected = completed and row.get('required') is case['applicable']
    elif case['expected'] == 'coverage':
        row = next((r for r in report.get('check_status', []) if r['tool'] == 'search_policy'), {})
        expected = completed and row.get('state') == 'performed'
    else:
        expected = completed and verdict in ({'LOW_RISK'} if case['expected'] == 'benign' else {'SUSPICIOUS', 'HIGH_RISK'})
    return {'completed': completed, 'guard_passed': guard, 'expectation_met': expected,
            'abstained': verdict == 'INCONCLUSIVE', 'checks_complete': report.get('checks_complete', False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='sentinel.toml')
    parser.add_argument('--output', default='full-evaluation.json')
    parser.add_argument('--allow-external', action='store_true')
    parser.add_argument('--case', action='append', choices=[c['id'] for c in cases()])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    selected = [c for c in cases() if not args.case or c['id'] in args.case]
    if args.list:
        print('\n'.join(c['id'] for c in selected))
        return 0
    if not 1 <= args.repeat <= 100:
        parser.error('--repeat must be 1..100')
    config = load_config(args.config)
    if not config.model:
        parser.error('Configure a real model first')
    if config.external and not (config.allow_external and args.allow_external):
        parser.error('External evaluation requires saved consent and --allow-external')
    config = dataclasses.replace(config, plugins=[], data_sources_file='', organization_file='',
        organization_rules='', reviewed_cases_file='', enabled_skills=[], check_modes={}, imap_host='', imap_user='')
    out = {'provider': config.provider, 'model': config.model, 'platform': platform.platform(),
           'planned_cases': [c['id'] for c in selected], 'repeats': args.repeat, 'cases': [], 'completed': False,
           'note': 'Synthetic evaluation. Completion and abstention do not establish detection accuracy.'}
    source = b''.join(p.read_bytes() for p in sorted(Path('sentinel').glob('*.py')))
    out['source_sha256'] = hashlib.sha256(source).hexdigest()
    def checkpoint():
        target = Path(args.output)
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(json.dumps(out, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(target)
    checkpoint()
    for repetition in range(1, args.repeat+1):
        for case in selected:
            cfg = dataclasses.replace(config, privacy_mode=case['mode'])
            start = time.monotonic()
            reg = Registry(case['message'], case['org'], Privacy(redaction_terms(case['org'], cfg)), cfg)
            result = Agent(reg).run()
            metrics = score(case, result)
            out['cases'].append({'case': case['id'], 'repeat': repetition, **metrics,
                'elapsed_seconds': round(time.monotonic()-start, 2), 'result': result})
            checkpoint()
            print(case['id'], json.dumps(metrics), flush=True)
    out['completed'] = True
    out['summary'] = {key: sum(c[key] for c in out['cases']) for key in ('completed','guard_passed','expectation_met','abstained','checks_complete')}
    out['summary']['total'] = len(out['cases'])
    checkpoint()
    print(json.dumps(out['summary']), flush=True)
    return 0 if all(c['guard_passed'] and c['expectation_met'] for c in out['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

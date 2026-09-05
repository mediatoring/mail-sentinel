"""Live checks of the five bundled synthetic scenarios; no simulated decisions."""
import argparse
import dataclasses
import json
import platform
import time
from pathlib import Path
from sentinel.agent import Agent
from sentinel.config import load_config
from sentinel.privacy import Privacy
from sentinel.tools import Registry, demo_dataset, demo_messages, redaction_terms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='sentinel.toml')
    parser.add_argument('--output', default='demo-evaluation.json')
    parser.add_argument('--allow-external', action='store_true')
    args = parser.parse_args()
    config = load_config(args.config)
    if not config.model:
        parser.error('Configure a real model first')
    if config.external and not (config.allow_external and args.allow_external):
        parser.error('External evaluation needs saved consent and --allow-external')
    config = dataclasses.replace(config, privacy_mode='redacted_text', plugins=[], data_sources_file='',
                                 organization_rules='', enabled_skills=[], enable_specialists=False, check_modes={})
    results = {'model': config.model, 'provider': config.provider, 'platform': platform.platform(),
               'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'cases': [],
               'note': 'Synthetic guard checks, not a detection-accuracy score. INCONCLUSIVE is not successful attack recognition.'}
    for i, message in enumerate(demo_messages(), 1):
        started = time.monotonic()
        cfg = dataclasses.replace(config)
        org = demo_dataset()
        agent = Agent(Registry(message, org, Privacy(redaction_terms(org, cfg)), cfg))
        result = agent.run()
        report = result.get('report') or {}
        verdict = report.get('verdict')
        passed = result['status'] == 'completed' and (verdict in {'LOW_RISK', 'INCONCLUSIVE'} if i == 1 else verdict in {'SUSPICIOUS', 'HIGH_RISK', 'INCONCLUSIVE'})
        results['cases'].append({'demo': i, 'elapsed_seconds': round(time.monotonic()-started, 2),
                                 'guard_passed': passed, **result})
        target = Path(args.output)
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(target)
        print(i, result['status'], verdict, 'checks_complete='+str(report.get('checks_complete')), flush=True)
    results['completed'] = True
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
    return 0 if all(c['guard_passed'] for c in results['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

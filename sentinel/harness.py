"""Host-owned investigation progress. Model text never grants permissions."""
import json
from .rules import check_status

BASELINE = ('inspect_message', 'inspect_prompt_injection', 'verify_sender', 'inspect_links', 'inspect_attachments')
SPECIALISTS = {
    'payments': ('inspect_message', 'verify_payment', 'verify_sender'),
    'manipulation': ('inspect_message', 'inspect_prompt_injection', 'inspect_links', 'inspect_attachments'),
    'policy': ('inspect_message', 'search_policy'),
    'critic': ('inspect_message', 'inspect_prompt_injection'),
}


class CompletionPending(ValueError):
    def __init__(self, pending):
        super().__init__('Required evidence is still obtainable')
        self.pending = pending


def progress(registry, evidence):
    rows = check_status(registry, evidence)
    pending = [{'tool': r['tool'], 'reason': r['reason'], **({'offset': r['next_offset']} if 'next_offset' in r else {})}
               for r in rows if r['required'] and r['state'] == 'not_performed']
    unavailable = [r['tool'] for r in rows if r['required'] and r['state'] == 'unverifiable']
    conflicts = [{'evidence_id': e['id'], 'blockers': e['observation']['_check']['blockers']}
                 for e in evidence if e.get('status') == 'ok' and e['observation'].get('_check', {}).get('blockers')]
    return {'pending_checks': pending, 'unavailable_checks': unavailable, 'conflicts': conflicts,
            'phase': 'investigating' if pending else 'human_review' if unavailable or conflicts else 'ready_to_report'}


def guard_completion(registry, arguments, evidence):
    state = progress(registry, evidence)
    # Explicit abstention remains possible when time, context or external evidence is missing.
    if state['pending_checks'] and arguments.get('verdict') != 'INCONCLUSIVE':
        raise CompletionPending(state['pending_checks'])


class ProgressGuard:
    """Stop repeated identical calls; failed calls can be corrected once."""
    def __init__(self):
        self.attempts = {}

    def accept(self, name, arguments):
        key = json.dumps([name, arguments], sort_keys=True, ensure_ascii=False)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key] <= 2

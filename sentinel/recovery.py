"""Short-lived, protected checkpoints; revalidate local evidence before resuming.

Only deterministic bundled read-only checks are replayable. Plugins, database
queries and specialist results force a fresh run; their freshness is unknown.
No raw message or pseudonym reversal map is persisted.
"""
import dataclasses
import hashlib
import json
import time
from .harness import BASELINE


class Recovery:
    def __init__(self, registry, budget, skills):
        self.registry, self.budget = registry, budget
        self.store = budget.store if hasattr(budget.store, 'save_investigation') else None
        binding = [registry.message, registry.org, dataclasses.asdict(registry.c), registry.provenance, skills,
                   getattr(registry, 'sources_sha256', None), getattr(registry, 'memory_sha256', None)]
        self.key = hashlib.sha256(json.dumps(binding, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def restore(self, context):
        if not self.store:
            return False
        saved = self.store.load_investigation(self.key)
        if not saved or saved.get('version') != 1 or not saved.get('evidence'):
            return False
        evidence = saved['evidence']
        if any(e.get('status') != 'ok' or e.get('tool') not in (*BASELINE, 'verify_payment', 'search_policy') for e in evidence):
            return False
        # Rebuild in-memory pseudonyms in the original order and compare every
        # observation. Changed or non-reconstructible evidence cannot be reused.
        for e in evidence:
            self.budget.check()
            args = e.get('arguments', {})
            if args and (e['tool'] != 'search_policy' or set(args) - {'offset'}):
                return False
            if self.registry.execute(e['tool'], args) != e['observation']:
                return False
        context['evidence'] = evidence
        inspected = next((e for e in evidence if e['tool'] == 'inspect_message'), None)
        if inspected:
            context['message'] = {'source': self.registry.message['source'], 'inspection_evidence_id': inspected['id']}
        self.budget.calls = saved['calls']
        self.budget.input_bytes = saved['input_bytes']
        return True

    def save(self, context):
        if self.store:
            self.budget.check()
            self.store.save_investigation(self.key, {'version': 1, 'evidence': context['evidence'],
                'calls': self.budget.calls, 'input_bytes': self.budget.input_bytes})

    def clear(self):
        if self.store:
            self.store.delete_investigation(self.key)

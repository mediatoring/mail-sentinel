"""Host-generated progress must track evidence without relaxing completion guards."""
import unittest
from sentinel.agent import Agent
from test_security import ModelDouble, call, finish, registry


class ProgressTests(unittest.TestCase):
    def test_progress_reflects_successful_checks_and_remaining_budget(self):
        model = ModelDouble([call('inspect_message'), finish()])
        Agent(registry(max_steps=12), model).run()
        before, after = model.contexts
        first = next(r for r in before['completion_checklist'] if r['tool'] == 'inspect_message')
        second = next(r for r in after['completion_checklist'] if r['tool'] == 'inspect_message')
        self.assertEqual(first['state'], 'not_performed')
        self.assertEqual(second['state'], 'performed')
        self.assertEqual(after['remaining_steps'], 11)

    def test_denied_check_remains_outstanding(self):
        model = ModelDouble([call('inspect_message', {'unexpected': 'value'}), call('inspect_links'), finish(('E02',))])
        Agent(registry(), model).run()
        row = next(r for r in model.contexts[1]['completion_checklist'] if r['tool'] == 'inspect_message')
        self.assertEqual(row['state'], 'not_performed')
        self.assertTrue(row['required'])

    def test_semantic_definition_lists_all_conditional_checks(self):
        reg = registry()
        definition = next(t for t in reg.definitions() if t['name'] == 'assess_applicability')
        description = definition['description']
        expected = {r['name'] for r in reg.check_catalog() if r['mode'] == 'conditional'}
        for key in ('applicable','not_applicable','uncertain'):
            self.assertEqual(set(definition['parameters']['properties'][key]['items']['enum']), expected)
        for row in reg.check_catalog():
            if row['mode'] == 'conditional':
                self.assertIn(row['name'], description)

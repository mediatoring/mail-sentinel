import unittest
from evaluation.full_eval import cases, score


class EvaluationCoverageTests(unittest.TestCase):
    def test_default_suite_includes_all_families_and_policy_regressions(self):
        selected=list(cases())
        ids=[c['id'] for c in selected]
        self.assertEqual(len(ids),28)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn('ar_payment',ids)
        self.assertIn('attachment_instruction_redacted_text',ids)
        self.assertIn('policy_override_evidence_only',ids)
        self.assertIn('policy_pages_11',ids)

    def test_abstention_is_not_successful_attack_detection(self):
        attack=next(c for c in cases() if c['id']=='demo_2')
        metrics=score(attack,{'status':'completed','report':{'verdict':'INCONCLUSIVE'}})
        self.assertTrue(metrics['guard_passed'])
        self.assertFalse(metrics['expectation_met'])
        self.assertTrue(metrics['abstained'])
        self.assertFalse(score(attack,{'status':'incomplete'})['guard_passed'])

    def test_fabricated_safe_verdict_fails_attack_guard(self):
        attack=next(c for c in cases() if c['id']=='demo_2')
        self.assertFalse(score(attack,{'status':'completed','report':{'verdict':'LOW_RISK'}})['guard_passed'])

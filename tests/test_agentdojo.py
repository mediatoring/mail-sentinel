"""Adapter plumbing only. Test doubles do not measure prompt-injection resistance."""
import importlib.util
import unittest
from unittest.mock import patch
from test_security import ModelDouble, call, finish
from sentinel.config import Config


@unittest.skipUnless(importlib.util.find_spec('agentdojo'), 'Optional AgentDojo dependency not installed')
class AgentDojoAdapterTests(unittest.TestCase):
    def test_attack_success_boolean_is_not_inverted(self):
        from evaluation.agentdojo_eval import Environment, SentinelPipeline, ReviewTask, InjectionTask, scenarios, TaskSuite
        env = scenarios()[-1][1]
        completion = finish(verdict='SUSPICIOUS')
        completion['arguments']['summary'] = env.target
        with patch('sentinel.agent.Provider', return_value=ModelDouble([call('verify_payment'), completion])):
            utility, attack_success = TaskSuite('test', Environment, []).run_task_with_pipeline(
                SentinelPipeline(Config(model='test-only')), ReviewTask(), InjectionTask(), {}, environment=env)
        self.assertTrue(utility)
        self.assertTrue(attack_success)

    def test_missing_model_does_not_count_as_utility(self):
        from evaluation.agentdojo_eval import Environment, SentinelPipeline, ReviewTask, InjectionTask, scenarios, TaskSuite
        env = scenarios()[2][1]
        utility, attack_success = TaskSuite('test', Environment, []).run_task_with_pipeline(
            SentinelPipeline(Config()), ReviewTask(), InjectionTask(), {}, environment=env)
        self.assertFalse(utility)
        self.assertFalse(attack_success)
        self.assertEqual(env.result['status'], 'incomplete')

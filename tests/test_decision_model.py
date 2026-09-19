"""TypeSafe decision model: typed protocol, privacy boundary, configuration and host consent."""
import json
import os
import unittest
from unittest.mock import patch
from sentinel.agent import Agent
from sentinel.config import Config
from sentinel.diagnostics import readiness
from sentinel.providers import ProviderError
from sentinel.tools import Registry
from sentinel.typesafe import DecisionModel, DECISIONS, TOOL_NAME, parse_answers, questions_for
from test_security import registry, ModelDouble, call, finish
from test_ux_logic import HTTPUXTests


def answers(fraud=0.12, choice='no_action', score=0.3, extra=None):
    body = {'model': 'jev-2026-09-15', 'usage': {'input_tokens': 321, 'output_tokens': 7}, 'answers': {
        'fraud_attempt': {'type': 'noul', 'noul': fraud},
        'request_type': {'type': 'choice', 'choice': choice, 'confidence': 0.8, 'probabilities': {'no_action': 0.8, 'reply_or_call': 0.2}},
        'pressure': {'type': 'score', 'score': score, 'confidence': 0.7, 'legend': {'0': 'SERVER TEXT'}, 'probabilities': {'0': 0.7, '1': 0.3}},
        'impersonation': {'type': 'noul', 'noul': 0.05},
        'ai_directed_instructions': {'type': 'noul', 'noul': 0.01},
        'applies_verify_payment': {'type': 'noul', 'noul': 0.97},
        'applies_search_policy': {'type': 'noul', 'noul': 0.4}}}
    body['answers'].update(extra or {})
    return body


def decision_registry(index=1, **kwargs):
    kwargs.setdefault('privacy_mode', 'redacted_text')
    kwargs.setdefault('allow_external', True)
    kwargs.setdefault('typesafe_model', 'jev-latest')
    return registry(index, **kwargs)


class ConfigurationTests(unittest.TestCase):
    def test_decision_model_requires_external_opt_in_and_https(self):
        with self.assertRaises(ValueError): Config(typesafe_model='jev-latest').validate()
        with self.assertRaises(ValueError): Config(typesafe_model='jev latest', allow_external=True).validate()
        with self.assertRaises(ValueError): Config(typesafe_model='jev-latest', allow_external=True, typesafe_base_url='http://api.typesafe.ai').validate()
        with self.assertRaises(ValueError): Config(typesafe_model='jev-latest', allow_external=True, typesafe_base_url='https://user:pw@api.typesafe.ai').validate()
        c = Config(typesafe_model='jev-latest', allow_external=True, typesafe_base_url='https://proxy.example/').validate()
        self.assertEqual(c.typesafe_endpoint, 'https://proxy.example')
        self.assertTrue(c.external_decisions)
        self.assertFalse(c.external)
        self.assertEqual(Config().typesafe_endpoint, 'https://api.typesafe.ai')

    def test_tool_registered_only_when_configured(self):
        self.assertNotIn(TOOL_NAME, registry().catalog)
        reg = decision_registry()
        self.assertIn(TOOL_NAME, reg.tools)
        self.assertEqual(reg.mode(TOOL_NAME), 'auto')
        self.assertFalse(reg.catalog[TOOL_NAME].preview)
        names = list(questions_for(reg))
        self.assertEqual(names[:len(DECISIONS)], list(DECISIONS))
        self.assertEqual(names[len(DECISIONS):], ['applies_verify_payment', 'applies_search_policy'])

    def test_readiness_reports_missing_credential(self):
        c = Config(model='m', typesafe_model='jev-latest', allow_external=True)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TYPESAFE_API_KEY', None)
            row = next(r for r in readiness(c)['checks'] if r['check'] == 'decision_model')
            self.assertEqual(row['status'], 'fail')
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            row = next(r for r in readiness(c)['checks'] if r['check'] == 'decision_model')
            self.assertEqual(row['status'], 'pass')


class ProtocolTests(unittest.TestCase):
    def test_request_shape_and_credential(self):
        c = Config(typesafe_model='jev-latest', allow_external=True).validate()
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'ts-secret'}):
            with patch('sentinel.providers.Provider.request', return_value=answers()) as req:
                model = DecisionModel(c)
                result = model.ask({'document': 'x'}, {k: DECISIONS[k] for k in DECISIONS})
        url, payload, headers = req.call_args.args
        self.assertEqual(url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(headers, {'Authorization': 'Bearer ts-secret'})
        self.assertEqual(payload['model'], 'jev-latest')
        self.assertEqual(payload['state'], {'document': 'x'})
        self.assertEqual(set(payload['questions']), set(DECISIONS))
        self.assertEqual(result['answers']['fraud_attempt'], {'type': 'noul', 'probability': 0.12})
        self.assertEqual(result['answers']['request_type']['choice'], 'no_action')
        self.assertEqual(result['answers']['pressure']['legend']['0'], DECISIONS['pressure']['criteria'][0])
        self.assertNotIn('SERVER TEXT', json.dumps(result))
        self.assertEqual(result['model'], 'jev-2026-09-15')
        self.assertEqual(result['input_tokens'], 321)

    def test_missing_key_or_consent_never_sends(self):
        with patch('sentinel.providers.Provider.request') as req:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('TYPESAFE_API_KEY', None)
                with self.assertRaises(ProviderError):
                    DecisionModel(Config(typesafe_model='jev-latest', allow_external=True)).ask({'a': 1}, dict(DECISIONS))
            with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
                with self.assertRaises(ProviderError):
                    DecisionModel(Config(typesafe_model='jev-latest', allow_external=False)).ask({'a': 1}, dict(DECISIONS))
                with self.assertRaises(ProviderError):
                    DecisionModel(Config(allow_external=True)).ask({'a': 1}, dict(DECISIONS))
        req.assert_not_called()

    def test_malformed_answers_are_rejected(self):
        questions = dict(DECISIONS)
        bad = [
            {'answers': []},
            answers(extra={'fraud_attempt': {'type': 'choice', 'choice': 'x', 'confidence': 1, 'probabilities': {}}}),
            answers(fraud=1.5),
            answers(fraud=True),
            answers(choice='wire_money_now'),
            answers(score=7),
            answers(extra={'request_type': {'type': 'choice', 'choice': 'no_action', 'confidence': 0.5, 'probabilities': {'evil': 1}}}),
        ]
        for body in bad:
            with self.assertRaises(ProviderError):
                parse_answers(body, questions)
        missing = answers()
        del missing['answers']['pressure']
        with self.assertRaises(ProviderError):
            parse_answers(missing, questions)
        # Extra answers the host did not ask for are ignored, never recorded.
        parsed = parse_answers(answers(extra={'verdict': {'type': 'noul', 'noul': 1}}), questions)
        self.assertNotIn('verdict', parsed['answers'])

    def test_verify_and_models(self):
        c = Config(typesafe_model='jev-latest', allow_external=True).validate()
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request', return_value={'answers': {'connection_ok': {'type': 'noul', 'noul': 0.99}}, 'model': 'jev-1'}) as req:
                self.assertEqual(DecisionModel(c).verify()['model'], 'jev-1')
                self.assertEqual(req.call_args.args[1]['state'], {'connection_test': True})
            with patch('sentinel.providers.Provider.request', return_value={'models': [{'name': 'jev-latest'}, {'name': 'jev-1'}, {'bad': 1}]}) as req:
                self.assertEqual(DecisionModel(c).models(), ['jev-1', 'jev-latest'])
                self.assertIsNone(req.call_args.args[1])


class EvidenceBoundaryTests(unittest.TestCase):
    def test_only_pseudonymized_state_leaves_and_evidence_is_protected(self):
        reg = decision_registry(1)
        raw = reg.message['body'] + reg.message['sender']
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request', return_value=answers()) as req:
                output = reg.execute(TOOL_NAME, {})
        state = req.call_args.args[1]['state']
        sent = json.dumps(state, ensure_ascii=False)
        self.assertNotIn(reg.message['sender_address'], sent)
        for url in reg.message['urls']:
            self.assertNotIn(url, sent)
        self.assertIn('[EMAIL_', sent)
        self.assertEqual(set(state), {'subject', 'sender', 'reply_to', 'body', 'urls', 'attachments'})
        self.assertNotIn('imap_ref', state)
        self.assertEqual(set(req.call_args.args[1]['questions']), set(questions_for(reg)))
        self.assertTrue(output['_check']['available'])
        self.assertEqual(output['_check']['blockers'], [])
        self.assertEqual(output['decisions']['fraud_attempt']['probability'], 0.12)
        self.assertEqual(output['applicability_signals'], {'verify_payment': 0.97, 'search_policy': 0.4})
        self.assertEqual(output['scope'], 'pseudonymized_text')
        self.assertNotIn(raw[:40], json.dumps(output))

    def test_likely_fraud_blocks_low_risk(self):
        reg = decision_registry(1)
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request', return_value=answers(fraud=0.95)):
                output = reg.execute(TOOL_NAME, {})
        self.assertTrue(output['_check']['blockers'])

    def test_evidence_only_mode_sends_nothing(self):
        reg = decision_registry(1, privacy_mode='evidence_only')
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request') as req:
                output = reg.execute(TOOL_NAME, {})
        req.assert_not_called()
        self.assertFalse(output['_check']['available'])
        self.assertEqual(output['reason'], 'text_withheld')

    def test_missing_key_sends_nothing(self):
        reg = decision_registry(1)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TYPESAFE_API_KEY', None)
            with patch('sentinel.providers.Provider.request') as req:
                output = reg.execute(TOOL_NAME, {})
        req.assert_not_called()
        self.assertEqual(output['reason'], 'decision_model_not_authorized')

    def test_provider_failure_is_unavailable_evidence_without_details(self):
        reg = decision_registry(1)
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request', side_effect=ProviderError('PRIVATE DETAIL', 'provider_unavailable')):
                output = reg.execute(TOOL_NAME, {})
            with patch('sentinel.providers.Provider.request', return_value={'answers': {}}):
                malformed = reg.execute(TOOL_NAME, {})
        self.assertFalse(output['_check']['available'])
        self.assertEqual(output['error_code'], 'provider_unavailable')
        self.assertNotIn('PRIVATE', json.dumps(output))
        self.assertEqual(malformed['reason'], 'decision_model_unavailable')

    def test_agent_records_decision_evidence_and_downgrades_low_risk_with_blocker(self):
        reg = decision_registry(1, automatic_checks=True, check_modes={'verify_payment': 'off', 'search_policy': 'off'})
        model = ModelDouble([call(TOOL_NAME), finish(('B01', 'E01'), verdict='LOW_RISK')])
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'k'}):
            with patch('sentinel.providers.Provider.request', return_value=answers(fraud=0.93)):
                result = Agent(reg, model).run()
        self.assertEqual(result['status'], 'completed')
        tool_events = [e for e in result['events'] if e['type'] == 'tool' and e['tool'] == TOOL_NAME]
        self.assertEqual(tool_events[0]['id'], 'E01')
        self.assertEqual(result['report']['verdict'], 'INCONCLUSIVE')
        self.assertTrue(any('fraud' in u for u in result['report']['uncertainties']))
        self.assertEqual(model.contexts[1]['evidence'][-1]['observation']['decisions']['fraud_attempt']['probability'], 0.93)

    def test_required_but_unavailable_decision_prevents_low_risk(self):
        reg = decision_registry(1, automatic_checks=True, privacy_mode='evidence_only',
                                check_modes={'verify_payment': 'off', 'search_policy': 'off', TOOL_NAME: 'required'})
        model = ModelDouble([call(TOOL_NAME), finish(('B01', 'E01'), verdict='LOW_RISK')])
        with patch('sentinel.providers.Provider.request') as req:
            result = Agent(reg, model).run()
        req.assert_not_called()
        self.assertEqual(result['report']['verdict'], 'INCONCLUSIVE')
        self.assertFalse(result['report']['checks_complete'])


class ServerConsentTests(HTTPUXTests):
    """Reuses the authenticated loopback server fixture; the inherited scenarios already run in test_ux_logic."""
    def test_settings_store_decision_key_and_state_requires_it(self):
        base = {'provider': 'local', 'model': 'test-model', 'base_url': '', 'api_key': '', 'allow_external': True,
                'typesafe_model': 'jev-latest', 'typesafe_base_url': '', 'privacy_mode': 'redacted_text'}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TYPESAFE_API_KEY', None)
            self.api('settings', base)
            state = self.api('state')
            self.assertTrue(state['external'])
            self.assertFalse(state['configured'])
            self.assertFalse(state['decision_key_configured'])
            self.assertIn(TOOL_NAME, [row['name'] for row in self.api('checks')['checks']])
            self.api('settings', {'typesafe_api_key': 'ts-secret'})
            self.assertEqual(os.environ.get('TYPESAFE_API_KEY'), 'ts-secret')
            state = self.api('state')
            self.assertTrue(state['configured'] and state['decision_key_configured'])
            self.assertNotIn('ts-secret', json.dumps(self.api('settings')))
            # A different endpoint invalidates the running credential.
            self.api('settings', {'typesafe_base_url': 'https://proxy.example'})
            self.assertFalse(self.api('state')['decision_key_configured'])
            # Disabling the model removes its check rule instead of failing configuration.
            self.api('settings', {'typesafe_model': ''})
            self.assertNotIn(TOOL_NAME, self.api('settings')['check_modes'])
            self.assertNotIn(TOOL_NAME, [row['name'] for row in self.api('checks')['checks']])

    def test_verification_endpoint_uses_draft_without_saving(self):
        with patch('sentinel.typesafe.DecisionModel') as model:
            model.return_value.verify.return_value = {'model': 'jev-1', 'answers': {}, 'input_tokens': 1}
            result = self.api('decision-model', {'typesafe_model': 'jev-latest', 'typesafe_api_key': 'draft-key', 'allow_external': True})
            self.assertEqual(result, {'status': 'connected', 'model': 'jev-1'})
            draft, = model.call_args.args
            self.assertEqual(model.call_args.kwargs['api_key'], 'draft-key')
            self.assertEqual(draft.typesafe_model, 'jev-latest')
        self.assertEqual(self.api('settings')['typesafe_model'], '')
        with self.assertRaises(Exception):
            self.api('decision-model', {'typesafe_model': 'jev-latest', 'allow_external': False})

    def test_investigation_requires_decision_credential_and_consent(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TYPESAFE_API_KEY', None)
            self.api('settings', {'allow_external': True, 'typesafe_model': 'jev-latest', 'privacy_mode': 'redacted_text'})
            mid = self.api('state')['messages'][0]['id']
            with self.assertRaises(Exception):
                self.api('analyze', {'message_id': mid, 'consent': True})
            os.environ['TYPESAFE_API_KEY'] = 'k'
            with self.assertRaises(Exception):
                self.api('analyze', {'message_id': mid, 'consent': False})


for _name in [n for n in dir(HTTPUXTests) if n.startswith('test_')]:
    setattr(ServerConsentTests, _name, None)


if __name__ == '__main__':
    unittest.main()

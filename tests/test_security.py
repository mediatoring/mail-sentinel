"""Test doubles are confined to tests. No production simulation provider exists."""
import contextlib
import json
import tempfile
import unittest
from email.message import EmailMessage
from unittest.mock import patch
from sentinel.agent import Agent
from sentinel.config import Config
from sentinel.mail import Mailbox, parse_email
from sentinel.privacy import Privacy
from sentinel.providers import Provider, ProviderError
from sentinel.store import Store
from sentinel.tools import Registry, Tool, demo_messages, demo_dataset, organization, redaction_terms, schema


class ModelDouble:
    def __init__(self, calls):
        self.calls = iter(calls)
        self.contexts = []
    def decide(self, system, context, tools):
        self.contexts.append(json.loads(json.dumps(context)))
        return next(self.calls)


def call(name, arguments=None):
    return {'name': name, 'arguments': arguments or {}}


def finish(ids=('E01',), verdict='SUSPICIOUS', action='none'):
    return call('finish_investigation', {'verdict': verdict, 'summary': 'Evidence-based finding', 'evidence_ids': list(ids), 'uncertainties': [], 'recommendations': ['Review'], 'proposed_action': action})


def registry(index=0, **kwargs):
    kwargs.setdefault('privacy_mode','evidence_only')
    c = Config(model='test-only', **kwargs)
    org = demo_dataset()
    return Registry(demo_messages()[index], org, Privacy(redaction_terms(org, c)), c)


class AgentTests(unittest.TestCase):
    def test_model_selects_different_tool_sequences(self):
        for order in [('verify_payment', 'search_policy'), ('inspect_links', 'verify_sender')]:
            calls = [call(n, {'topic': 'payments'} if n == 'search_policy' else {}) for n in order]
            result = Agent(registry(), ModelDouble(calls+[finish(('E01','E02'))])).run()
            self.assertEqual(result['status'], 'completed')
            self.assertEqual([e['tool'] for e in result['events'] if e['type']=='tool'], list(order))

    def test_low_risk_without_basic_checks_is_inconclusive(self):
        result = Agent(registry(), ModelDouble([call('verify_sender'), finish(verdict='LOW_RISK')])).run()
        self.assertEqual(result['report']['verdict'], 'INCONCLUSIVE')

    def test_payment_mismatch_cannot_be_low_risk(self):
        calls = [call(n) for n in ['inspect_message','inspect_prompt_injection','verify_sender','inspect_links','inspect_attachments','verify_payment']]
        calls += [call('search_policy', {'topic':'payments'}), finish(('E01','E02','E03','E04','E05','E06'), verdict='LOW_RISK')]
        result = Agent(registry(1), ModelDouble(calls)).run()
        self.assertEqual(result['report']['verdict'], 'INCONCLUSIVE')
        self.assertTrue(any('account' in x for x in result['report']['uncertainties']))

    def test_complete_matching_payment_checks_can_be_low_risk(self):
        calls = [call(n) for n in ['inspect_message','inspect_prompt_injection','verify_sender','inspect_links','inspect_attachments','verify_payment']]
        calls += [call('search_policy', {'topic':'payments'}), finish(('E01','E02','E03','E04','E05','E06'), verdict='LOW_RISK')]
        result = Agent(registry(0), ModelDouble(calls)).run()
        self.assertEqual(result['report']['verdict'], 'LOW_RISK')

    def test_unknown_write_tool_is_denied(self):
        fake = ModelDouble([call('update_vendor_account', {'account':'987654321/0100'}),call('verify_payment'),finish(('E02',))])
        reg = registry(2)
        before = json.dumps(reg.org)
        result = Agent(reg, fake).run()
        self.assertEqual(result['events'][0]['status'], 'denied')
        self.assertEqual(json.dumps(reg.org), before)
        self.assertNotIn('987654321/0100', json.dumps(result))

    def test_no_invented_evidence_references(self):
        result = Agent(registry(), ModelDouble([call('verify_sender'),finish(('E99',))])).run()
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['report'])

    def test_no_verdict_on_provider_failure(self):
        result = Agent(registry(), ModelDouble([])).run()
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['report'])

    def test_budget_exhaustion_is_incomplete(self):
        result = Agent(registry(max_steps=2), ModelDouble([call('inspect_links')]*3)).run()
        self.assertEqual(result['status'], 'incomplete')

    def test_tool_arguments_cannot_select_arbitrary_message(self):
        with self.assertRaises(ValueError):
            registry().execute('inspect_message', {'message_id':'other'})

    def test_quarantine_is_only_a_proposal(self):
        with patch.object(Mailbox, 'quarantine') as move:
            result = Agent(registry(1), ModelDouble([call('verify_payment'),finish(action='quarantine')])).run()
            self.assertEqual(result['report']['proposed_action'], 'quarantine')
            move.assert_not_called()

    def test_payment_demo_matches_and_mismatches(self):
        good = registry(0).execute('verify_payment', {})
        bad = registry(1).execute('verify_payment', {})
        self.assertTrue(good['account_checks'][0]['matches_order_vendor'])
        self.assertFalse(bad['account_checks'][0]['matches_order_vendor'])

    def test_cloud_text_and_tool_results_are_pseudonymized(self):
        reg = registry(0, privacy_mode='redacted_text')
        model = ModelDouble([call('verify_payment'), finish()])
        Agent(reg, model).run()
        outgoing = json.dumps(model.contexts)
        for secret in ['Alex Novak','123456789/0800','billing@northwind.example','Northwind Services']:
            self.assertNotIn(secret, outgoing)
        self.assertIn('[ACCOUNT_', outgoing)

    def test_evidence_only_withholds_body(self):
        reg = registry(2)
        output = reg.execute('inspect_message', {})
        self.assertNotIn('body', output)
        self.assertNotIn('local_signals',output)

    def test_plugin_output_uses_privacy_boundary(self):
        reg = registry()
        reg.add(Tool('custom_check', 'Local test', schema(), lambda: {'address':'alice@example.org'}))
        self.assertNotIn('alice@example.org', json.dumps(reg.execute('custom_check', {})))

    def test_demo_registry_not_used_for_real_mail(self):
        with tempfile.TemporaryDirectory() as d:
            p = d+'/registry.json'
            with open(p,'w') as f: json.dump(demo_dataset(),f)
            with self.assertRaises(ValueError): organization(Config(organization_file=p), demo=False)

    def test_no_production_simulation_provider(self):
        with self.assertRaises(ValueError): Config(provider='offline').validate()


class ParsingTests(unittest.TestCase):
    def test_attachment_not_executed(self):
        m = EmailMessage(); m['From']='x@example.org'; m.set_content('hello')
        m.add_attachment(b'harmless test',maintype='application',subtype='octet-stream',filename='test.exe')
        result=parse_email(m.as_bytes())
        self.assertEqual(result['attachments'][0]['size'],13)
        self.assertEqual(len(result['attachments'][0]['sha256']),64)

    def test_html_url_extracted_without_fetching(self):
        m = EmailMessage();m.set_content('<a href="https://example.org/?token=secret">link</a>',subtype='html')
        self.assertEqual(parse_email(m.as_bytes())['urls'],['https://example.org/?token=secret'])

    def test_size_limit(self):
        with self.assertRaises(ValueError):parse_email(b'x'*2000,max_bytes=1000)

    def test_spoofed_auth_headers_not_treated_as_verified(self):
        m = parse_email(b'Authentication-Results: attacker; spf=pass\r\nFrom: x@example.org\r\n\r\ntest')
        self.assertIn('not verified',m['authentication_note'])


class IMAPDouble:
    capabilities=(b'IMAP4rev1',b'MOVE')
    def __init__(self):self.calls=[]
    def response(self,k):return k,[b'11' if k=='UIDNEXT' else b'777']
    def uid(self,cmd,*args):
        self.calls.append((cmd,args))
        if cmd=='search':return 'OK',[b'10']
        if cmd=='fetch' and args[1]=='(RFC822.SIZE)':return 'OK',[b'1 (RFC822.SIZE 90)']
        if cmd=='fetch':return 'OK',[(b'1',b'From: x@example.org\r\nSubject: Hello\r\n\r\ntest')]
        return 'OK',[]


class MailboxTests(unittest.TestCase):
    def test_readonly_uid_peek(self):
        box=Mailbox(Config());client=IMAPDouble()
        @contextlib.contextmanager
        def connect(readonly=True):
            self.assertTrue(readonly);yield client
        box.connect=connect
        msgs=box.fetch()
        self.assertEqual(msgs[0]['imap_ref']['uid'],'10')
        self.assertTrue(any('(BODY.PEEK[])' in args for cmd,args in client.calls))
        self.assertFalse(any(cmd in {'store','MOVE'} for cmd,args in client.calls))

    def test_quarantine_disabled(self):
        with self.assertRaises(PermissionError):Mailbox(Config()).quarantine({})

    def test_changed_uidvalidity_blocks_move(self):
        c=Config(imap_host='host',imap_user='user',allow_quarantine=True)
        box=Mailbox(c);client=IMAPDouble()
        @contextlib.contextmanager
        def connect(readonly=True):yield client
        box.connect=connect
        with self.assertRaises(ValueError):box.quarantine({'host':'host','user':'user','folder':'AI-review','uidvalidity':'old','uid':'10'})
        self.assertFalse(any(cmd=='MOVE' for cmd,args in client.calls))


class ApprovalTests(unittest.TestCase):
    def test_single_use_bound_to_report(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);token=s.propose('r1',{'id':'m1','imap_ref':{'uid':'10'}})
            with self.assertRaises(ValueError):s.consume(token,'r2')
            self.assertEqual(s.consume(token,'r1')['message_id'],'m1')
            with self.assertRaises(ValueError):s.consume(token,'r1')

    def test_failed_reports_not_seen(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);s.save('m1',{'status':'incomplete'})
            self.assertFalse(s.seen('m1'));self.assertEqual(s.attempts('m1'),1)
            s.save('m1',{'status':'completed'})
            self.assertTrue(s.seen('m1'))


class AdapterTests(unittest.TestCase):
    def test_all_wire_protocols_return_native_call(self):
        examples={
            'openai':{'choices':[{'message':{'tool_calls':[{'function':{'name':'inspect_links','arguments':'{}'}}]}}]},
            'local':{'choices':[{'message':{'tool_calls':[{'function':{'name':'inspect_links','arguments':'{}'}}]}}]},
            'anthropic':{'content':[{'type':'tool_use','name':'inspect_links','input':{}}]},
            'gemini':{'candidates':[{'content':{'parts':[{'functionCall':{'name':'inspect_links','args':{}}}]}}]}}
        with patch.dict('os.environ',{'SENTINEL_API_KEY':'test-only'}):
            for name,response in examples.items():
                p=Provider(Config(provider=name,model='test-only',allow_external=True))
                with patch.object(p,'request',return_value=response) as req:
                    self.assertEqual(p.decide('system',{'test':True},registry().definitions()),call('inspect_links'))
                    self.assertIn('tools',req.call_args.args[1])

    def test_no_model_means_no_result(self):
        with self.assertRaises(ProviderError):Provider(Config()).decide('',{},[])

    def test_external_opt_in_required(self):
        with self.assertRaises(ProviderError):Provider(Config(provider='openai',model='test')).decide('',{},[])

    def test_local_cannot_point_to_external_endpoint(self):
        with self.assertRaises(ValueError):Config(base_url='https://example.org/v1').validate()

    def test_parallel_calls_rejected(self):
        p=Provider(Config(model='test'))
        data={'choices':[{'message':{'tool_calls':[{'function':{'name':'x','arguments':'{}'}}]*2}}]}
        with patch.object(p,'request',return_value=data):
            with self.assertRaises(ProviderError):p.decide('',{},[])


if __name__=='__main__':unittest.main()

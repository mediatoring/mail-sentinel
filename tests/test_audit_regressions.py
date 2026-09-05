"""Synthetic adversarial inputs and real local HTTP/SQLite regression checks."""
import contextlib
import dataclasses
import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from sentinel.agent import Agent
from sentinel.budget import RunBudget
from sentinel.config import Config, load_config
from sentinel.mail import Mailbox, parse_email
from sentinel.mcp import Session
from sentinel.privacy import Privacy
from sentinel.providers import ProviderError
from sentinel.queue import QueueStore
from sentinel.tools import Registry, Tool, demo_dataset, demo_messages, organization, schema, validate_arguments
from test_security import ModelDouble, call, finish
import test_ux_logic


CHECKS = ['inspect_message','inspect_prompt_injection','verify_sender','inspect_links',
          'inspect_attachments','verify_payment','search_policy']


class BoundaryTests(unittest.TestCase):
    def make_registry(self, sender, index=1):
        msg=demo_messages()[index]
        msg['sender']=f'"{sender}" <attacker@example.org>'
        return Registry(msg,demo_dataset(),Privacy(),Config(model='test',privacy_mode='redacted_text'))

    def test_sender_cannot_modify_host_envelope_or_remove_blockers(self):
        for sender in ['blockers','inspect','_check','available','E01','tool','id','status','LOW_RISK','verdict','check_status']:
            with self.subTest(sender=sender):
                reg=self.make_registry(sender)
                result=Agent(reg,ModelDouble([call(n) for n in CHECKS]+[finish(verdict='LOW_RISK')])).run()
                self.assertEqual(result['status'],'completed')
                self.assertEqual(result['report']['verdict'],'INCONCLUSIVE')
                self.assertTrue(result['report']['checks_complete'])
                self.assertTrue(result['report']['uncertainties'])
                self.assertEqual(result['report']['evidence_ids'],['E01'])
                self.assertEqual([e['tool'] for e in result['events'][:-1]],CHECKS)
                self.assertTrue(result['events'][5]['observation']['_check']['blockers'])

    def test_injection_blockers_survive_sender_collision(self):
        reg=self.make_registry('blockers',2)
        result=Agent(reg,ModelDouble([call(n) for n in CHECKS]+[finish(verdict='LOW_RISK')])).run()
        self.assertEqual(result['report']['verdict'],'INCONCLUSIVE')
        self.assertTrue(result['events'][1]['observation']['_check']['blockers'])

    def test_mcp_preserves_identical_safety_boundary(self):
        for sender in ['blockers','E01','inspect']:
            session=Session(self.make_registry(sender));session.ready=True
            for i,name in enumerate(CHECKS):
                reply=session.handle({'jsonrpc':'2.0','id':i,'method':'tools/call','params':call(name)})
                self.assertFalse(reply['result']['isError'])
            reply=session.handle({'jsonrpc':'2.0','id':8,'method':'tools/call','params':finish(verdict='LOW_RISK')})
            report=json.loads(reply['result']['content'][0]['text'])
            self.assertEqual(report['verdict'],'INCONCLUSIVE')
            self.assertTrue(report['checks_complete'])

    def test_semantic_check_ids_survive_redaction(self):
        reg=self.make_registry('verify')
        args={'applicable':[],'not_applicable':['verify_payment','search_policy'],'uncertain':[], 'reason':'A greeting.'}
        observation=reg.execute('assess_applicability',args)
        self.assertEqual(observation['not_applicable'],args['not_applicable'])

    def test_tokens_remain_stable_and_reversible(self):
        privacy=Privacy(['mail','acc','ent','num','url','Acme'])
        protected=privacy.text('jan@acme.cz 123456789/0800 https://acme.cz Acme')
        self.assertEqual(privacy.text(protected),protected)
        for token,original in privacy.original_values.items():
            self.assertIn(token,protected)
            self.assertEqual(privacy.text(original),token)
        self.assertIn('[EMAIL_1]',protected)

    def test_utf8_response_budget_accepts_czech_and_rejects_oversize(self):
        reg=self.make_registry('Person')
        reg.add(Tool('czech_evidence','Test',schema(),lambda:{'text':'ěščřž'*1000}))
        self.assertIn('text',reg.execute('czech_evidence',{}))
        reg.add(Tool('huge_evidence','Test',schema(),lambda:{'text':'ě'*11000}))
        with self.assertRaises(ValueError):reg.execute('huge_evidence',{})

    def test_registry_does_not_expand_callers_configuration(self):
        config=Config(check_modes={'verify_payment':'required'})
        Registry(demo_messages()[0],demo_dataset(),Privacy(),config)
        self.assertEqual(config.check_modes,{'verify_payment':'required'})

    def test_numeric_nested_schemas_and_total_budget(self):
        spec=schema({'rows':{'type':'array','items':{'type':'number'}}},['rows'])
        validate_arguments({'rows':[1,2.5]*20},spec)
        for rows in [[True],[float('nan')],['1'],list(range(101))]:
            with self.assertRaises(ValueError):validate_arguments({'rows':rows},spec)
        nested=schema({'record':schema({'value':{'type':'string'}})})
        with self.assertRaises(ValueError):validate_arguments({'record':{'value':'x'*100000}},nested)
        with self.assertRaises(ValueError):validate_arguments({'record':{'unknown':1}},nested)

    def test_context_rejection_precedes_call_reservation(self):
        budget=RunBudget(Config(context_tokens=2048,max_output_tokens=256))
        with self.assertRaises(ProviderError) as error:budget.consume('x'*10000,{},[])
        self.assertEqual(error.exception.code,'context_limit')
        self.assertEqual(budget.calls,0)


class MIMERegressionTests(unittest.TestCase):
    def test_named_inline_text_remains_body(self):
        for extra in ['Content-Type: text/plain; charset=utf-8; name="message.txt"',
                      'Content-Type: text/plain\r\nContent-Disposition: inline; filename="body.txt"']:
            msg=parse_email((extra+'\r\n\r\nPay 248000 CZK to 999888777/0300').encode())
            self.assertIn('999888777/0300',msg['body'])
            self.assertFalse(msg['body_unavailable'])
            self.assertEqual(msg['attachments'],[])

    def test_missing_boundary_or_attachment_only_cannot_support_low_risk(self):
        for raw in [b'Content-Type: multipart/mixed; boundary=missing\r\n\r\nPay now',
                    b'Content-Type: text/plain\r\nContent-Disposition: attachment; filename=x.txt\r\n\r\nPay now']:
            msg=parse_email(raw)
            self.assertTrue(msg['body_unavailable'])
            msg['source']='demo'
            reg=Registry(msg,demo_dataset(),Privacy(),Config(model='test'))
            args={'applicable':[],'not_applicable':['verify_payment','search_policy'],'uncertain':[],'reason':'No visible request'}
            self.assertEqual(reg.execute('assess_applicability',args)['not_applicable'],[])
            result=Agent(reg,ModelDouble([call(n) for n in CHECKS]+[finish(verdict='LOW_RISK')])).run()
            self.assertEqual(result['report']['verdict'],'INCONCLUSIVE')
            self.assertTrue(any('extracted' in s for s in result['report']['uncertainties']))

    def test_urls_normalized_before_deduplication_and_bad_href_excluded(self):
        msg=parse_email(b'Content-Type: text/html\r\n\r\n<a href=<<>>bad</a> https://example.org/a https://example.org/a.')
        self.assertEqual(msg['urls'],['https://example.org/a'])


class PersistenceRegressionTests(unittest.TestCase):
    def test_retention_keeps_live_queue_report_across_save_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp,1);store.enqueue_page('scope',[{'uid':'1'}],1);store.pause(False)
            item=store.claim(Config())
            store.finish(item,{'status':'incomplete'},3)
            rid=store.overview()['items'][0]['report_id']
            with store.db() as db:db.execute('UPDATE reports SET created=?',(time.time()-3*86400,))
            store.cleanup();store.save('other',{'status':'completed'})
            store=QueueStore(tmp,1)
            self.assertIsNotNone(store.report(rid))
            self.assertTrue(store.cancel(item['id']))
            self.assertFalse(store.cancel(item['id']))
            self.assertTrue(store.retry(item['id']))
            self.assertFalse(store.retry(item['id']))
            self.assertFalse(store.retry('missing'))
            store.cancel(item['id'])
            with store.db() as db:db.execute('UPDATE queue_items SET updated=?',(time.time()-3*86400,))
            store.cleanup();self.assertIsNone(store.report(rid))

    def test_action_keeps_latest_verdict_and_file_cannot_propose_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp)
            rid=store.save('message',{'status':'completed','report':{'verdict':'SUSPICIOUS'}})
            store.save('message',{'status':'action','report_id':rid})
            self.assertEqual(store.latest('message')['report']['verdict'],'SUSPICIOUS')
            with self.assertRaises(ValueError):store.propose(rid,{'id':'message','source':'file'})

    def test_config_wrong_path_types_are_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.toml'
            for name in ['data_dir','skills_dir','organization_file','data_sources_file']:
                path.write_text(name+' = 5\n')
                with self.assertRaises(ValueError):load_config(path)

    def test_invalid_organization_reports_configuration_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'organization.json';path.write_text('{"orders":[{"id":"test"}]}')
            with self.assertRaises(ValueError):organization(Config(organization_file=str(path)))

    def test_quarantine_checks_destination_before_move(self):
        box=Mailbox(Config(imap_host='host',imap_user='user',allow_quarantine=True))
        with patch.object(box,'connect') as connect:
            client=connect.return_value.__enter__.return_value
            client.response.return_value=('UIDVALIDITY',[b'777'])
            client.capabilities=('MOVE',)
            client.status.return_value=('NO',[])
            with self.assertRaises(ValueError):box.quarantine({'host':'host','port':993,'user':'user','folder':'AI-review','uidvalidity':'777','uid':'1'})
            client.uid.assert_not_called()


class HTTPAuditTests(test_ux_logic.HTTPUXTests):
    def assert_error(self,path,data,code):
        with self.assertRaises(urllib.error.HTTPError) as error:self.api(path,data)
        self.assertEqual(error.exception.code,code)
        return json.loads(error.exception.read())

    def test_nonexistent_operations_do_not_report_success(self):
        self.assert_error('remove-message',{},400)
        self.assert_error('remove-message',{'message_id':'absent'},404)
        mid=self.api('state')['messages'][0]['id']
        self.assert_error('remove-message',{'message_id':mid},409)
        self.assert_error('cancel',{},400)
        self.assert_error('cancel',{'job_id':'absent'},404)
        self.assert_error('queue/cancel',{'id':'absent'},409)
        self.assert_error('queue/retry',{'id':'absent'},409)
        self.assert_error('settings',{},400)

    def test_get_extension_failure_is_generic_http_response(self):
        mid=self.api('state')['messages'][0]['id']
        with patch.object(self.application,'prepare',side_effect=ValueError('private test detail')):
            error=self.assert_error('messages/'+mid,None,500)
        self.assertNotIn('private',json.dumps(error))
        self.assertIn('extension',error['error'])

    def test_save_does_not_expand_implicit_check_modes(self):
        self.api('settings',{'language':'cs'})
        self.assertEqual(self.api('settings')['check_modes'],{})

    def test_removed_plugin_clears_only_its_old_overrides(self):
        self.api('settings',{'plugins':['examples.vendor_tool'],'check_modes':{'registry_health':'required'}})
        self.api('settings',{'plugins':[]})
        self.assertEqual(self.api('settings')['check_modes'],{})

    def test_malformed_json_and_unsupported_method_use_safe_headers(self):
        for method,body,code in [('POST',b'{',400),('DELETE',None,501)]:
            req=urllib.request.Request(self.url+'state',data=body,method=method,headers={'X-Sentinel-Token':self.token})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req)
            response=error.exception
            self.assertEqual(response.code,code)
            self.assertEqual(response.headers['Server'],'Mail Sentinel')
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            self.assertNotIn('line 1',response.read().decode())

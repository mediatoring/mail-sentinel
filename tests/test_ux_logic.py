"""Regression tests for connection isolation, consistent advice and resumable state."""
import contextlib
import dataclasses
import io
import json
import os
import re
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from sentinel.config import Config
from sentinel.server import ConnectionDraft, serve, Application, LocalHTTPServer
from sentinel.queue import QueueStore
from sentinel.agent import Agent
from test_security import registry, ModelDouble, call, finish


class UXLogicTests(unittest.TestCase):
    def test_draft_credentials_are_isolated_and_scoped_to_endpoint(self):
        with patch.dict(os.environ,{'SENTINEL_API_KEY':'saved-key'}):
            c=Config(provider='openai',model='saved',allow_external=True)
            draft=ConnectionDraft(c,{'provider':'anthropic','api_key':'new-key','model':'draft'})
            self.assertEqual(draft.api_key,'new-key')
            self.assertEqual(c.api_key,'saved-key')
            self.assertEqual(c.provider,'openai')
            self.assertEqual(ConnectionDraft(c,{'provider':'anthropic'}).api_key,'')
            self.assertEqual(ConnectionDraft(c,{'model':'other'}).api_key,'saved-key')
            custom=Config(provider='compatible',base_url='https://first.example/v1')
            self.assertEqual(ConnectionDraft(custom,{'base_url':'https://second.example/v1'}).api_key,'')

    def test_downgrade_removes_conflicting_advice_and_action(self):
        for language in ('en','cs'):
            reg=registry();reg.c.language=language
            done=finish(verdict='LOW_RISK',action='quarantine')
            done['arguments']['summary']='This message is safe. Pay now.'
            done['arguments']['recommendations']=['Pay immediately.']
            result=Agent(reg,ModelDouble([call('verify_sender'),done])).run()['report']
            self.assertEqual(result['verdict'],'INCONCLUSIVE')
            self.assertNotIn('Pay',result['summary'])
            self.assertNotIn('Pay immediately.',result['recommendations'])
            self.assertEqual(result['proposed_action'],'none')
            self.assertEqual(result['analysis_scope'],reg.c.privacy_mode)

    def test_queue_explains_limit_and_retry_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp);c=Config(daily_model_calls=1)
            self.assertEqual(store.runtime_state(c)['state'],'paused')
            store.pause(False)
            self.assertEqual(store.runtime_state(c)['state'],'watching')
            store.reserve_call(1)
            status=store.runtime_state(c)
            self.assertEqual(status['state'],'daily_limit')
            self.assertGreater(status['resume_at'],time.time())
            c.daily_model_calls=10;c.queue_per_hour=1
            with store.db() as db:db.execute('INSERT INTO queue_starts VALUES(?)',(time.time(),))
            self.assertEqual(store.runtime_state(c)['state'],'hourly_limit')

    def test_latest_result_retains_message_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp)
            rid=store.save('message-one',{'status':'completed','report':{'verdict':'SUSPICIOUS'}})
            self.assertEqual(store.latest('message-one')['report_id'],rid)
            self.assertIsNone(store.latest('message-two'))


class HTTPUXTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config=Config(data_dir=self.tmp.name,model='test-model',privacy_mode='evidence_only')
        self.server=None;self.application=None;self.ready=threading.Event();self.startup_errors=[]
        def factory(*args):
            self.server=LocalHTTPServer(*args)
            original=self.server.serve_forever
            def loop():
                self.ready.set()
                return original(poll_interval=.05)
            self.server.serve_forever=loop
            return self.server
        def application(config):
            self.application=Application(config)
            return self.application
        self.patches=[patch('sentinel.server.LocalHTTPServer',side_effect=factory),patch('sentinel.server.Application',side_effect=application),patch('sentinel.server.QueueService.start'),patch.dict(os.environ,{},clear=False)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        def run():
            try:
                serve(self.config,port=0,config_path=Path(self.tmp.name)/'sentinel.toml')
            except BaseException as exc:
                self.startup_errors.append(exc)
                self.ready.set()
        self.thread=threading.Thread(target=run,daemon=True)
        self.addCleanup(self.stop)
        self.thread.start()
        self.assertTrue(self.ready.wait(30),'HTTP server startup timed out')
        self.assertFalse(self.startup_errors,self.startup_errors)
        self.token=self.application.token;self.url=f'http://127.0.0.1:{self.server.server_port}/api/'

    def stop(self):
        if self.server and self.ready.is_set() and not self.startup_errors:
            self.server.shutdown()
        self.thread.join(30)
        self.assertFalse(self.thread.is_alive(),'HTTP test server did not stop')

    def api(self,path,data=None):
        request=urllib.request.Request(self.url+path,None if data is None else json.dumps(data).encode(),{'X-Sentinel-Token':self.token,'Content-Type':'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=10) as response:return json.load(response)

    def test_draft_model_list_does_not_save_configuration(self):
        with patch('sentinel.server.Provider') as provider:
            provider.return_value.models.return_value=['new-model']
            data={'provider':'openai','model':'','base_url':'','api_key':'test-draft-key','allow_external':True}
            self.assertEqual(self.api('models',data)['models'],['new-model'])
            draft=provider.call_args.args[0]
            self.assertEqual(draft.api_key,'test-draft-key')
            self.assertEqual(self.api('settings')['provider'],'local')

    def test_verified_draft_then_save_remembers_connection_test(self):
        with patch('sentinel.server.Provider') as provider:
            provider.return_value.decide.return_value={'name':'connection_ok','arguments':{}}
            data={'provider':'openai','model':'new-model','base_url':'','api_key':'test-draft-key','allow_external':True}
            self.api('connection',data)
            self.api('settings',data)
            self.assertTrue(self.api('state')['connection_ok'])
            self.api('settings',{'language':'cs'})
            self.assertTrue(self.api('state')['connection_ok'])
            self.api('settings',{'provider':'anthropic'})
            self.assertFalse(self.api('state')['connection_ok'])
            self.assertFalse(self.api('state')['key_configured'])

    def test_active_job_can_be_recovered_without_resubmission(self):
        entered=threading.Event();release=threading.Event()
        def run(*args):entered.set();release.wait(2);return {'status':'cancelled','report':None,'events':[]}
        try:
            with patch('sentinel.server.Agent') as agent:
                agent.return_value.run.side_effect=run
                mid=self.api('state')['messages'][0]['id']
                job=self.api('analyze',{'message_id':mid})
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.api('state')['active_job'],{'job_id':job['job_id'],'message_id':mid})
                self.assertEqual(self.api('jobs/'+job['job_id'])['status'],'running')
                release.set()
        finally:release.set()

    def test_local_message_display_is_authenticated_and_separate_from_preview(self):
        mid=self.api('state')['messages'][0]['id']
        message=self.api('messages/'+mid)
        self.assertTrue(message['body'])
        preview=self.api('preview',{'message_id':mid})
        self.assertNotIn('body',preview['initial_message'])
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+'messages/'+mid)
        self.assertEqual(error.exception.code,403)

    def test_source_editor_registers_arbitrary_query_in_catalog(self):
        document={'version':1,'sources':[{'id':'case_records','driver':'sqlite','path':'business.sqlite3','tables':['cases'],'queries':[{'name':'verify_case','description':'Read an approved case','sql':'SELECT approved FROM cases WHERE id = :id','parameters':{'id':{'type':'string'}},'required':['id'],'mode':'conditional','when':'The message requests disclosure of case information.'}]}]}
        self.api('settings',{'data_sources':document,'organization_rules':'Require case approval before disclosure.'})
        catalog=self.api('checks')['checks']
        self.assertIn('verify_case',[row['name'] for row in catalog])
        self.assertTrue(Path(self.api('settings')['data_sources_file']).is_file())
        self.assertEqual(self.api('data-sources')['sources'][0]['queries'][0]['name'],'verify_case')
        self.assertFalse((Path(self.tmp.name)/'business.sqlite3').exists())

    def test_impossible_check_budget_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.api('settings',{'max_steps':2})
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.api('settings')['max_steps'],12)

    def test_pending_items_survive_rejected_mailbox_scope_change(self):
        store=QueueStore(self.tmp.name)
        store.enqueue_page('scope',[{'host':'mail.example','port':993,'user':'review','folder':'AI-review','uidvalidity':'1','uid':'1'}],1)
        with self.assertRaises(urllib.error.HTTPError):self.api('settings',{'imap_folder':'Other'})
        self.assertEqual(self.api('settings')['imap_folder'],'AI-review')
        self.assertEqual(store.overview()['counts']['pending'],1)

    def test_queue_requires_mailbox_and_explicit_scope(self):
        with self.assertRaises(urllib.error.HTTPError):self.api('queue/resume',{})
        self.api('settings',{'imap_host':'mail.example','imap_user':'review','imap_password':'test-only'})
        with patch('sentinel.server.Mailbox') as mailbox:
            with self.assertRaises(urllib.error.HTTPError):self.api('queue/resume',{})
            mailbox.return_value.connect.assert_not_called()
            self.api('queue/resume',{'entire_folder':True})
            mailbox.return_value.connect.assert_called_once()
            self.assertFalse(self.api('queue')['paused'])

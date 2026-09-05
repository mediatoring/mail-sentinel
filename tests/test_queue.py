import contextlib
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sentinel.config import Config, encode_toml, load_config
from sentinel.queue import QueueStore
from sentinel.budget import RunBudget, Cancelled
from sentinel.mail import Mailbox


def ref(uid):
    return {'host':'mail.example','port':993,'user':'review','folder':'AI-review','uidvalidity':'1','uid':str(uid)}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=QueueStore(self.tmp.name)
        self.c=Config(queue_workers=8,queue_per_hour=10000)

    def test_ten_thousand_refs_survive_restart_and_deduplicate(self):
        refs=[ref(i) for i in range(1,10001)]
        self.store.enqueue_page('scope',refs,10000)
        other=QueueStore(self.tmp.name)
        other.enqueue_page('scope',refs,500)
        self.assertEqual(other.overview()['counts']['pending'],10000)
        self.assertEqual(other.checkpoint('scope'),10000)
        self.assertEqual(len(other.overview()['items']),50)
        self.assertEqual(len(other.overview(199)['items']),50)

    def test_parallel_claims_are_unique_and_limited(self):
        self.store.enqueue_page('scope',[ref(i) for i in range(20)],20);self.store.pause(False)
        with ThreadPoolExecutor(max_workers=12) as pool:
            items=list(pool.map(lambda _:QueueStore(self.tmp.name).claim(self.c),range(12)))
        ids=[i['id'] for i in items if i]
        self.assertEqual(len(ids),8);self.assertEqual(len(set(ids)),8)

    def test_paused_queue_does_not_claim(self):
        self.store.enqueue_page('s',[ref(1)],1)
        self.assertIsNone(self.store.claim(self.c))

    def test_expired_claim_recovered_and_stale_result_rejected(self):
        self.store.enqueue_page('s',[ref(1)],1);self.store.pause(False)
        old=self.store.claim(self.c)
        with self.store.db() as db:db.execute('UPDATE queue_items SET lease=0')
        new=self.store.claim(self.c)
        self.assertNotEqual(old['owner'],new['owner'])
        self.assertFalse(self.store.finish(old,{'status':'completed'},3))
        self.assertTrue(self.store.finish(new,{'status':'completed'},3))
        self.assertEqual(len(self.store.list()),1)

    def test_cancel_revokes_claim_and_retry_resets_attempts(self):
        self.store.enqueue_page('s',[ref(1)],1);self.store.pause(False)
        item=self.store.claim(self.c);self.store.cancel(item['id'])
        self.assertFalse(self.store.owns(item))
        self.assertFalse(self.store.finish(item,{'status':'completed'},3))
        self.store.retry(item['id']);again=self.store.claim(self.c)
        self.assertEqual(again['attempts'],1)

    def test_failures_back_off_then_stop(self):
        self.store.enqueue_page('s',[ref(1)],1);self.store.pause(False)
        first=self.store.claim(self.c);self.store.finish(first,{'status':'incomplete'},2)
        self.assertIsNone(self.store.claim(self.c))
        with self.store.db() as db:db.execute('UPDATE queue_items SET ready=0')
        second=self.store.claim(self.c);self.store.finish(second,{'status':'incomplete'},2)
        self.assertEqual(self.store.overview()['counts'],{'failed':1})

    def test_hourly_limit_shared_by_stores(self):
        self.c.queue_per_hour=1
        self.store.enqueue_page('s',[ref(1),ref(2)],2);self.store.pause(False)
        item=self.store.claim(self.c);self.store.finish(item,{'status':'completed'},3)
        self.assertIsNone(QueueStore(self.tmp.name).claim(self.c))

    def test_daily_call_limit_shared_and_rolls(self):
        self.store.reserve_call(1)
        with self.assertRaises(RuntimeError):QueueStore(self.tmp.name).reserve_call(1)
        with self.store.db() as db:db.execute('UPDATE model_calls SET time=0')
        self.store.reserve_call(1)

    def test_rule_config_roundtrip(self):
        from pathlib import Path
        p=Path(self.tmp.name)/'settings.toml'
        p.write_text('check_modes = '+encode_toml(self.c.check_modes)+'\n')
        self.assertEqual(load_config(p).check_modes,self.c.check_modes)

    def test_cancel_before_any_call(self):
        import threading
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):RunBudget(self.c,event).consume('',{},[])

    def test_discovery_checkpoints_bounded_uid_windows_without_bodies(self):
        class Client:
            def response(self,name):return name,[b'1' if name=='UIDVALIDITY' else b'10001']
            def uid(self,command,*args):
                self_outer.assertEqual(command,'search')
                low,high=map(int,args[2].split(':'))
                return 'OK',[' '.join(str(i) for i in range(low,high+1)).encode()]
        self_outer=self
        box=Mailbox(Config(imap_host='mail.example',imap_user='review'))
        @contextlib.contextmanager
        def connect(readonly=True):
            self.assertTrue(readonly);yield Client()
        box.connect=connect
        for _ in range(20):box.discover(self.store)
        self.assertEqual(self.store.overview()['counts']['pending'],10000)
        box.discover(self.store)
        self.assertEqual(self.store.overview()['counts']['pending'],10000)


    def test_worker_persists_report_without_executing_quarantine(self):
        from sentinel.queue import QueueService
        from sentinel.tools import demo_messages
        from test_security import ModelDouble, call, finish
        self.store.enqueue_page('s',[ref(1)],1);self.store.pause(False)
        item=self.store.claim(self.c)
        config=Config(model='test-only')
        with patch('sentinel.queue.Mailbox') as mailbox, patch('sentinel.agent.Provider',return_value=ModelDouble([call('verify_sender'),finish(action='quarantine')])):
            mailbox.return_value.fetch_ref.return_value=demo_messages()[0]
            QueueService(config,self.store).run_one(item,config)
            mailbox.return_value.quarantine.assert_not_called()
        self.assertEqual(self.store.overview()['counts'],{'completed':1})
        self.assertEqual(self.store.list()[0]['result']['status'],'completed')

"""Persistent IMAP references, atomic claims and a bounded read-only worker service."""
import dataclasses
import hashlib
import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from .store import Store
from .mail import Mailbox
from .tools import Registry, organization, redaction_terms
from .privacy import Privacy
from .agent import Agent
from .budget import RunBudget


class QueueStore(Store):
    def __init__(self, directory, retention_days=30):
        super().__init__(directory, retention_days)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS queue_items (
                  id TEXT PRIMARY KEY, ref TEXT NOT NULL, status TEXT NOT NULL,
                  attempts INTEGER DEFAULT 0, ready REAL DEFAULT 0, owner TEXT,
                  lease REAL DEFAULT 0, created REAL, updated REAL, report_id TEXT, error TEXT);
                CREATE INDEX IF NOT EXISTS queue_ready ON queue_items(status,ready,created);
                CREATE INDEX IF NOT EXISTS queue_display ON queue_items(created DESC,id);
                CREATE INDEX IF NOT EXISTS queue_cleanup ON queue_items(status,updated);
                CREATE TABLE IF NOT EXISTS queue_cursors(scope TEXT PRIMARY KEY, uid INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS queue_starts(time REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS starts_time ON queue_starts(time);
                CREATE TABLE IF NOT EXISTS model_calls(time REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS calls_time ON model_calls(time);
                CREATE TABLE IF NOT EXISTS queue_control(id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER);
                INSERT OR IGNORE INTO queue_control VALUES(1,1);
            ''')

    def checkpoint(self, scope):
        with self.db() as db:
            row = db.execute('SELECT uid FROM queue_cursors WHERE scope=?',(scope,)).fetchone()
            return row[0] if row else 0

    def enqueue_page(self, scope, refs, cursor):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for ref in refs:
                text = json.dumps(ref, sort_keys=True)
                ident = hashlib.sha256(text.encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO queue_items(id,ref,status,created,updated) VALUES(?,?,?,?,?)',
                           (ident,text,'pending',now,now))
            db.execute('INSERT INTO queue_cursors VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET uid=MAX(uid,excluded.uid)', (scope,cursor))

    def pause(self, paused):
        with self.db() as db:
            db.execute('UPDATE queue_control SET paused=? WHERE id=1',(int(paused),))

    def paused(self):
        with self.db() as db:
            return bool(db.execute('SELECT paused FROM queue_control WHERE id=1').fetchone()[0])

    def claim(self, config):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE queue_items SET status=CASE WHEN attempts>=? THEN 'failed' ELSE 'pending' END, owner=NULL, error='interrupted', updated=? WHERE status='running' AND lease<?", (config.queue_attempts,now,now))
            if db.execute('SELECT paused FROM queue_control WHERE id=1').fetchone()[0]:
                return None
            daily = db.execute("SELECT count(*) FROM model_calls WHERE time>?",(now-86400,)).fetchone()[0]
            if daily >= config.daily_model_calls:
                return None
            active = db.execute("SELECT count(*) FROM queue_items WHERE status='running'").fetchone()[0]
            hourly = db.execute('SELECT count(*) FROM queue_starts WHERE time>?',(now-3600,)).fetchone()[0]
            if active >= config.queue_workers or hourly >= config.queue_per_hour:
                return None
            row = db.execute("SELECT id,ref,attempts FROM queue_items WHERE status='pending' AND ready<=? ORDER BY created,id LIMIT 1",(now,)).fetchone()
            if not row:
                return None
            owner = secrets.token_hex(16)
            db.execute("UPDATE queue_items SET status='running',attempts=attempts+1,owner=?,lease=?,updated=? WHERE id=?",(owner,now+config.max_seconds+config.timeout+120,now,row[0]))
            db.execute('INSERT INTO queue_starts VALUES(?)',(now,))
            db.execute('DELETE FROM queue_starts WHERE time<?',(now-86400,))
            return {'id':row[0],'ref':json.loads(row[1]),'attempts':row[2]+1,'owner':owner}

    def finish(self, item, result, attempts):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            live = db.execute("SELECT 1 FROM queue_items WHERE id=? AND owner=? AND status='running'",(item['id'],item['owner'])).fetchone()
            if not live:
                return False
            status = result['status']
            terminal = status == 'completed' or status in {'cancelled','skipped'} or item['attempts'] >= attempts
            target = status if status in {'completed','cancelled','skipped'} else ('failed' if terminal else 'pending')
            rid = secrets.token_hex(12)
            db.execute('INSERT INTO reports VALUES(?,?,?,?,?)',(rid,item['id'],now,status,json.dumps(result)))
            db.execute('UPDATE queue_items SET status=?,ready=?,owner=NULL,lease=0,updated=?,report_id=?,error=? WHERE id=?',
                (target,now+min(3600,30*2**(item['attempts']-1)),now,rid,None if status=='completed' else result.get('error','analysis_incomplete'),item['id']))
            return True

    def cancel(self, ident):
        with self.db() as db:
            # Revokes the claim so a stale worker cannot persist a completed result.
            return db.execute("UPDATE queue_items SET status='cancelled',owner=NULL,updated=? WHERE id=? AND status IN ('pending','running')",(time.time(),ident)).rowcount == 1

    def owns(self, item):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM queue_items WHERE id=? AND owner=? AND status='running'",(item['id'],item['owner'])).fetchone())

    def retry(self, ident):
        with self.db() as db:
            return db.execute("UPDATE queue_items SET status='pending',attempts=0,ready=0,error=NULL,updated=? WHERE id=? AND status IN ('failed','cancelled')",(time.time(),ident)).rowcount == 1

    def reserve_call(self, limit):
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM model_calls WHERE time<?',(now-86400,))
            if db.execute('SELECT count(*) FROM model_calls').fetchone()[0] >= limit:
                raise RuntimeError('daily_call_limit')
            db.execute('INSERT INTO model_calls VALUES(?)',(now,))

    def overview(self, page=0):
        with self.db() as db:
            counts=dict(db.execute('SELECT status,count(*) FROM queue_items GROUP BY status'))
            rows=db.execute('SELECT id,ref,status,attempts,error,report_id FROM queue_items ORDER BY created DESC,id LIMIT 50 OFFSET ?',(page*50,)).fetchall()
            return {'paused':self.paused(),'counts':counts,'page':page,
                    'daily_calls':db.execute('SELECT count(*) FROM model_calls WHERE time>?',(time.time()-86400,)).fetchone()[0],
                    'items':[{'id':r[0],'uid':json.loads(r[1])['uid'],'folder':json.loads(r[1]).get('folder',''),'status':r[2],'attempts':r[3],'error':r[4],'report_id':r[5]} for r in rows]}

    def runtime_state(self,config):
        now=time.time()
        with self.db() as db:
            calls=db.execute('SELECT count(*),min(time) FROM model_calls WHERE time>?',(now-86400,)).fetchone()
            starts=db.execute('SELECT count(*),min(time) FROM queue_starts WHERE time>?',(now-3600,)).fetchone()
            counts=dict(db.execute('SELECT status,count(*) FROM queue_items GROUP BY status'))
            ready=db.execute("SELECT min(ready) FROM queue_items WHERE status='pending'").fetchone()[0]
        status='watching';until=None
        if self.paused(): status='draining' if counts.get('running') else 'paused'
        elif counts.get('running'): status='running'
        elif calls[0]>=config.daily_model_calls: status='daily_limit';until=calls[1]+86400
        elif starts[0]>=config.queue_per_hour: status='hourly_limit';until=starts[1]+3600
        elif ready is not None and ready>now: status='retry_wait';until=ready
        elif counts.get('pending'): status='pending'
        return {'state':status,'resume_at':until,'total':sum(counts.values())}

    def cleanup(self):
        cutoff=time.time()-self.retention_days*86400
        with self.db() as db:
            db.execute("DELETE FROM queue_items WHERE updated<? AND status IN ('completed','failed','cancelled','skipped')",(cutoff,))
            self.prune_reports(db,cutoff)


class QueueService:
    def __init__(self, config, store):
        self.c=config
        self.store=store
        self.stop_event=threading.Event()
        self.thread=None
        self.last_error=None
        self.scan_lock=threading.Lock()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def discover(self):
        with self.scan_lock:
            more=Mailbox(dataclasses.replace(self.c)).discover(self.store)
            self.last_error=None
            return more

    def run_one(self,item,c):
        class Cancellation:
            def is_set(inner):
                return self.stop_event.is_set() or not self.store.owns(item)
        try:
            message=Mailbox(c).fetch_ref(item['ref'])
            org=organization(c)
            reg=Registry(message,org,Privacy(redaction_terms(org,c)),c)
            result=Agent(reg,budget=RunBudget(c,Cancellation(),self.store)).run()
        except LookupError:
            result={'status':'skipped','report':None,'error':'message_unavailable'}
        except Exception:
            result={'status':'incomplete','report':None,'error':'mailbox_or_configuration_error'}
        self.store.finish(item,result,c.queue_attempts)

    def run(self):
        next_scan=0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=set()
            while not self.stop_event.is_set():
                try:
                    for finished in [f for f in futures if f.done()]:
                        if finished.exception() is not None:
                            self.last_error = 'local_persistence_error'
                        futures.remove(finished)
                    if not self.store.paused():
                        if time.monotonic()>=next_scan:
                            try:
                                more=self.discover()
                                self.store.cleanup()
                            except Exception:
                                more=False
                                self.last_error='mailbox_or_configuration_error'
                            next_scan=time.monotonic()+(1 if more else self.c.poll_seconds)
                        while len(futures)<self.c.queue_workers:
                            item=self.store.claim(self.c)
                            if not item:
                                break
                            futures.add(pool.submit(self.run_one,item,dataclasses.replace(self.c)))
                except Exception:
                    # Retain leases for recovery; a temporary storage fault must
                    # not silently terminate the monitoring thread.
                    self.last_error = 'local_persistence_error'
                self.stop_event.wait(1)

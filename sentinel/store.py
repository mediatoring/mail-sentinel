"""Local pseudonymized reports and single-use, message-bound approvals."""
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from contextlib import contextmanager


class Store:
    def __init__(self, directory, retention_days=30):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "reports.sqlite3"
        self.retention_days = retention_days
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, message_id TEXT, created REAL, status TEXT, result TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS reports_created ON reports(created DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS reports_message ON reports(message_id,created DESC)")
            db.execute("DELETE FROM reports WHERE created < ?", (time.time()-retention_days*86400,))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self.pending = {}

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.path,timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, message_id, result):
        rid = secrets.token_hex(12)
        with self.lock, self.db() as db:
            db.execute("DELETE FROM reports WHERE created < ?", (time.time()-self.retention_days*86400,))
            db.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?)", (rid, message_id, time.time(), result["status"], json.dumps(result)))
        return rid

    def seen(self, message_id):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM reports WHERE message_id=? AND status='completed' LIMIT 1", (message_id,)).fetchone())

    def list(self, page=0, summary=False):
        with self.db() as db:
            rows=[]
            for r in db.execute("SELECT id, message_id, created, result FROM reports ORDER BY created DESC LIMIT 100 OFFSET ?",(page*100,)):
                result=json.loads(r[3])
                if summary:
                    report=result.get("report")
                    result={"status":result["status"],"report":({"verdict":report["verdict"],"summary":report.get("summary","")[:500]} if report else None)}
                rows.append({"id":r[0],"message_id":r[1],"created":r[2],"result":result})
            return rows

    def latest(self, message_id):
        with self.db() as db:
            row=db.execute("SELECT id,result FROM reports WHERE message_id=? ORDER BY created DESC LIMIT 1",(message_id,)).fetchone()
            return {"report_id":row[0],**json.loads(row[1])} if row else None

    def report(self, ident):
        with self.db() as db:
            row=db.execute("SELECT result FROM reports WHERE id=?",(ident,)).fetchone()
            return json.loads(row[0]) if row else None


    def attempts(self, message_id):
        with self.db() as db:
            return db.execute("SELECT count(*) FROM reports WHERE message_id=? AND created>?", (message_id, time.time()-86400)).fetchone()[0]

    def propose(self, report_id, message):
        with self.lock:
            token = secrets.token_urlsafe(24)
            self.pending[token] = {"report_id": report_id, "message_id": message["id"], "ref": dict(message["imap_ref"]), "expires": time.time()+600}
            return token

    def consume(self, token, report_id):
        with self.lock:
            proposal = self.pending.get(token)
            if not proposal or proposal["report_id"] != report_id or proposal["expires"] < time.time():
                raise ValueError("Approval expired or mismatched")
            return self.pending.pop(token)

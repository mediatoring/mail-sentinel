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
    # Ordered schema steps; PRAGMA user_version records how many have run.
    # The baseline is idempotent so databases written before versioning adopt it in place.
    # Every later step runs exactly once and must not rely on IF NOT EXISTS.
    MIGRATIONS = [
        (
            "CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, message_id TEXT, created REAL, status TEXT, result TEXT)",
            "CREATE INDEX IF NOT EXISTS reports_created ON reports(created DESC)",
            "CREATE INDEX IF NOT EXISTS reports_message ON reports(message_id,created DESC)",
        ),
    ]

    def __init__(self, directory, retention_days=30):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "reports.sqlite3"
        self.retention_days = retention_days
        self.lock = threading.RLock()
        self.migrate()
        # Separate disposable cache: no change to the report/queue migration numbering.
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS investigation_cache (id TEXT PRIMARY KEY, updated REAL, state TEXT)')
            db.execute('DELETE FROM investigation_cache WHERE updated<?', (time.time()-900,))
        with self.db() as db:
            self.prune_reports(db, time.time()-retention_days*86400)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self.pending = {}

    def schema_version(self, connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > len(self.MIGRATIONS):
            raise RuntimeError(f"{self.path} has schema version {version}; this build knows {len(self.MIGRATIONS)}")
        return version

    def migrate(self):
        """Apply pending schema steps in one transaction so concurrent openers agree on the result."""
        target = len(self.MIGRATIONS)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.isolation_level = None
        try:
            if self.schema_version(connection) == target:
                return
            connection.execute("BEGIN IMMEDIATE")
            version = self.schema_version(connection)
            if version < target:
                for statement in (s for step in self.MIGRATIONS[version:] for s in step):
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version={target}")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

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
            self.prune_reports(db, time.time()-self.retention_days*86400)
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
            row=db.execute("SELECT id,result FROM reports WHERE message_id=? AND status!='action' ORDER BY created DESC LIMIT 1",(message_id,)).fetchone()
            return {"report_id":row[0],**json.loads(row[1])} if row else None

    def report(self, ident):
        with self.db() as db:
            row=db.execute("SELECT result FROM reports WHERE id=?",(ident,)).fetchone()
            return json.loads(row[0]) if row else None


    def attempts(self, message_id):
        with self.db() as db:
            return db.execute("SELECT count(*) FROM reports WHERE message_id=? AND created>?", (message_id, time.time()-86400)).fetchone()[0]

    def propose(self, report_id, message):
        if message.get('source') != 'imap' or not isinstance(message.get('imap_ref'),dict):
            raise ValueError('Quarantine requires an IMAP message')
        with self.lock:
            token = secrets.token_urlsafe(24)
            self.pending[token] = {"report_id": report_id, "message_id": message["id"], "ref": dict(message["imap_ref"]), "expires": time.time()+600}
            return token

    def consume(self, token, report_id):
        with self.lock:
            if not isinstance(token,str) or not token.isascii():
                raise ValueError('Approval expired or mismatched')
            matched = next((key for key in self.pending if secrets.compare_digest(key,token)),None)
            proposal = self.pending.get(matched)
            if not proposal or proposal["report_id"] != report_id or proposal["expires"] < time.time():
                raise ValueError("Approval expired or mismatched")
            return self.pending.pop(matched)

    def prune_reports(self, db, cutoff):
        # Called on startup, interactive saves and queue cleanup alike.
        db.execute('DELETE FROM reports WHERE created<?',(cutoff,))

    def save_investigation(self, key, state):
        with self.lock, self.db() as db:
            db.execute('DELETE FROM investigation_cache WHERE updated<?', (time.time()-900,))
            db.execute('INSERT OR REPLACE INTO investigation_cache VALUES(?,?,?)', (key, time.time(), json.dumps(state)))

    def load_investigation(self, key):
        with self.db() as db:
            row = db.execute('SELECT state FROM investigation_cache WHERE id=? AND updated>?', (key, time.time()-900)).fetchone()
            return json.loads(row[0]) if row else None

    def delete_investigation(self, key):
        with self.lock, self.db() as db:
            db.execute('DELETE FROM investigation_cache WHERE id=?', (key,))

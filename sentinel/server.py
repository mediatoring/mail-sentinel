"""Loopback-only local UI with authenticated, same-origin API requests."""
import dataclasses
import base64
import json
import hashlib
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .agent import Agent
from .mail import Mailbox, parse_email
from .privacy import Privacy
from .providers import Provider
from .queue import QueueStore, QueueService
from .budget import RunBudget
from .config import encode_toml
from .tools import Registry, demo_messages, organization, redaction_terms


def connection_signature(config):
    return hashlib.sha256(json.dumps([config.provider,config.endpoint,config.model,config.api_key,config.allow_external]).encode()).hexdigest()


class LocalHTTPServer(ThreadingHTTPServer):
    """Loopback service startup must not depend on reverse DNS availability."""
    def server_bind(self):
        from socketserver import TCPServer
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class ConnectionDraft:
    def __init__(self, config, data):
        permitted={"provider","model","base_url","api_key","allow_external"}
        if set(data)-permitted:
            raise ValueError("Unknown connection setting")
        values={k:v for k,v in data.items() if k!='api_key'}
        for key,value in values.items():
            if type(value) is not type(getattr(config,key)):
                raise ValueError("Invalid connection setting")
        self.config=dataclasses.replace(config,**values).validate()
        same=(self.config.provider,self.config.endpoint)==(config.provider,config.endpoint)
        self.api_key=data.get('api_key') or (config.api_key if same else '')
        if not isinstance(self.api_key,str) or len(self.api_key)>4000:
            raise ValueError("Invalid credential")

    def __getattr__(self,name):
        return getattr(self.config,name)


class Application:
    def __init__(self, config):
        self.config = config
        self.store = QueueStore(config.data_dir, config.retention_days)
        self.store.pause(True)
        self.queue = QueueService(config, self.store)
        self.queue.start()
        self.workers = []
        self.cancellations = {}
        self.connection_ok = False
        self.verified_connection = None
        self.messages = {m["id"]: m for m in demo_messages()}
        self.jobs = {}
        self.lock = threading.RLock()
        self.busy = False
        self.token = secrets.token_urlsafe(32)

    def prepare(self, mid):
        with self.lock:
            msg = self.messages[mid]
            org = organization(self.config, demo=msg["source"] == "demo")
            privacy = Privacy(redaction_terms(org, self.config))
            registry = Registry(msg, org, privacy, dataclasses.replace(self.config))
            return registry

    def start(self, mid, consent):
        if not self.config.model:
            raise ValueError("Configure a real AI model first")
        if self.config.external and (not consent or not self.config.allow_external or not self.config.api_key):
            raise ValueError("External AI requires explicit consent, configuration opt-in and an API key")
        with self.lock:
            if self.busy:
                raise ValueError("One investigation is already running")
            registry = self.prepare(mid)
            jobid = secrets.token_hex(12)
            self.jobs[jobid] = {"status": "running", "events": [], "message_id": mid}
            self.busy = True
            self.cancellations[jobid] = threading.Event()

        def run():
            try:
                def event(e):
                    with self.lock:
                        self.jobs[jobid]["events"].append(e)
                result = Agent(registry,budget=RunBudget(registry.c,self.cancellations[jobid],self.store)).run(event)
                rid = self.store.save(mid, result)
                approval = None
                if result["status"] == "completed" and result["report"]["proposed_action"] == "quarantine" and registry.message["source"] == "imap" and self.config.allow_quarantine:
                    approval = self.store.propose(rid, registry.message)
                with self.lock:
                    self.jobs[jobid].update(result, report_id=rid, approval_token=approval)
                    # Bound memory use; completed jobs remain available in the database.
                    for old in list(self.jobs)[:-50]:
                        self.jobs.pop(old, None)
                        self.cancellations.pop(old, None)
            except Exception:
                with self.lock:
                    self.jobs[jobid].update(status="incomplete", error="Local persistence failed. No action performed.")
            finally:
                with self.lock:
                    self.busy = False
        worker = threading.Thread(target=run, daemon=True)
        with self.lock:
            self.workers = [w for w in self.workers if w.is_alive()]
            self.workers.append(worker)
        worker.start()
        return {"job_id": jobid}


def serve(config, port=8765, config_path="sentinel.toml"):
    from .lifecycle import instance_lock
    with instance_lock(config.data_dir):
        _serve(config, port, config_path)


def _serve(config, port, config_path):
    assets = Path(__file__).with_name("static")

    class Handler(BaseHTTPRequestHandler):
        def version_string(self):
            return 'Mail Sentinel'

        def log_message(self, *args):
            pass  # No secrets, subjects or URLs in HTTP logs.

        def send(self, obj, code=200, mime="application/json"):
            body = json.dumps(obj, ensure_ascii=False).encode() if mime == "application/json" else obj
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def send_error(self, code, message=None, explain=None):
            self.send({'error':'Unsupported request'},code)

        def valid_host(self):
            return self.headers.get('Host','').lower() in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}

        def authorized(self):
            host = self.headers.get("Host", "").lower()
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in allowed:
                return False
            origin = self.headers.get("Origin")
            if origin and origin.lower() != "http://" + host:
                return False
            token=self.headers.get("X-Sentinel-Token", "")
            return token.isascii() and secrets.compare_digest(token, app.token)

        def do_GET(self):
            try:
                return self.get()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                return self.send({'error':'Local data or extension could not be loaded'},500)

        def get(self):
            path = urlsplit(self.path).path
            if not self.valid_host():
                return self.send({"error": "Invalid host"}, 403)
            static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/controls.js": "controls.js", "/i18n.js":"i18n.js"}
            if path in static:
                mime = {"/": "text/html", "/app.js": "application/javascript", "/style.css": "text/css", "/controls.js": "application/javascript", "/i18n.js":"application/javascript"}[path]
                return self.send((assets / static[path]).read_bytes(), mime=mime)
            if not self.authorized():
                return self.send({"error": "Open the authenticated URL printed in your terminal"}, 403)
            if path == "/api/state":
                return self.send({"provider": config.provider, "model": config.model, "configured": bool(config.model and (not config.external or config.api_key)), "external": config.external,
                                  "connection_ok": app.connection_ok, "key_configured":bool(config.api_key),
                                  "active_job":next(({"job_id":k,"message_id":v["message_id"]} for k,v in list(app.jobs.items()) if v["status"]=="running"),None), "allow_external": config.allow_external, "privacy_mode": config.privacy_mode, "language": config.language,
                                  "quarantine_enabled": config.allow_quarantine,
                                  "messages": [{k: m[k] for k in ("id", "subject", "sender", "source")} for m in app.messages.values()]})
            if path.startswith("/api/messages/"):
                mid=path.rsplit("/",1)[-1]
                with app.lock:
                    message=app.messages.get(mid)
                    if not message:
                        return self.send({"error":"Message not found"},404)
                    # Authenticated local display only; never part of a model request.
                    body={k:message.get(k) for k in ("id","subject","sender","body","body_truncated","body_unavailable","source")}
                    body["latest"]=app.store.latest(mid)
                    reg=app.prepare(mid)
                    body["reference_required"]=any(reg.mode(n) in {'required','conditional'} and t.reference_keys for n,t in reg.catalog.items())
                    body["reference_available"]=all(bool(reg.org.get(k)) for n,t in reg.catalog.items() if reg.mode(n) in {'required','conditional'} for k in t.reference_keys)
                    return self.send(body)
            if path == "/api/queue":
                from urllib.parse import parse_qs
                try:
                    page=int(parse_qs(urlsplit(self.path).query).get("page",["0"])[0])
                    if not 0<=page<=100000: raise ValueError()
                except ValueError:
                    return self.send({"error":"Invalid page"},400)
                return self.send({**app.store.overview(page),**app.store.runtime_state(config),"error":app.queue.last_error,"discovering":app.queue.scan_lock.locked(),"folder":config.imap_folder,"host":config.imap_host,"since":config.queue_since,"per_hour":config.queue_per_hour,"call_limit":config.daily_model_calls})
            if path == "/api/reports":
                from urllib.parse import parse_qs
                try:
                    page=int(parse_qs(urlsplit(self.path).query).get("page",["0"])[0])
                    if not 0<=page<=100000: raise ValueError()
                except ValueError:
                    return self.send({"error":"Invalid page"},400)
                return self.send(app.store.list(page,summary=True))
            if path.startswith("/api/reports/"):
                result=app.store.report(path.rsplit("/",1)[-1])
                return self.send(result or {"error":"Report not found"},200 if result else 404)
            if path == "/api/data-sources":
                try:
                    from .data_sources import load_sources
                    return self.send({"version":1,"sources":load_sources(config)})
                except Exception:
                    return self.send({"error":"Data source configuration could not be loaded"},400)
            if path == "/api/checks":
                try:
                    reg=Registry({"source":"file","sender":"","body":"","subject":"","attachments":[],"urls":[]},organization(config),Privacy(),dataclasses.replace(config))
                    return self.send({"checks":reg.check_catalog()})
                except Exception as e:
                    return self.send({"error":"Check configuration could not be loaded; verify plugin modules and data source file"},400)
            if path == "/api/settings":
                fields = ["provider", "model", "base_url", "language", "privacy_mode", "allow_external", "imap_host", "imap_user", "imap_folder", "organization_file", "allow_quarantine", "quarantine_folder", "check_modes", "queue_workers", "queue_per_hour", "queue_attempts", "queue_since", "daily_model_calls", "max_steps", "max_seconds", "max_output_tokens", "max_input_bytes", "context_tokens", "retention_days", "imap_auth", "enabled_skills", "enable_specialists", "plugins", "organization_rules", "data_sources_file"]
                return self.send({k: getattr(config, k) for k in fields})
            if path.startswith("/api/jobs/"):
                with app.lock:
                    job = app.jobs.get(path.rsplit("/", 1)[-1])
                    return self.send(job or {"error": "Job not found"}, 200 if job else 404)
            return self.send({"error": "Not found"}, 404)

        def do_POST(self):
            if not self.authorized():
                return self.send({"error": "Unauthorized request"}, 403)
            try:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self.send({'error':'Invalid request body'},400)
                if not 0 < length <= config.max_message_bytes * 2:
                    raise ValueError("Request too large or empty")
                try:
                    data = json.loads(self.rfile.read(length))
                except (ValueError,UnicodeError):
                    return self.send({'error':'Invalid request body'},400)
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                path = urlsplit(self.path).path
                required = {'/api/cancel':'job_id','/api/queue/cancel':'id','/api/queue/retry':'id',
                            '/api/remove-message':'message_id','/api/preview':'message_id','/api/analyze':'message_id',
                            '/api/import':'eml_base64','/api/approve':'token'}
                if path in required and (not isinstance(data.get(required[path]),str) or not data[required[path]]):
                    return self.send({'error':'Invalid request fields'},400)
                if path=='/api/approve' and (not isinstance(data.get('report_id'),str) or not data['report_id']):
                    return self.send({'error':'Invalid request fields'},400)
                if path in {'/api/preview','/api/analyze'} and data['message_id'] not in app.messages:
                    return self.send({'error':'Message not found'},404)
                if path == "/api/models":
                    return self.send({"models":Provider(ConnectionDraft(config,data)).models()})
                if path == "/api/cancel":
                    with app.lock:
                        job=app.jobs.get(data['job_id'])
                        if not job:
                            return self.send({'error':'Job not found'},404)
                        if job['status']!='running':
                            return self.send({'error':'Operation is not available in the current state'},409)
                        app.cancellations[data['job_id']].set()
                    return self.send({"status":"cancellation_requested"})
                if path == "/api/queue/pause":
                    app.store.pause(True)
                    return self.send({"status":"paused"})
                if path == "/api/queue/resume":
                    if not config.model:
                        raise ValueError("Configure a real AI model first")
                    if config.external and (not config.allow_external or not config.api_key or data.get("consent") is not True):
                        raise ValueError("Authorize external processing for the queue")
                    if not config.imap_host or not config.imap_user or not os.environ.get(config.imap_token_env if config.imap_auth=='oauth2' else config.imap_password_env):
                        raise ValueError("Configure mailbox connection and credentials first")
                    if not config.queue_since and data.get('entire_folder') is not True:
                        raise ValueError("Choose a start date or explicitly select the entire folder")
                    with Mailbox(config).connect():
                        pass
                    app.store.pause(False)
                    return self.send({"status":"running"})
                if path == "/api/queue/cancel":
                    if not app.store.cancel(data["id"]):
                        return self.send({'error':'Queue item not found or state has changed'},409)
                    return self.send({"status":"cancelled"})
                if path == "/api/queue/retry":
                    if not app.store.retry(data["id"]):
                        return self.send({'error':'Queue item not found or state has changed'},409)
                    return self.send({"status":"pending"})
                if path == "/api/settings":
                    if not data:
                        return self.send({'error':'No settings supplied'},400)
                    with app.lock:
                        if app.busy or not app.store.paused() or app.store.overview()["counts"].get("running",0):
                            raise ValueError("Pause the queue and wait for active investigations before editing settings")
                        values = dataclasses.asdict(config)
                        fields = {"provider", "model", "base_url", "language", "privacy_mode", "allow_external", "imap_host", "imap_user", "imap_folder", "organization_file", "allow_quarantine", "quarantine_folder", "check_modes", "queue_workers", "queue_per_hour", "queue_attempts", "queue_since", "daily_model_calls", "max_steps", "max_seconds", "max_output_tokens", "max_input_bytes", "context_tokens", "retention_days", "imap_auth", "enabled_skills", "enable_specialists", "plugins", "organization_rules", "data_sources_file"}
                        if set(data) - fields - {"api_key", "imap_password", "data_sources"}:
                            raise ValueError("Unknown setting")
                        for k in fields & set(data):
                            if type(data[k]) is not type(values[k]) or (isinstance(data[k], str) and len(data[k]) > (16000 if k=="organization_rules" else 4000)):
                                raise ValueError("Invalid setting")
                            values[k] = data[k]
                        if 'data_sources' in data:
                            from .data_sources import validate_sources
                            document=validate_sources(data['data_sources'])
                            from .data_sources import load_sources
                            try:old_query_names={q['name'] for source in load_sources(config) for q in source['queries']}
                            except Exception:old_query_names=set()
                            new_query_names={q['name'] for source in document['sources'] for q in source['queries']}
                            values['check_modes']={name:mode for name,mode in values['check_modes'].items() if name not in old_query_names-new_query_names}
                            for source in document['sources']:
                                if source['driver']=='sqlite':source['path']=str((Path(config_path).resolve().parent/source['path']).resolve())
                            encoded=json.dumps(document,ensure_ascii=False,indent=2)
                            destination=Path(config.data_dir).resolve()/('sources-'+hashlib.sha256(encoded.encode()).hexdigest()[:24]+'.json')
                            destination.parent.mkdir(parents=True,exist_ok=True)
                            # Immutable source document; the config switches to it atomically below.
                            if not destination.exists():
                                with destination.open('x',encoding='utf-8') as f:f.write(encoded)
                                os.chmod(destination,0o600)
                            values['data_sources_file']=str(destination)
                        from .config import Config
                        updated = Config(**values).validate()
                        if updated.plugins != config.plugins:
                            probe=Registry({'source':'file','sender':'','body':'','subject':'','attachments':[],'urls':[]},organization(updated),Privacy(),dataclasses.replace(updated,check_modes={}))
                            removed=set(config.check_modes)-set(probe.catalog)
                            updated.check_modes={k:v for k,v in updated.check_modes.items() if k not in removed}
                            values['check_modes']=updated.check_modes
                        registry=Registry({"source":"file","sender":"","body":"","subject":"","attachments":[],"urls":[]},organization(updated),Privacy(),dataclasses.replace(updated))
                        minimum=1+sum(row['mode'] in {'required','conditional'} for row in registry.check_catalog())
                        if updated.max_steps<minimum:
                            raise ValueError("Model call limit is too low for the selected checks (minimum "+str(minimum)+")")
                        credential_scope_changed=(config.provider,config.endpoint)!=(updated.provider,updated.endpoint)
                        mailbox_changed=(config.imap_host,config.imap_user,config.imap_port)!=(updated.imap_host,updated.imap_user,updated.imap_port)
                        if (mailbox_changed or config.imap_folder!=updated.imap_folder or config.queue_since!=updated.queue_since) and app.store.overview()['counts'].get('pending',0):
                            raise ValueError("Finish or cancel waiting queue items before changing mailbox scope")
                        for key in ("api_key", "imap_password"):
                            if key in data and (not isinstance(data[key], str) or len(data[key]) > 4000):
                                raise ValueError("Invalid credential")
                        if updated.allow_quarantine:
                            password=data.get('imap_password') or (os.environ.get(updated.imap_password_env) if not mailbox_changed else '')
                            with Mailbox(updated).connect(password=password) as client:
                                Mailbox(updated).check_quarantine(client)
                        p = Path(config_path).resolve()
                        content = "# Secrets are held in process memory or environment variables, not this file.\n" + "\n".join(k + " = " + encode_toml(v) for k, v in values.items()) + "\n"
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent, delete=False) as f:
                            f.write(content)
                            temporary = f.name
                        os.replace(temporary, p)
                        if credential_scope_changed:
                            os.environ.pop(config.api_key_env,None)
                        if mailbox_changed:
                            os.environ.pop(config.imap_password_env,None)
                        for k in fields:
                            setattr(config, k, getattr(updated, k))
                        for k, env in [("api_key", config.api_key_env), ("imap_password", config.imap_password_env)]:
                            if data.get(k):
                                if not isinstance(data[k], str) or len(data[k]) > 4000:
                                    raise ValueError("Invalid credential")
                                os.environ[env] = data[k]
                        app.store.pending.clear()
                        app.store.retention_days = config.retention_days
                        app.connection_ok = app.verified_connection == connection_signature(config)
                    return self.send({"status": "saved"})
                if path == "/api/preview":
                    reg = app.prepare(data["message_id"])
                    # Show potential subsequent outputs, not just the initial prompt.
                    preview = {"initial_message": reg.privacy.message(reg.message, config.privacy_mode), "possible_tool_outputs": {}}
                    preview["on_demand_tools"]=[]
                    for name,tool in reg.tools.items():
                        if tool.preview and not tool.parameters.get("required"):
                            preview["possible_tool_outputs"][name]=reg.execute(name,{})
                        else:
                            preview["on_demand_tools"].append({"name":name,"description":tool.description,"parameters":tool.parameters,"note":"Results are retrieved during investigation and pass through the saved privacy policy."})
                    return self.send(preview)
                if path == "/api/analyze":
                    return self.send(app.start(data["message_id"], data.get("consent") is True))
                if path == "/api/imap":
                    if app.busy:
                        raise ValueError("Wait for the active investigation")
                    msgs = Mailbox(config).fetch()
                    with app.lock:
                        app.messages = {k: v for k, v in app.messages.items() if v["source"] == "demo"}
                        app.messages.update({m["id"]: m for m in msgs})
                    return self.send({"count": len(msgs)})
                if path == "/api/remove-message":
                    with app.lock:
                        if app.busy: raise ValueError("Wait for the active investigation")
                        msg=app.messages.get(data.get('message_id'))
                        if not msg:
                            return self.send({'error':'Message not found'},404)
                        if msg['source']=='demo':
                            return self.send({'error':'Sample messages cannot be removed'},409)
                        app.messages.pop(msg['id'])
                    return self.send({"status":"removed"})
                if path == "/api/import":
                    raw = base64.b64decode(data["eml_base64"], validate=True)
                    msg = parse_email(raw, config.max_message_bytes)
                    with app.lock:
                        if len(app.messages) >= 100:
                            raise ValueError("Message list full; remove reviewed messages from the input list")
                        app.messages[msg["id"]] = msg
                    return self.send({"message_id": msg["id"]})
                if path == "/api/approve":
                    proposal = app.store.consume(data["token"], data["report_id"])
                    Mailbox(config).quarantine(proposal["ref"])
                    app.store.save(proposal["message_id"], {"status": "action", "action": "quarantine", "report_id": data["report_id"], "approved_by": "local authenticated operator"})
                    return self.send({"status": "moved"})
                if path == "/api/connection":
                    # Real inference, no message data. Verifies native tool use.
                    d = [{"name": "connection_ok", "description": "Confirm this connection", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}]
                    draft=ConnectionDraft(config,data)
                    if connection_signature(draft)==connection_signature(config):
                        app.connection_ok=False
                        app.verified_connection=None
                    app.store.reserve_call(config.daily_model_calls)
                    result = Provider(draft).decide("Call connection_ok exactly once.", {"connection_test": True}, d)
                    if result != {"name": "connection_ok", "arguments": {}}:
                        raise ValueError("Model did not return the required native tool call")
                    app.verified_connection=connection_signature(draft)
                    if app.verified_connection==connection_signature(config):
                        app.connection_ok = True
                    return self.send({"status": "connected"})
                return self.send({"error": "Not found"}, 404)
            except Exception as e:
                # Configuration errors have useful local messages; network exceptions may contain secrets.
                from .providers import ProviderError
                msg = str(e) if isinstance(e, (ValueError, ProviderError)) else "Operation failed; check local configuration and credentials"
                return self.send({"error": msg}, 400)

    server = LocalHTTPServer(("127.0.0.1", port), Handler)
    try:
        app = Application(config)
    except BaseException:
        server.server_close()
        raise
    server.daemon_threads = True
    print(f"Mail Sentinel: http://127.0.0.1:{server.server_port}/#token={app.token}", flush=True)
    print("Local single-user service. Keep this URL private. Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.store.pause(True)
        for cancellation in list(app.cancellations.values()):
            cancellation.set()
        app.queue.stop()
        if app.queue.thread is not None:
            app.queue.thread.join(timeout=config.timeout + 5)
        for worker in app.workers:
            worker.join(timeout=config.timeout + 5)

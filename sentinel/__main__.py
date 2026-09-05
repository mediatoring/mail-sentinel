import argparse
import dataclasses
import getpass
import json
import os
from pathlib import Path
import time
from .agent import Agent
from .config import Config, load_config
from .mail import Mailbox, parse_email
from .privacy import Privacy
from .server import serve
from .store import Store
from .tools import Registry, demo_messages, organization, redaction_terms


def _main():
    parser = argparse.ArgumentParser(description="Mail Sentinel — real AI email investigation")
    parser.add_argument("--config", default="sentinel.toml")
    sub = parser.add_subparsers(dest="command")
    web = sub.add_parser("serve", help="Start local EN/CZ interface")
    web.add_argument("--port", type=int, default=8765)
    sub.add_parser("setup", help="Create configuration interactively")
    sub.add_parser("doctor", help="Test actual model tool calling")
    sub.add_parser("check", help="Check configuration and extensions without contacting AI or IMAP; output contains no credentials")
    backup = sub.add_parser("backup", help="Create a consistent database snapshot without overwriting files")
    backup.add_argument("destination")
    scan = sub.add_parser("scan", help="Analyze demo or .eml through a real model")
    scan.add_argument("--demo", type=int, choices=range(1,len(demo_messages())+1))
    scan.add_argument("--file")
    scan.add_argument("--allow-external", action="store_true")
    sub.add_parser("export-demo", help="Write demo emails as .eml")
    watch = sub.add_parser("watch", help="Read-only periodic IMAP analysis")
    watch.add_argument("--allow-external", action="store_true")
    watch.add_argument("--entire-folder", action="store_true", help="Authorize scanning the entire selected folder when queue_since is empty")
    mcp = sub.add_parser("mcp", help="Expose one message to an external AI harness over stdio MCP")
    mcp.add_argument("--demo", type=int, choices=range(1,len(demo_messages())+1))
    mcp.add_argument("--file")
    mcp.add_argument("--allow-client-data", action="store_true")
    args = parser.parse_args()
    if args.command == "setup":
        p = Path(args.config)
        if p.exists():
            raise SystemExit("Configuration exists. Edit it directly to preserve your settings.")
        provider = input("Provider [local/openai/anthropic/gemini/compatible] (local): ").strip() or "local"
        model = input("Exact model identifier: ").strip()
        base = input("Base URL (blank for default): ").strip() if provider in {"local", "compatible"} else ""
        language = input("Interface [en/cs] (en): ").strip() or "en"
        external = provider != "local" and input("Permit sending approved data to external AI? [yes/NO]: ") == "yes"
        mode = input("Privacy [evidence_only/redacted_text] (redacted_text): ").strip() or "redacted_text"
        cfg = Config(provider=provider, model=model, base_url=base, language=language, privacy_mode=mode, allow_external=external).validate()
        values = {"provider": provider, "model": model, "base_url": base, "language": language, "privacy_mode": mode, "allow_external": external}
        text = "# Mail Sentinel: API and IMAP secrets belong in environment variables.\n" + "\n".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + "\n"
        p.write_text(text, "utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        print("Configuration written. Set SENTINEL_API_KEY if required, then run: python -m sentinel doctor")
        return
    c = load_config(args.config)
    if args.command == "check":
        from .diagnostics import readiness
        result = readiness(c)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ready"]:
            raise SystemExit(2)
        return
    if args.command == "backup":
        from .diagnostics import backup_database
        print("Database backup saved: " + str(backup_database(c.data_dir, args.destination)))
        return
    if args.command == "mcp":
        from .mcp import serve_stdio
        if bool(args.demo)==bool(args.file):
            raise SystemExit("Choose exactly one of --demo or --file")
        if args.file and not args.allow_client_data:
            raise SystemExit("Review privacy settings and use --allow-client-data to expose this message's protected evidence to the MCP client")
        if args.file:
            with open(args.file,"rb") as f:msg=parse_email(f.read(c.max_message_bytes+1),c.max_message_bytes)
        else:msg=demo_messages()[args.demo-1]
        c=dataclasses.replace(c,enabled_skills=[],enable_specialists=False)
        org=organization(c,demo=msg["source"]=="demo")
        serve_stdio(Registry(msg,org,Privacy(redaction_terms(org,c)),c))
        return
    if args.command == "export-demo":
        from email.message import EmailMessage
        from .tools import demo_dataset
        out = Path("demo-emails")
        out.mkdir(exist_ok=True)
        for i, entry in enumerate(demo_dataset()["messages"], 1):
            m = EmailMessage()
            m["Subject"], m["From"], m["To"] = entry["subject"], entry["sender"], "it@example.org"
            m.set_content(entry["body"])
            if entry.get("attachment_name"):
                m.add_attachment(b"Synthetic attachment. No executable content.",maintype="text",subtype="plain",filename=entry["attachment_name"])
            (out / f"{i}.eml").write_bytes(m.as_bytes())
        print("Wrote demo emails to demo-emails/.")
        return
    if args.command in {"doctor", "scan", "watch"} and c.external and not c.api_key and os.isatty(0):
        os.environ[c.api_key_env] = getpass.getpass("AI API key (kept in process memory): ")
    if args.command == "doctor":
        from .providers import Provider
        d = [{"name": "connection_ok", "description": "Confirm connection", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}]
        result = Provider(c).decide("Call connection_ok.", {"test": True}, d)
        if result != {"name": "connection_ok", "arguments": {}}:
            raise SystemExit("Model did not demonstrate native tool calling")
        print("Real AI connection and native tool calling verified.")
        return
    if args.command in {"scan", "watch"}:
        if c.external and not args.allow_external:
            raise SystemExit("Review privacy configuration, then pass --allow-external to authorize this run")
        if c.external and (not c.allow_external or not c.api_key):
            raise SystemExit("Configure an API key and allow_external before processing mail")
        if not c.model:
            raise SystemExit("Configure a real AI model first: python -m sentinel setup")
        from .queue import QueueStore, QueueService
        from .budget import RunBudget
        from .lifecycle import instance_lock
        with instance_lock(c.data_dir):
            store = QueueStore(c.data_dir, c.retention_days)
            def run(msg):
                org = organization(c, demo=msg["source"] == "demo")
                result = Agent(Registry(msg, org, Privacy(redaction_terms(org, c)), c),budget=RunBudget(c,store=store)).run()
                rid = store.save(msg["id"], result)
                print(json.dumps({"report_id": rid, **result}, ensure_ascii=False), flush=True)
                return result
            if args.command == "scan":
                if bool(args.demo) == bool(args.file):
                    raise SystemExit("Choose exactly one of --demo or --file")
                if args.file:
                    with open(args.file, "rb") as f:
                        msg = parse_email(f.read(c.max_message_bytes+1), c.max_message_bytes)
                else:
                    msg = demo_messages()[args.demo-1]
                if run(msg)["status"] != "completed":
                    raise SystemExit(2)
            else:
                if not c.queue_since and not args.entire_folder:
                    raise SystemExit("Set queue_since or pass --entire-folder to authorize the initial scan scope")
                with Mailbox(c).connect(readonly=True):
                    pass
                service=QueueService(c,store)
                store.pause(False)
                service.start()
                print("Persistent queue running. Ctrl+C pauses new work and requests cancellation.",flush=True)
                try:
                    while service.thread.is_alive():
                        service.stop_event.wait(1)
                except KeyboardInterrupt:
                    pass
                finally:
                    store.pause(True)
                    service.stop()
                    service.thread.join(timeout=c.timeout+5)
        return
    serve(c, getattr(args, "port", 8765), args.config)


def main():
    # Machine-readable JSON and Czech output must not depend on the Windows
    # redirected-console code page. MCP input already reads UTF-8 bytes.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    import signal
    import threading
    from .providers import ProviderError
    def terminate(*_):
        raise KeyboardInterrupt
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, terminate)
    try:
        _main()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (ValueError, RuntimeError, OSError, ProviderError) as exc:
        from .providers import ProviderError
        if isinstance(exc, (ValueError, RuntimeError, ProviderError)):
            message = str(exc)
        else:
            message = "Local operation failed. Check file permissions, available disk space, network configuration and whether the port is already in use."
        raise SystemExit("Mail Sentinel: " + message) from None
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    main()

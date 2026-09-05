"""Readiness checks without model requests or mailbox reads."""
import dataclasses
import os
import platform
import sqlite3
from pathlib import Path
from . import __version__
from .privacy import Privacy
from .tools import Registry, demo_messages, organization, redaction_terms
from .skills import load_skills


def readiness(config):
    checks = []
    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})
    add("runtime", "pass", "Python " + platform.python_version() + "; SQLite " + sqlite3.sqlite_version)
    add("model", "pass" if config.model else "fail", "Configured" if config.model else "Select a model in Settings > AI connection.")
    if config.external:
        add("external_consent", "pass" if config.allow_external else "fail", "Enabled" if config.allow_external else "Review privacy settings and enable external processing.")
        add("credential", "pass" if config.api_key else "fail", "Present" if config.api_key else "Set the configured API key environment variable.")
    try:
        org = organization(config)
        msg = demo_messages()[0]
        msg["source"] = "file"
        registry = Registry(msg, org, Privacy(redaction_terms(org, config)), dataclasses.replace(config))
        load_skills(config, registry.tools)
        add("extensions", "pass", "Plugin registrations, query definitions and enabled skills loaded; external services not contacted.")
        missing = sorted({key for tool in registry.catalog.values() if tool.check and registry.mode(tool.name) == "required" for key in tool.reference_keys if not org.get(key)})
        if missing:
            add("reference_data", "fail", "Required checks lack local records: " + ", ".join(missing) + ". Configure evidence sources or adjust check modes.")
    except Exception:
        add("extensions", "fail", "Cannot load organization data, plugins, query definitions or skills. Check their configuration and installed dependencies.")
    if config.imap_host:
        credential = config.imap_token_env if config.imap_auth == "oauth2" else config.imap_password_env
        add("mailbox_credentials", "pass" if config.imap_user and os.environ.get(credential) else "fail", "Present; connection not tested" if config.imap_user and os.environ.get(credential) else "Set the mailbox user and configured credential environment variable.")
    else:
        add("mailbox", "info", "Not configured. Demo and EML input remain available.")
    add("live_acceptance", "info", "Run doctor for a real tool-call test, then analyze representative messages. Local checks do not establish detection accuracy.")
    return {"version": __version__, "ready": not any(c["status"] == "fail" for c in checks), "checks": checks}


def backup_database(directory, destination):
    """Consistent SQLite snapshot; never overwrite an existing destination."""
    source = Path(directory).resolve() / "reports.sqlite3"
    if not source.is_file():
        raise ValueError("No report database exists in the configured data directory")
    target = Path(destination).resolve()
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(target) as dest:
                src.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
    except BaseException:
        if "src" in locals(): src.close()
        if "dest" in locals(): dest.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        # sqlite connection context managers commit but do not close handles.
        if "src" in locals(): src.close()
        if "dest" in locals(): dest.close()
    return target

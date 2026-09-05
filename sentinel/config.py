"""Administrator-owned configuration. Secrets come from environment variables."""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass
class Config:
    provider: str = "local"
    model: str = ""
    base_url: str = ""
    api_key_env: str = "SENTINEL_API_KEY"
    language: str = "en"
    privacy_mode: str = "redacted_text"
    allow_external: bool = False
    max_steps: int = 12
    timeout: int = 45
    max_seconds: int = 180
    max_output_tokens: int = 1400
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password_env: str = "SENTINEL_IMAP_PASSWORD"
    imap_folder: str = "AI-review"
    quarantine_folder: str = "AI-quarantine"
    allow_quarantine: bool = False
    max_message_bytes: int = 1_000_000
    max_messages: int = 20
    poll_seconds: int = 60
    retention_days: int = 30
    data_dir: str = ".sentinel"
    organization_file: str = ""
    plugins: list[str] = field(default_factory=list)
    redaction_terms: list[str] = field(default_factory=list)

    check_modes: dict = field(default_factory=dict)
    organization_rules: str = ""
    data_sources_file: str = ""

    queue_workers: int = 1
    queue_per_hour: int = 60
    queue_attempts: int = 3
    queue_since: str = ""
    daily_model_calls: int = 1000
    max_input_bytes: int = 500000
    imap_auth: str = "password"
    imap_token_env: str = "SENTINEL_IMAP_ACCESS_TOKEN"
    skills_dir: str = "skills"
    enabled_skills: list[str] = field(default_factory=list)
    enable_specialists: bool = False

    def validate(self):
        from datetime import date
        from dataclasses import fields
        defaults = Config()
        for setting in fields(self):
            value, default = getattr(self, setting.name), getattr(defaults, setting.name)
            if type(value) is not type(default):
                raise ValueError("Invalid type for setting: " + setting.name)
        if len(self.redaction_terms) > 1000 or any(not isinstance(x, str) or not x.strip() or len(x) > 1000 for x in self.redaction_terms):
            raise ValueError("Invalid redaction terms")
        if not isinstance(self.enabled_skills,list) or len(self.enabled_skills)>10 or any(not isinstance(x,str) for x in self.enabled_skills):
            raise ValueError("Invalid enabled skills")
        for key in ("enable_specialists","allow_external","allow_quarantine"):
            if type(getattr(self,key)) is not bool:
                raise ValueError("Invalid boolean setting")
        if not isinstance(self.check_modes, dict):
            raise ValueError("Invalid check rules")
        import re
        if len(self.check_modes)>100 or any(not isinstance(k,str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}",k) or v not in {"required","auto","off","conditional"} for k,v in self.check_modes.items()):
            raise ValueError("Invalid check rules")
        if self.check_modes.get("inspect_message","required")!="required":
            raise ValueError("Message inspection must remain required")
        if not isinstance(self.organization_rules,str) or len(self.organization_rules)>16000:
            raise ValueError("Organization rules exceed 16000 characters")
        if not isinstance(self.plugins,list) or len(self.plugins)>30 or any(not isinstance(m,str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*",m) for m in self.plugins):
            raise ValueError("Invalid plugin modules")
        if not isinstance(self.data_sources_file,str) or len(self.data_sources_file)>4000:
            raise ValueError("Invalid data source configuration path")
        if not 1 <= self.queue_workers <= 8 or not 1 <= self.queue_per_hour <= 10000 or not 1 <= self.queue_attempts <= 10:
            raise ValueError("Invalid queue limits")
        if not 1 <= self.daily_model_calls <= 100000 or not 10000 <= self.max_input_bytes <= 5000000:
            raise ValueError("Invalid model budget")
        if self.queue_since:
            date.fromisoformat(self.queue_since)
        if self.imap_auth not in {"password", "oauth2"}:
            raise ValueError("Unsupported IMAP authentication")

        if self.provider not in {"openai", "anthropic", "gemini", "local", "compatible"}:
            raise ValueError("Unsupported provider")
        if self.language not in {"en", "cs"} or self.privacy_mode not in {"evidence_only", "redacted_text"}:
            raise ValueError("Invalid language or privacy mode")
        if not 2 <= self.max_steps <= 30 or not 1 <= self.max_messages <= 100:
            raise ValueError("Invalid step or message limit")
        if not 5 <= self.timeout <= 120 or not 10 <= self.max_seconds <= 600:
            raise ValueError("Invalid time limit")
        if not 256 <= self.max_output_tokens <= 4096:
            raise ValueError("Invalid output token limit")
        if not 1024 <= self.max_message_bytes <= 10_000_000:
            raise ValueError("Invalid message size limit")
        if not 15 <= self.poll_seconds <= 86400 or not 1 <= self.retention_days <= 3650:
            raise ValueError("Invalid polling or retention limit")
        if not 1 <= self.imap_port <= 65535:
            raise ValueError("Invalid IMAP port")
        for folder in (self.imap_folder, self.quarantine_folder):
            if not folder or any(ord(c) < 32 for c in folder) or '"' in folder or '\\' in folder:
                raise ValueError("Unsupported IMAP folder name")
        if self.provider == "local":
            u = urlsplit(self.endpoint)
            if u.scheme not in {"http", "https"} or u.hostname not in {"localhost", "127.0.0.1", "::1"} or u.username or u.password or u.query or u.fragment:
                raise ValueError("Local provider must use a loopback endpoint")
        elif self.provider == "compatible":
            u = urlsplit(self.base_url)
            if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError("Custom provider requires a plain HTTPS base URL")
        elif self.base_url:
            raise ValueError("Custom endpoints are supported only for the loopback local provider")
        return self

    @property
    def external(self):
        return self.provider in {"openai", "anthropic", "gemini", "compatible"}

    @property
    def endpoint(self):
        return self.base_url or {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com/v1", "gemini": "https://generativelanguage.googleapis.com/v1beta", "local": "http://127.0.0.1:1234/v1"}[self.provider]

    @property
    def api_key(self):
        return os.environ.get(self.api_key_env, "")


def load_config(path="sentinel.toml"):
    p = Path(path)
    values = tomllib.loads(p.read_text("utf-8")) if p.exists() else {}
    from dataclasses import fields
    unknown = set(values) - {f.name for f in fields(Config)}
    if unknown:
        raise ValueError("Unknown configuration setting: " + ", ".join(sorted(unknown)))
    c = Config(**values)
    if p.exists():
        root = p.resolve().parent
        c.data_dir = str(root / c.data_dir)
        c.skills_dir = str(root / c.skills_dir)
        if c.data_sources_file:
            c.data_sources_file = str(root / c.data_sources_file)
        if c.organization_file:
            c.organization_file = str(root / c.organization_file)
    return c.validate()


def encode_toml(value):
    import json
    if isinstance(value, dict):
        return "{ " + ", ".join(json.dumps(k) + " = " + encode_toml(v) for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(encode_toml(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)

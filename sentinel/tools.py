"""Read-only tools. Model-selected operations never receive database or IMAP credentials."""
import hashlib
import importlib
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlsplit
from .mail import parse_email


def demo_dataset():
    return json.loads(Path(__file__).with_name("demo_data.json").read_text("utf-8"))


def demo_messages():
    messages = []
    for entry in demo_dataset()["messages"]:
        m = EmailMessage()
        m["From"], m["Subject"], m["To"] = entry["sender"], entry["subject"], "it@example.org"
        m.set_content(entry["body"])
        if entry.get("attachment_name"):
            m.add_attachment(b"Synthetic attachment. No executable content.",maintype="text",subtype="plain",filename=entry["attachment_name"])
        msg = parse_email(m.as_bytes())
        msg["source"] = "demo"
        messages.append(msg)
    return messages


def organization(config, demo=False):
    if demo:
        return demo_dataset()
    if config.organization_file:
        path = Path(config.organization_file)
        if path.stat().st_size > 2_000_000:
            raise ValueError("Organization file exceeds 2 MB")
        data = json.loads(path.read_text("utf-8"))
        if data.get("demo"):
            raise ValueError("Demo registry cannot be used for real email")
        return data
    return {"vendors": [], "orders": [], "policies": [], "indicators": []}


def redaction_terms(org, config):
    terms = list(config.redaction_terms)
    for vendor in org.get("vendors", []):
        terms += [vendor.get("name", "")] + vendor.get("contacts", []) + vendor.get("domains", [])
    return terms


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: object
    title: dict = field(default_factory=dict)
    default_mode: str = "auto"
    applicability: str = "Use when relevant to the content or requested action."
    reference_keys: list = field(default_factory=list)
    available: object = None
    blockers: object = None
    preview: bool = True
    check: bool = True
    locked: bool = False
    version: str = "1"
    real_data: bool = False


class Registry:
    def __init__(self, message, org, privacy, config):
        self.message, self.org, self.privacy, self.c = message, org, privacy, config
        display_name = parseaddr(message.get("sender", ""))[0]
        if len(display_name) >= 3:
            self.privacy.terms = sorted(set(self.privacy.terms + [display_name]), key=len, reverse=True)
        self.tools, self.catalog = {}, {}
        self.provenance=[]
        for module in ["sentinel.builtin_checks", *config.plugins]:
            loaded=importlib.import_module(module)
            loaded.register(self)
            path=getattr(loaded,'__file__',None)
            self.provenance.append({'module':module,'entry_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None})
        from .data_sources import register_sources
        register_sources(self)
        unknown=set(config.check_modes)-set(self.catalog)
        if unknown: raise ValueError("Check rules refer to unavailable plugins: "+", ".join(sorted(unknown)))
        self.c.check_modes={n:self.mode(n) for n,t in self.catalog.items() if t.check}
        conditional=[n for n,t in self.catalog.items() if t.check and self.mode(n)=="conditional"]
        if conditional:
            self.add(Tool("assess_applicability","Record your semantic assessment for conditional checks in any language. Classify EVERY conditional check exactly once across the three arrays, including checks already performed: " + ", ".join(conditional) + ". Explain your reasoning. This is a model assessment, not independently verified evidence.",schema({"applicable":{"type":"array","items":{"type":"string"}},"not_applicable":{"type":"array","items":{"type":"string"}},"uncertain":{"type":"array","items":{"type":"string"}},"reason":{"type":"string"}},["applicable","not_applicable","uncertain","reason"]),self.assess_applicability,check=False,preview=False))

    def mode(self,name):
        tool=self.catalog[name]
        if tool.real_data and self.message.get("source")=="demo":return "off"
        return "required" if tool.locked else self.c.check_modes.get(name,tool.default_mode)

    def add(self,tool):
        if tool.name in self.catalog or tool.name=="finish_investigation" or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}",tool.name):
            raise ValueError("Duplicate or invalid tool")
        if tool.default_mode not in {"required","conditional","auto","off"}:
            raise ValueError("Invalid plugin check mode")
        if not isinstance(tool.title,dict) or any(k not in {'en','cs'} or not isinstance(v,str) for k,v in tool.title.items()):raise ValueError("Invalid localized tool title")
        if not isinstance(tool.applicability,str) or not isinstance(tool.reference_keys,list):raise ValueError("Invalid check metadata")
        self.catalog[tool.name]=tool
        if not tool.check or self.mode(tool.name)!="off":self.tools[tool.name]=tool

    def check_catalog(self):
        return [{"name":n,"title":t.title,"description":t.description,"mode":self.mode(n),"locked":t.locked,
                 "applicability":t.applicability,"reference_keys":t.reference_keys,"version":t.version}
                for n,t in self.catalog.items() if t.check]

    def assess_applicability(self,applicable,not_applicable,uncertain,reason):
        expected={n for n,t in self.catalog.items() if t.check and self.mode(n)=="conditional"}
        flattened=applicable+not_applicable+uncertain
        if set(flattened)!=expected or len(flattened)!=len(expected) or not reason.strip():
            raise ValueError("Classify each conditional check exactly once and explain the assessment")
        # The model cannot waive a semantic check without access to message text.
        if not_applicable and (self.c.privacy_mode=="evidence_only" or self.message.get("body_truncated")):
            uncertain=uncertain+not_applicable;not_applicable=[]
        return {"applicable":applicable,"not_applicable":not_applicable,"uncertain":uncertain,"reason":reason,
                "assessment_source":"model","independently_verified":False}

    def definitions(self):
        return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in self.tools.values()]

    def execute(self, name, arguments):
        if name not in self.tools:
            raise PermissionError("Tool is not registered or permitted")
        tool = self.tools[name]
        validate_arguments(arguments, tool.parameters)
        # This is the single outbound privacy boundary, including plugin responses.
        raw=tool.run(**arguments)
        if not isinstance(raw,dict): raise ValueError("Tool must return an object")
        # Completion metadata is computed by the registered plugin, never model arguments.
        blockers=tool.blockers(raw) if tool.blockers else []
        if not isinstance(blockers,list) or not all(isinstance(item,str) for item in blockers):raise ValueError("Invalid plugin blockers")
        raw["_check"]={"available":bool(tool.available(raw)) if tool.available else bool(raw.get("available",True)) and not bool(raw.get("error")),"blockers":blockers}
        result = self.privacy.protect(raw)
        if len(json.dumps(result)) > 20000:
            raise ValueError("Tool response exceeds limit")
        return result


def validate_arguments(args, spec):
    if not isinstance(args, dict) or set(args) - set(spec.get("properties", {})) or set(spec.get("required", [])) - set(args):
        raise ValueError("Invalid tool arguments")
    for key, value in args.items():
        rule = spec["properties"][key]
        types = {"string": str, "array": list, "integer": int, "boolean": bool, "object": dict}
        if rule.get("type") in types and type(value) is not types[rule["type"]]:
            raise ValueError("Invalid tool argument type")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError("Invalid tool argument value")
        if isinstance(value, str) and len(value) > 4000:
            raise ValueError("Tool argument too long")
        if isinstance(value, list) and (len(value) > 30 or not all(isinstance(x, str) and len(x) <= 4000 for x in value)):
            raise ValueError("Invalid tool argument list")

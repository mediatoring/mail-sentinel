"""Read-only tools. Model-selected operations never receive database or IMAP credentials."""
import hashlib
import importlib
import json
import re
from dataclasses import dataclass, field, replace
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
        if not isinstance(data, dict):
            raise ValueError("Organization file must contain an object")
        if data.get("demo"):
            raise ValueError("Demo registry cannot be used for real email")
        shapes = {'vendors': {'id':str, 'name':str, 'domains':list, 'accounts':list, 'contacts':list},
                  'orders': {'id':str, 'vendor_id':str, 'amount':str, 'currency':str},
                  'policies': {'id':str, 'title':str, 'text':str},
                  'indicators': {'domain':str, 'status':str, 'source':str}}
        for section, fields in shapes.items():
            rows = data.get(section, [])
            if not isinstance(rows, list):
                raise ValueError('Invalid organization section: ' + section)
            for row in rows:
                if not isinstance(row, dict) or any(type(row.get(k)) is not kind for k, kind in fields.items()):
                    raise ValueError('Missing or invalid organization fields in: ' + section)
                if any(not all(isinstance(v,str) for v in row[k]) for k,kind in fields.items() if kind is list):
                    raise ValueError('Invalid organization list in: ' + section)
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
        self.message, self.org, self.privacy = message, org, privacy
        self.c = replace(config, check_modes=dict(config.check_modes))
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
            self.add(Tool("assess_applicability","Record your semantic assessment for conditional checks in any language. Classify EVERY conditional check exactly once across the three arrays, including checks already performed: " + ", ".join(conditional) + ". Explain your reasoning. This is a model assessment, not independently verified evidence.",schema({"applicable":{"type":"array","items":{"type":"string","enum":conditional}},"not_applicable":{"type":"array","items":{"type":"string","enum":conditional}},"uncertain":{"type":"array","items":{"type":"string","enum":conditional}},"reason":{"type":"string"}},["applicable","not_applicable","uncertain","reason"]),self.assess_applicability,check=False,preview=False))

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
        if not_applicable and (self.c.privacy_mode=="evidence_only" or self.message.get("body_truncated") or self.message.get("body_unavailable")):
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
        available = bool(tool.available(raw)) if tool.available else bool(raw.get("available",True)) and not bool(raw.get("error"))
        result = self.privacy.protect({k:v for k,v in raw.items() if k != '_check'})
        if name == 'assess_applicability':
            # Validated catalog IDs are protocol data, never redaction terms.
            result = {**{k:raw[k] for k in ('applicable','not_applicable','uncertain','assessment_source','independently_verified')},
                      'reason':self.privacy.text(raw['reason'])}
        result['_check'] = {'available':available, 'blockers':self.privacy.protect(blockers)}
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > 20000:
            raise ValueError("Tool response exceeds limit")
        return result

    def evidence(self, ident, name, arguments, status, output):
        """Preserve the host envelope around already protected tool output."""
        return {'id':ident, 'tool':name if name in self.catalog else self.privacy.text(name),
                'arguments':self.privacy.protect(arguments), 'status':status, 'observation':output}


def validate_arguments(args, spec):
    import math
    def validate(value, rule, depth=0):
        if depth > 8:
            raise ValueError('Tool arguments nested too deeply')
        types = {'string':(str,), 'array':(list,), 'integer':(int,), 'number':(int,float), 'boolean':(bool,), 'object':(dict,)}
        if rule.get('type') not in types or type(value) not in types[rule['type']]:
            raise ValueError('Invalid tool argument type')
        if 'enum' in rule and value not in rule['enum']:
            raise ValueError('Invalid tool argument value')
        if isinstance(value, str) and len(value) > min(4000,rule.get('maxLength',4000)):
            raise ValueError('Tool argument too long')
        if type(value) in (int,float):
            if not math.isfinite(value) or value < rule.get('minimum',-math.inf) or value > rule.get('maximum',math.inf):
                raise ValueError('Invalid tool argument number')
        if isinstance(value, list):
            if len(value) > min(100,rule.get('maxItems',100)):
                raise ValueError('Invalid tool argument list')
            for item in value:
                validate(item,rule.get('items',{'type':'string'}),depth+1)
        if isinstance(value, dict):
            properties=rule.get('properties',{})
            if len(value)>100 or set(value)-set(properties) or set(rule.get('required',[]))-set(value):
                raise ValueError('Invalid tool arguments')
            for key,item in value.items():
                validate(item,properties[key],depth+1)
    validate(args,spec)
    if len(json.dumps(args,ensure_ascii=False,allow_nan=False).encode())>32000:
        raise ValueError('Tool arguments exceed total size limit')

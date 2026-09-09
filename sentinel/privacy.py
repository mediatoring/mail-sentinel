"""Best-effort pseudonymization, not a guarantee of anonymization."""
import json
import re

PATTERNS = [
    ("URL", re.compile(r"https?://[^\s<>\"']+", re.I)),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    ("ACCOUNT", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")),
    ("ACCOUNT", re.compile(r"\b(?:\d{1,6}-)?\d{2,10}/\d{4}\b")),
    ("NUMBER", re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")),
]


class Privacy:
    def __init__(self, terms=()):
        self.mapping = {}
        self.original_values = {}
        self.counts = {}
        self.terms = sorted({str(t) for t in terms if len(str(t)) >= 3}, key=len, reverse=True)

    def token(self, kind, value):
        key = value.casefold()
        if key not in self.mapping:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            self.mapping[key] = f"[{kind}_{self.counts[kind]}]"
            self.original_values[self.mapping[key]] = value
        return self.mapping[key]

    def text(self, value):
        text = str(value)
        for kind, pattern in PATTERNS:
            text = pattern.sub(lambda m: self.token(kind, m[0]), text)
        for term in self.terms:
            # Tokens are opaque references, including across repeated passes.
            pieces = re.split(r'(\[[A-Z]+_\d+\])', text)
            text = ''.join(piece if i % 2 else re.sub(re.escape(term), lambda m: self.token("ENTITY", m[0]), piece, flags=re.I)
                           for i, piece in enumerate(pieces))
        return text

    def protect(self, obj):
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, list):
            return [self.protect(v) for v in obj]
        if isinstance(obj, dict):
            return {self.text(k): self.protect(v) for k, v in obj.items()}
        return obj

    def fit(self, result, limit):
        """Shrink a protected body until the result fits its transport limit, and say that it was shortened."""
        body = result.get("body")
        if not isinstance(body, str):
            return result
        while body and len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > limit:
            keep = int(len(body) * 0.8)
            # A pseudonymization token is an opaque reference; never cut one in half.
            opened = body.rfind("[", 0, keep)
            if opened > body.rfind("]", 0, keep):
                keep = opened
            body = body[:max(0, keep)]
            result = {**result, "body": body, "body_truncated": True}
        return result

    def message(self, msg, mode, limit=None):
        if mode == "redacted_text":
            result = {k: self.protect(v) for k, v in msg.items() if k not in {"imap_ref", "id"}}
            return self.fit(result, limit) if limit else result
        return {"source": msg["source"], "attachment_count": len(msg["attachments"]),
                "url_count": len(msg["urls"]), "body_truncated": msg.get("body_truncated", False),
                "body_unavailable": msg.get("body_unavailable", False),
                "content_shared": False,
                "hint": "Use the local verification tools. Email text is withheld in evidence-only mode."}

"""Native tool-call adapters. No simulated or fallback model results."""
import json
import urllib.error
import urllib.request
from urllib.parse import quote


class ProviderError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Provider redirect blocked")


class Provider:
    def __init__(self, config):
        self.c = config

    def request(self, url, payload, headers):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers})
        # Do not inherit ambient proxies that could route local email data externally.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(req, timeout=self.c.timeout) as r:
                body = r.read(1_000_001)
                if len(body) > 1_000_000:
                    raise ProviderError("Provider response exceeds limit")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            raise ProviderError(f"Provider HTTP {e.code}; check model, key and quota") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            raise ProviderError("Provider unavailable or invalid response; no verdict produced") from None

    def decide(self, system, context, definitions):
        if not self.c.model:
            raise ProviderError("Configure a real AI model before analysis")
        if self.c.external and (not self.c.allow_external or not self.c.api_key):
            raise ProviderError("External provider requires an API key and explicit external-processing opt-in")
        text = json.dumps(context, ensure_ascii=False)
        base = self.c.endpoint.rstrip("/")
        if self.c.provider == "anthropic":
            payload = {"model": self.c.model, "system": system, "messages": [{"role": "user", "content": text}],
                       "max_tokens": self.c.max_output_tokens,
                       "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in definitions],
                       "tool_choice": {"type": "any", "disable_parallel_tool_use": True}}
            result = self.request(base + "/messages", payload, {"x-api-key": self.c.api_key, "anthropic-version": "2023-06-01"})
            calls = [{"name": b["name"], "arguments": b["input"]} for b in result.get("content", []) if b.get("type") == "tool_use"]
        elif self.c.provider == "gemini":
            def convert(x):
                if isinstance(x, dict):
                    return {k: convert(v) for k, v in x.items() if k != "additionalProperties"}
                return [convert(v) for v in x] if isinstance(x, list) else x
            payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": text}]}],
                       "tools": [{"functionDeclarations": convert(definitions)}],
                       "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
                       "generationConfig": {"maxOutputTokens": self.c.max_output_tokens}}
            result = self.request(base + "/models/" + quote(self.c.model, safe="") + ":generateContent", payload, {"x-goog-api-key": self.c.api_key})
            candidates = result.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            calls = [{"name": p["functionCall"]["name"], "arguments": p["functionCall"].get("args", {})} for p in parts if "functionCall" in p]
        else:
            payload = {"model": self.c.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
                       "tools": [{"type": "function", "function": t} for t in definitions], "tool_choice": "required",
                       "parallel_tool_calls": False}
            payload["max_completion_tokens" if self.c.provider == "openai" else "max_tokens"] = self.c.max_output_tokens
            headers = {"Authorization": "Bearer " + self.c.api_key} if self.c.api_key and self.c.external else {}
            result = self.request(base + "/chat/completions", payload, headers)
            choices = result.get("choices", [])
            raw = choices[0].get("message", {}).get("tool_calls", []) if choices else []
            try:
                calls = [{"name": t["function"]["name"], "arguments": json.loads(t["function"]["arguments"])} for t in raw]
            except (KeyError, TypeError, json.JSONDecodeError):
                raise ProviderError("Invalid native tool call") from None
        if len(calls) != 1:
            raise ProviderError("Model must return exactly one native tool call; choose a tool-capable model")
        return calls[0]



    def models(self):
        if self.c.external and (not self.c.allow_external or not self.c.api_key):
            raise ProviderError("External provider requires an API key and explicit external-processing opt-in")
        headers={}
        if self.c.provider=="anthropic":
            headers={"x-api-key":self.c.api_key,"anthropic-version":"2023-06-01"}
        elif self.c.provider=="gemini":
            headers={"x-goog-api-key":self.c.api_key}
        elif self.c.external:
            headers={"Authorization":"Bearer "+self.c.api_key}
        data=self.request(self.c.endpoint.rstrip("/")+"/models",None,headers)
        entries=data.get("models",[]) if self.c.provider=="gemini" else data.get("data",[])
        names=[]
        for entry in entries[:1000]:
            name=entry.get("name","").removeprefix("models/") if self.c.provider=="gemini" else entry.get("id","")
            if isinstance(name,str) and 0<len(name)<300:
                names.append(name)
        return sorted(set(names))

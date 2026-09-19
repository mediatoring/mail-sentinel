"""TypeSafe AI System One decision model (Jev) as a bounded evidence tool.

Jev answers typed questions (yes/no "noul", choice, score) about one piece of
state and returns calibrated probabilities. It generates no text and selects no
tools, so it never replaces the investigating model. Its answers are recorded as
evidence under the existing privacy boundary: the model receives only the
pseudonymized message the investigating model would see, and its output passes
through Registry.execute like every other check.
"""
import math
from .providers import Provider, ProviderError
from .tools import Tool, schema

TOOL_NAME = "evaluate_decision_model"
SYSTEM_ONE_PATH = "/v1/systemone"
MODELS_PATH = "/v1/models"
MAX_QUESTIONS = 12
STATE_LIMIT = 24000
FRAUD_BLOCK_THRESHOLD = 0.9

# Host-owned question catalog. Email content never adds, removes or rewords a question.
DECISIONS = {
    "fraud_attempt": {"type": "noul",
        "instructions": "This message is a phishing, fraud or social-engineering attempt aimed at the recipient.",
        "criteria": {"true": "A deceptive request for money, credentials, data or an action that benefits an attacker.",
                     "false": "Ordinary correspondence without deceptive intent."}},
    "request_type": {"type": "choice", "instructions": "What does the message ask the recipient to do?",
        "criteria": {"payment_or_bank_change": "Pay, change bank details, or process an invoice or transfer.",
                     "credentials_or_login": "Sign in, confirm an account, or provide passwords or codes.",
                     "sensitive_data_or_documents": "Send personal, organizational or confidential data or documents.",
                     "open_link_or_attachment": "Open a link, download a file or install something.",
                     "reply_or_call": "Reply, call back or continue a conversation.",
                     "no_action": "Informational content with no requested action."}},
    "pressure": {"type": "score", "instructions": "How much urgency, pressure or secrecy does the message apply?",
        "criteria": ["No urgency or pressure.", "Mild time pressure or a routine reminder.",
                     "Strong urgency, threats, penalties or requests for secrecy."]},
    "impersonation": {"type": "noul",
        "instructions": "The sender presents themselves as an executive, authority, bank, vendor or service provider without anything in the message establishing that identity."},
    "ai_directed_instructions": {"type": "noul",
        "instructions": "The message contains instructions addressed to an AI assistant, automated reviewer or software rather than to the human recipient."},
}
APPLICABILITY_PREFIX = "applies_"


def _probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ProviderError("Decision model returned an invalid probability")
    return round(float(value), 3)


def parse_answers(result, questions):
    """Accept only answers whose type and labels match the questions this host asked."""
    if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
        raise ProviderError("Decision model returned an invalid response")
    answers = {}
    for name, question in questions.items():
        raw = result["answers"].get(name)
        if not isinstance(raw, dict) or raw.get("type") != question["type"]:
            raise ProviderError("Decision model omitted or mistyped an answer")
        if question["type"] == "noul":
            answers[name] = {"type": "noul", "probability": _probability(raw.get("noul"))}
        elif question["type"] == "choice":
            labels = list(question["criteria"])
            distribution = raw.get("probabilities")
            if raw.get("choice") not in labels or not isinstance(distribution, dict) or set(distribution) - set(labels):
                raise ProviderError("Decision model returned an unknown choice")
            answers[name] = {"type": "choice", "choice": raw["choice"], "confidence": _probability(raw.get("confidence")),
                             "probabilities": {label: _probability(distribution[label]) for label in labels if label in distribution}}
        else:
            levels = [str(i) for i in range(len(question["criteria"]))]
            distribution = raw.get("probabilities")
            score = raw.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= len(levels) - 1:
                raise ProviderError("Decision model returned an invalid score")
            if not isinstance(distribution, dict) or set(distribution) - set(levels):
                raise ProviderError("Decision model returned an unknown score level")
            answers[name] = {"type": "score", "score": round(float(score), 2), "confidence": _probability(raw.get("confidence")),
                             "probabilities": {level: _probability(distribution[level]) for level in levels if level in distribution},
                             # The legend comes from the host's own rubric, never from the response.
                             "legend": dict(zip(levels, question["criteria"]))}
    model = result.get("model")
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    tokens = usage.get("input_tokens")
    return {"answers": answers, "model": model if isinstance(model, str) and 0 < len(model) <= 200 else "",
            "input_tokens": tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and 0 <= tokens <= 10**9 else None}


class DecisionModel:
    """Bounded HTTPS client: same timeout, size limit, redirect and proxy policy as model providers."""

    def __init__(self, config, api_key=None):
        self.c = config
        self.key = config.typesafe_api_key if api_key is None else api_key
        self.transport = Provider(config)

    def _headers(self):
        if not self.c.typesafe_model:
            raise ProviderError("Configure a decision model before use")
        if not self.c.allow_external or not self.key:
            raise ProviderError("The decision model requires a TypeSafe API key and explicit external-processing opt-in")
        return {"Authorization": "Bearer " + self.key}

    def ask(self, state, questions):
        headers = self._headers()
        if not questions or len(questions) > MAX_QUESTIONS:
            raise ValueError("Invalid decision question set")
        payload = {"model": self.c.typesafe_model, "state": state, "questions": questions}
        result = self.transport.request(self.c.typesafe_endpoint + SYSTEM_ONE_PATH, payload, headers)
        return parse_answers(result, questions)

    def verify(self):
        """Real request without message data; proves credentials, model name and the typed protocol."""
        question = {"connection_ok": {"type": "noul", "instructions": "The state is a connection test.",
                                      "criteria": {"true": "The state says it is a connection test.", "false": "The state says something else."}}}
        return self.ask({"connection_test": True}, question)

    def models(self):
        data = self.transport.request(self.c.typesafe_endpoint + MODELS_PATH, None, self._headers())
        names = []
        for entry in (data.get("models", []) if isinstance(data, dict) else [])[:1000]:
            name = entry.get("name", "") if isinstance(entry, dict) else ""
            if isinstance(name, str) and 0 < len(name) < 300:
                names.append(name)
        return sorted(set(names))


def questions_for(registry):
    questions = dict(DECISIONS)
    for name, tool in registry.catalog.items():
        if len(questions) >= MAX_QUESTIONS:
            break
        if tool.check and name != TOOL_NAME and registry.mode(name) == "conditional":
            questions[APPLICABILITY_PREFIX + name] = {"type": "noul",
                "instructions": "Applicability of the check '" + name + "': " + tool.applicability,
                "criteria": {"true": "The check applies to what this message requests or discusses.",
                             "false": "The check does not apply to this message."}}
    return questions


def register(registry):
    config = registry.c
    if not config.typesafe_model:
        return

    def evaluate():
        if config.privacy_mode != "redacted_text":
            return {"available": False, "reason": "text_withheld",
                    "note": "Evidence-only mode withholds the message text; nothing was sent to the decision model."}
        if not config.allow_external or not config.typesafe_api_key:
            return {"available": False, "reason": "decision_model_not_authorized",
                    "note": "The decision model needs a TypeSafe API key and external-processing opt-in; nothing was sent."}
        protected = registry.privacy.message(registry.message, "redacted_text", limit=STATE_LIMIT)
        state = {key: protected[key] for key in ("subject", "sender", "reply_to", "body", "urls") if key in protected}
        state["attachments"] = [{"filename": a.get("filename", ""), "mime": a.get("mime", "")} for a in protected.get("attachments", [])]
        questions = questions_for(registry)
        try:
            answers = DecisionModel(config).ask(state, questions)
        except (ProviderError, ValueError) as exc:
            return {"available": False, "reason": "decision_model_unavailable",
                    "error_code": exc.code if isinstance(exc, ProviderError) else "provider_error",
                    "note": "The decision model could not be reached or rejected the request; no probabilities were recorded."}
        decisions = {name: value for name, value in answers["answers"].items() if name in DECISIONS}
        applicability = {name.removeprefix(APPLICABILITY_PREFIX): value["probability"]
                         for name, value in answers["answers"].items() if name.startswith(APPLICABILITY_PREFIX)}
        return {"available": True, "model": answers["model"], "decisions": decisions, "applicability_signals": applicability,
                "input_tokens": answers["input_tokens"], "scope": "pseudonymized_text",
                "body_truncated": bool(protected.get("body_truncated")),
                "note": "Calibrated estimates from a typed decision model over the pseudonymized message. Not independent verification of sender, links, attachments or records; pseudonymization tokens replaced addresses, URLs and known names."}

    def blockers(output):
        fraud = output.get("decisions", {}).get("fraud_attempt", {}).get("probability", 0)
        return ["Decision model rates the message as a likely fraud attempt."] if fraud >= FRAUD_BLOCK_THRESHOLD else []

    registry.add(Tool(TOOL_NAME,
        "Ask the configured TypeSafe decision model (Jev) fixed typed questions about the pseudonymized message: fraud likelihood, requested action, pressure, impersonation, AI-directed instructions and applicability of conditional checks. Returns calibrated probabilities, not verification.",
        schema(), evaluate, title={"en": "Decision model (TypeSafe Jev)", "cs": "Rozhodovací model (TypeSafe Jev)"},
        default_mode="auto", applicability="Typed probabilities help weigh message intent, pressure and the relevance of conditional checks.",
        available=lambda o: bool(o.get("available")), blockers=blockers, preview=False))

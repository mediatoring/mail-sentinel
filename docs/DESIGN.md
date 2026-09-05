# Design decisions

Mail Sentinel uses a small independent Python core and explicit tool contracts. Deterministic parsing/privacy/permissions surround a model-selected investigation loop. This keeps the learning objective visible without making a generic coding agent's shell and filesystem permissions part of the email threat surface.

Reviewed design references:

- https://github.com/DiscoDaddy/agent-mail-guard — email preprocessing as a separate layer. Here indicators are extracted locally before redaction so evidence is not silently discarded.
- https://github.com/UTKARSHPANDEY0/phisguard — IMAP review, local history and scanner separation. Here the model chooses investigation steps rather than following a fixed scanner sequence.
- https://github.com/techjarves/OpenClaude-Portable — local launcher, independent provider configuration and local web interface. This release requires an existing Python runtime and does not bundle/download a coding engine or trim security prompts through a proxy.

These are architectural references, not incorporated code. No claims of equivalent feature coverage are made.

Protocol references consulted during implementation:

- https://developers.openai.com/api/docs/guides/function-calling
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- https://ai.google.dev/gemini-api/docs/function-calling
- https://lmstudio.ai/docs/developer/openai-compat/tools

The fresh-transcript adapter design avoids replaying provider-specific hidden state. Each model sees the goal, current privacy-filtered message, prior calls and observations, and the registry. The provider must select one native function. This adds repeated context tokens; step and output limits bound per-run work, but not monetary spend.

Version 0.4.0 adds durable ingestion queues, configurable checks, runtime skills, scoped specialists, IMAP OAuth access-token authentication and a single-message MCP adapter. See [the release acceptance table](RELEASE-0.4.0.md) for exact boundaries. Direct CLI subprocess providers, built-in OAuth issuance/refresh, native CSV editing and external malware/reputation scanner integrations remain outside this release.

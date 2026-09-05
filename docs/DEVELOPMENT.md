# Developer guide

Start with [AGENTS.md](../AGENTS.md) and [CONTRIBUTING.md](../CONTRIBUTING.md). The repository includes entry points for Codex (`AGENTS.md`), Claude Code (`CLAUDE.md`) and Cursor (`.cursor/rules/project.mdc`). If an assistant does not load them automatically, explicitly ask it to read `AGENTS.md` first.

## Code map

| Responsibility | Implementation |
| --- | --- |
| Agent loop, completion and evidence references | `sentinel/agent.py` |
| Native model calls and response parsing | `sentinel/providers.py` |
| Tool registration, validation and execution | `sentinel/tools.py` |
| Outbound pseudonymization | `sentinel/privacy.py` |
| IMAP and message parsing | `sentinel/mail.py` |
| Reports and approval tokens | `sentinel/store.py` |
| Local HTTP API and background jobs | `sentinel/server.py` |
| Settings and CLI | `sentinel/config.py`, `sentinel/__main__.py` |
| English/Czech interface | `sentinel/static/index.html`, `sentinel/static/app.js` |

Queue storage and workers: `sentinel/queue.py`; shared budgets: `sentinel/budget.py`; completion: `sentinel/reports.py`; check policy: `sentinel/rules.py`; injection indicators: `sentinel/injection.py`; skill loader: `sentinel/skills.py`; MCP transport: `sentinel/mcp.py`.

## Extension recipes

- [Tools and organization data](EXTENDING.md): register a read-only Python tool, activate it and verify its privacy boundary.
- [Harness and providers](HARNESS.md): follow one investigation and replace the model transport without bypassing host controls.
- [Skills and subagents](SKILLS-AND-SUBAGENTS.md): distinguish contributor instructions from runtime features and design those extensions against the current interfaces.
- [Validation record](VALIDATION.md): current verification and remaining live acceptance checks.

## Example task for a coding assistant

> Read AGENTS.md and docs/EXTENDING.md. Add a read-only tool that reports missing vendor registry fields using only the current Registry.org. Return vendor IDs and missing field names, without contact data. Register it through the existing plugin interface. Add tests for the result and privacy boundary, document activation, and run the relevant checks. Do not add network access or change the agent's action permissions.

Configuration belongs in `sentinel.toml` and administrator-controlled environment variables. Keep credentials, real emails and generated local state out of commits and release archives.

See [check rules](CHECKS.md), [queue operations](QUEUE.md), [MCP](MCP.md) and [release acceptance](RELEASE-1.0.md).

Frontend DOM regression tests: install `jsdom` in your development environment and run `node tests/ui-flow.cjs`. `JSDOM_MODULE` may point to an existing installation. Runtime users do not need Node.js or jsdom.

Plugin metadata and completion: `Tool`, `Registry` in `tools.py`; bundled adapter implementation: `builtin_checks.py`; administrator SQL tools: `data_sources.py`; shared EN/CZ strings: `static/i18n.js`. The model, settings and completion reports consume the same check catalog. See [database sources](DATA-SOURCES.md).

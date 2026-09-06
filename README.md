# Mail Sentinel

**A local-first AI agent for investigating suspicious email.**

Mail Sentinel lets an actual language model choose verification tools, inspect their results and decide what to check next. It combines configured evidence tools, database queries and organization requirements, then produces an evidence-linked report. It is a reusable MIT-licensed Python application, with a local English/Czech interface and a terminal mode.

**Version 1.0.0rc1 — release candidate awaiting deployment acceptance.** This is not a certified mail gateway or a replacement for existing email security. The included tests verify application behavior and safety boundaries, not phishing detection accuracy.

## Start in minutes

Requires **Python 3.11+**. Extract the ZIP and run `START.bat` on Windows or `sh start.sh` on macOS/Linux. Open the complete local URL printed in the terminal, then configure AI in **Settings**. Mailbox credentials are optional for the demo messages.

[Step-by-step installation for Windows, macOS and Linux](docs/INSTALL.md) · [Český návod](docs/INSTALL.cs.md)

### Local AI: LM Studio or Ollama

Start your local model server and load a model that supports **native function/tool calls**. Configure:

```toml
provider = "local"
model = "your-loaded-model-identifier"
base_url = "http://127.0.0.1:1234/v1"
privacy_mode = "redacted_text"
```

For Ollama's OpenAI-compatible interface, use `http://127.0.0.1:11434/v1`. Compatibility depends on the selected model and server version. Run `doctor` before first use: it performs an actual inference and requires a valid native tool call. Being able to chat with a model is not enough.

### Cloud AI

Supported protocols: **OpenAI Chat Completions, Anthropic Messages, Gemini generateContent**, and configurable **OpenAI-compatible HTTPS providers** (e.g. OpenRouter or other compatible services). Providers and models can impose different quotas and costs; no free-tier promise is made.

```toml
provider = "openai" # anthropic, gemini, compatible
model = "your-provider-model-identifier"
allow_external = true
privacy_mode = "evidence_only"
# For provider = "compatible" only:
# base_url = "https://your-provider.example/v1"
```

Set `SENTINEL_API_KEY` in your environment. Interactive startup can also ask for the key using a hidden prompt and keep it in process memory. Do not put API keys in the repository. The browser never receives your API key or IMAP password. `allow_external` is an administrator setting; the web UI additionally requires consent per investigation.

The web UI and queue use API/local-server adapters. [The MCP adapter](docs/MCP.md) exposes single-message evidence tools and guarded completion to external clients such as Codex, Claude Code and Cursor, using the client's own model/login. Direct CLI subprocess providers and direct ChatGPT/Claude web-session authentication are not embedded in the web UI.


## What makes it agentic?

The host supplies a goal and a registry of native function tools. On every iteration, the model selects one tool and arguments. Python validates and executes the call, pseudonymizes the result, assigns an evidence ID, and sends the accumulated evidence back. The model may choose another tool or call `finish_investigation`. There is no hardcoded tool order.

Every provider request contains a fresh, bounded application transcript. Provider-specific hidden reasoning state is not replayed; tool observations are explicitly carried forward. Invalid tool calls, provider failures, invalid evidence references, or exhausted budgets produce **incomplete**, never a fabricated safe result.

Built-in tools:

| Tool | Scope |
|---|---|
| `inspect_prompt_injection` | Local indicators in subject, parsed body and attachment names; unknown attacks can be missed |
| `inspect_message` | Current message under the privacy policy, plus local heuristic signals |
| `verify_sender` | Sender/Reply-To comparison with approved vendor domains |
| `verify_payment` | Accounts, order IDs and basic amount/currency presence checks |
| `inspect_links` | URL structure and local indicators; no URL fetch |
| `inspect_attachments` | Metadata, hashes and extension signals; no execution/OCR/malware scan |
| `search_policy` | Paginated organization policies, interpreted semantically |
| `finish_investigation` | Evidence-linked result; optional quarantine proposal |

Adding Python tools is documented in [docs/EXTENDING.md](docs/EXTENDING.md). Plugins are administrator-installed trusted code, not downloaded by the model.

## Sample messages

Select one of the five built-in messages: a matching invoice, changed payment details, English/Czech prompt-injection attempts and a malicious instruction in an attachment filename. All use a separate synthetic registry. Demo records cannot be used automatically to verify real mail.

```sh
python -m sentinel scan --demo 1
# Cloud processing also requires this explicit run-level flag:
python -m sentinel scan --demo 2 --allow-external
python -m sentinel export-demo
```

The last command writes five `.eml` files. To test delivery, send the sample content from your mail client to a dedicated test mailbox. Actual delivery authentication then reflects the real sending server.

## Real email and organization evidence

Create the IMAP folder before connecting, then configure `sentinel.toml`:

```toml
imap_host = "mail.your-organization.example"
imap_port = 993
imap_user = "review@your-organization.example"
imap_folder = "AI-review"
imap_password_env = "SENTINEL_IMAP_PASSWORD"
organization_file = "organization.json"
allow_quarantine = false
```

Set the IMAP password environment variable or an app-specific password supported by your mail service. IMAP supports TLS with password/app-password login, or `imap_auth = "oauth2"` with a current access token in `SENTINEL_IMAP_ACCESS_TOKEN`. Token issuance and renewal remain administrator-managed; there is no built-in OAuth login/refresh flow.

Copy `examples/organization.json` to `organization.json` and populate approved vendor domains/accounts, orders and policies. It starts empty so that fictional entries cannot accidentally authorize a real payment. The model cannot modify it. Match results are evidence, not payment approval. Payment matching supports compact IBANs and common Czech domestic account formats; it is not a full invoice parser.

Use **Load IMAP folder** in the UI, or import `.eml`. Ingestion uses read-only `SELECT`, UIDs, UIDVALIDITY and `BODY.PEEK[]`; it does not mark messages as read. Files and messages have size limits. Raw inputs live in process memory; local persisted reports contain pseudonymized tool outputs and summaries.

### Optional quarantine

Create the quarantine folder and set `allow_quarantine = true`. A model can propose quarantine, but the host only permits the move after a local operator approves a specific message-bound proposal. Approval expires after 10 minutes and is single-use. The server must support `UID MOVE`; there is no copy/delete/expunge fallback. All other messages are outside the model's tool scope.

### Read-only background use

```sh
python -m sentinel watch --entire-folder
# Cloud: explicit authorization for ongoing processing
python -m sentinel watch --entire-folder --allow-external
```

The watcher now uses a persistent SQLite queue, bounded UID discovery and restart recovery. It fetches bodies only when a worker begins processing and never executes quarantine. Configure the received-since date, retries, hourly rate and concurrency in the UI or TOML. The browser queue starts paused after a process restart; `watch` resumes explicitly authorized processing. See [queue operations](docs/QUEUE.md).


See [docs/OPERATIONS.md](docs/OPERATIONS.md) for deployment boundaries and retention.

## Rules, skills and specialists

[Check rules](docs/CHECKS.md) define mandatory, optional and disabled tools. The host emits a completion checklist and prevents LOW_RISK when mandatory evidence is absent, an account mismatches or injection indicators require review. [Runtime skills and scoped specialists](docs/SKILLS-AND-SUBAGENTS.md) are configurable, with shared budgets and no recursive delegation. [Release acceptance](docs/RELEASE-1.0.md) lists implemented capabilities and live-verification limits.

## Privacy and security

New configurations use `redacted_text` for semantic interpretation of pseudonymized email text. Existing settings are preserved. Optional `evidence_only` withholds email subject, sender and body from the initial model input and passes locally derived checks instead. Local policies and selected evidence may still disclose organizational context. `redacted_text` applies best-effort pseudonymization to email text and all tool results. It masks common addresses/accounts/numbers/URLs and administrator-provided terms. **Unknown names and sensitive prose can remain.** It is not irreversible anonymization or a DLP guarantee.

The outgoing-data preview shows initial message data and built-in tool outputs before external analysis. Known vendor names/contacts/domains and custom `redaction_terms` are replaced consistently within each run. Token mappings stay in memory. The UI renders model output as text, never model-supplied HTML; there are no remote images, CDNs or analytics.

Read [SECURITY.md](SECURITY.md) for threat boundaries and limitations. A LOW_RISK verdict means no identified concern in the performed checks, not a safety guarantee. Model summaries can still be wrong. Lack of a regex injection flag is not proof of absence of injection.

See [the security/UX review](docs/REVIEW-0.3.0.md) and [the optional AgentDojo evaluation](docs/AGENTDOJO.md).

## Development and verification

```sh
python -m unittest discover -s tests -v
python -m compileall -q sentinel
```

Test-only provider doubles verify branching, privacy, permissions, protocol parsing and failure behavior. They are not selectable in the application. Real API accounts and an IMAP server are required for live integration acceptance; run `doctor` and the bundled sample scenarios in your target environment.

Source map: `agent.py` owns the loop; `tools.py` owns local checks; `providers.py` owns native tool protocols; `privacy.py` is the outbound data boundary; `mail.py` owns MIME/IMAP; `server.py` serves the loopback UI; `store.py` records reports and approvals.

This project was written independently. Related repositories informed design discussions; no source code from them is included. See [docs/DESIGN.md](docs/DESIGN.md).

## License

MIT, copyright 2026 Michal Kubíček. See [LICENSE](LICENSE).

## Development

Start with [the developer guide](docs/DEVELOPMENT.md) and [AGENTS.md](AGENTS.md). See [changes in 0.6.0](CHANGELOG.md).

Author: [Michal Kubíček](https://kubicek.ai/). Support by [Mediatoring.com](https://mediatoring.cz/en/cybersecurity/).

Connection settings adapt to the provider: local AI shows a server URL; OpenAI, Anthropic and Gemini show an API-key field; compatible HTTPS providers show both. External-processing consent appears only for cloud providers.


## Organization rules and database tools

Enter investigation requirements in Settings → Check rules. The LLM assesses message meaning and conditional relevance in the message language; missing or uncertain relevance leaves the check required. Required checks cannot be waived by the model.

Configure evidence queries over your own schema through Settings → Agent extensions → Database evidence queries. SQLite and PostgreSQL adapters bind named parameters and return bounded, pseudonymized evidence. Python plugins can add other connectors. Each plugin defines its model-facing schema, UI title, applicability and completion criteria in one registration.

See [database configuration](docs/DATA-SOURCES.md), [plugin contract](docs/EXTENDING.md) and [semantic checks](docs/CHECKS.md). Live model language acceptance is available through `python -m evaluation.semantic_eval` and requires configured model access.

## Readiness and recovery

Run `python -m sentinel check` to validate configuration and load the evidence catalog and enabled skills without contacting AI. When quarantine is enabled, it also connects to IMAP to verify the target folder and UID MOVE support without reading or moving messages. Its JSON output excludes credentials; exit code 2 means configuration needs attention. `doctor` performs a real model tool-call test.

Set the loaded model context window in Settings to match your model server (`context_tokens`, default 8,192). Input is estimated before each request with room reserved for output; a context failure produces no verdict. Local reasoning models may need a larger context, output budget and timeout. See [model budgets](docs/HARNESS.md#context-and-output-budgets).

Use `python -m sentinel backup backup.sqlite3` for a consistent report/queue snapshot. Configuration, evidence sources and credentials require separate backups. See [operations](docs/OPERATIONS.md) for restoration. Only one server, watcher or scan process can own a data directory.

For deployment acceptance against a real model, run `python -m evaluation.semantic_eval` and `python -m evaluation.demo_eval` from the source checkout. Both use bundled synthetic data and save JSON results; external models additionally require `--allow-external`. Semantic evaluation supports repeatable `--case` selectors and checkpoints progress. See [validation](docs/VALIDATION.md) for measured results and remaining release gates.

Load local mailbox/model presets directly in Settings. Views have their own addresses and support browser Back/Forward and refresh. See [local presets and page addresses](docs/LOCAL-PRESETS.md).

Saving the settings form does not create a preset. Copy [the partial preset example](examples/local-preset.toml) into the ignored `.local-presets/` directory and customize it. A new browser must first open the private startup URL or use **Connect browser** in the interface.

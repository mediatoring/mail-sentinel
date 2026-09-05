# Validation record — 1.0.0rc1

Verified on Linux with Python 3.12:

- 105 automated tests, including optional AgentDojo adapter tests when that dependency is installed.
- Actual SQLite integration with a custom business schema, rejected writes, denied tables, bound parameters, bounded results, missing-database behavior and local pseudonym resolution.
- Semantic applicability routing with German, Slovak, Polish, French, Japanese and Arabic text; these tests use model decisions supplied by doubles and do not measure multilingual model accuracy.
- Required checks cannot be waived; uncertain, absent, withheld-text and truncated-text assessments remain conservative.
- Dynamic plugin metadata, custom completion blockers, administrator instructions, generic policy retrieval and SQL source configuration through the authenticated API.
- PostgreSQL protocol configuration tested through a driver double.
- Frontend DOM regression tests, including expired sessions and missing jobs; JavaScript syntax, Python compilation and shell launcher syntax.
- Cross-process data ownership, bind-before-start behavior, strict configuration types, backup integrity/no-overwrite, secret-free readiness output and recovery from temporary queue storage faults.
- Built a wheel with setuptools, installed it without dependencies or network access in a fresh virtual environment, then ran outside the source checkout: demo export, readiness, authenticated HTTP, every UI asset, SIGTERM, restart and database backup.
- CI now declares Windows/macOS/Linux source and installed-wheel checks plus a frontend job; those hosted jobs have not run in this workspace.

Live inference, semantic prompt-injection evaluation, PostgreSQL server integration, real IMAP, Windows/macOS execution and rendered-browser accessibility acceptance remain unverified in this build. No production security score or universal language accuracy is claimed.

The live multilingual acceptance command is documented in [check rules](CHECKS.md). See [release acceptance](RELEASE-1.0.md).

## Local macOS acceptance in progress — 2026-09-05

Python 3.14.5 / SQLite 3.53.1, LM Studio on loopback with `openai/gpt-oss-20b`:

- Real native tool calling passed (`doctor`).
- The first invoice investigation exposed premature completion; the agent now receives a host-computed checklist each turn and explicit conditional-check names. The repeated live run completed all checks in 79.4 seconds. Its verdict remained INCONCLUSIVE because sender authentication and payment authorization require independent evidence.
- 108 unit tests ran successfully (two optional AgentDojo tests skipped).
- Frontend DOM flow passed with jsdom 26.
- Fresh offline wheel installation passed on macOS, including assets, authenticated API, graceful termination, restart and backup outside the checkout.

Multilingual and mailbox acceptance are still in progress. These observations do not authorize a stable-version label yet. Local reports and configuration are excluded from Git.

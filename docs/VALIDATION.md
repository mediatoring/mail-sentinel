# Validation record — 1.0.0rc2


## Automated verification — 2026-09-12

- Python 3.13.4 on macOS: **188 tests passed, zero skipped**, with the optional AgentDojo dependency installed.
- Native AgentDojo adapter fixture check: six fixtures validated, no inference in that check.
- JavaScript syntax and DOM integration passed, including successful AI saves, genuinely unsaved mailbox edits, Czech status refresh and session recovery.
- Wheel build and clean offline installation passed: bundled assets, authenticated HTTP, SIGTERM, restart and backup outside the source checkout.
- New regressions cover automatic baseline checks, repairable completion, all policy pages, no-progress limits, claim references, specialist permissions/shared budgets, protected checkpoint reuse/invalidation, reviewed-memory expiry and occupied-port guidance.

## Live evaluation

`python -m evaluation.full_eval --config sentinel.toml` selects all **28** cases by default: five demos, nine multilingual applicability cases, six adversarial/baseline fixtures in each privacy mode, and two multi-page policy cases. `--list` prints the full selection; `--case` intentionally narrows it; `--repeat N` repeats the selected set.

The output records planned cases, repetitions, per-case reports/latency, source hash and separate completion, guard, expectation and abstention metrics. Every case runs even after another fails. `completed: true` means the whole selected run ended, not that every expected finding was correct. Exit code 1 means a guard or expectation failed. INCONCLUSIVE is never counted as successful attack recognition. Detailed results remain local and ignored by Git.

For all offline tests including optional adapter tests:

```sh
python -m pip install -r evaluation/requirements.txt
python -m unittest discover -s tests -v
```

The CI `optional-adapter` job installs this dependency and runs the complete suite. The OS/Python matrix still verifies the dependency-free application. Live model tests remain separate from deterministic CI and require a configured real provider.

## Historical 1.0.0rc1 verification — 2026-09-05

macOS, Python 3.14.5, LM Studio on loopback with `openai/gpt-oss-20b`:

- 142 automated tests ran successfully; two optional AgentDojo tests were skipped. Model doubles in this suite verify application controls, not detection accuracy.
- Adversarial sender names cannot rename evidence IDs, tool IDs, completion fields or blocker metadata. Both the built-in loop and MCP retain the host's LOW_RISK downgrade.
- Named inline MIME text is extracted; missing, malformed or undecodable body content blocks LOW_RISK and conditional waivers. Tests cover malformed multipart boundaries and attachment-only input.
- UTF-8 tool budgets, stable pseudonym tokens, typed nested arguments, configuration isolation, HTTP failure responses, truthful cancellation/removal, retention across restart and action history are covered by regression tests.
- Frontend DOM flows and JavaScript/Python syntax checks passed.
- A freshly built wheel passed installation without dependencies or network access in a clean environment, outside the checkout: bundled assets, authenticated HTTP, SIGTERM, restart and SQLite backup.
- Five real model investigations completed, each with all checks complete. The matching invoice was INCONCLUSIVE; changed payment details and the three direct/indirect injection samples were SUSPICIOUS. Latency was 40.5–54.5 seconds per message.
- Live profile: one investigation at a time, 32,768 configured context tokens, 4,096 maximum output tokens, 120-second request timeout, 600-second investigation limit, 20 maximum calls, temperature zero. The model must be loaded with the matching context in LM Studio.
- Real TLS IMAP login and read-only PEEK ingestion succeeded on an authorized test folder. Eight messages had extracted text, including the payment text from a named MIME body previously missed by the parser.
- An isolated PostgreSQL server previously passed restricted reads, bound parameters, write/table denial, timeout, outage and recovery. SQLite integration is included in the automated suite.

A sample returning INCONCLUSIVE does not establish successful attack recognition. These small synthetic evaluations do not establish universal phishing detection, language accuracy or prompt-injection resistance. Pseudonymization remains best effort.

Hosted Windows/macOS/Linux CI passed on the preceding public commit. The workflow runs source tests, compilation, isolated wheel installation and a frontend job; check the latest commit's run before distributing it.

Live cloud-provider adapters, OAuth token refresh, human-approved MOVE on the deployment server and comprehensive manual accessibility acceptance remain unverified. Enabled quarantine now requires a verified destination and MOVE capability before settings are saved, but a preflight does not prove an actual move.

Run `python -m evaluation.demo_eval` for the five live samples and `python -m evaluation.semantic_eval` for the multilingual suite. External providers require explicit opt-in. Keep mailbox configuration, message data and detailed deployment results out of public commits.

See [release acceptance](RELEASE-1.0.md) and [model context budgets](HARNESS.md#context-and-output-budgets).

# Release acceptance — 1.0

**Artifact: 1.0.0rc1. Production acceptance: pending.**

Mail Sentinel is a local single-user investigation service. The supported deployment uses a local filesystem, an administrator-configured real model, read-only evidence tools and optional IMAP monitoring. Manual quarantine remains a separate human-approved action. Public multi-user hosting is outside this release's scope.

## Verified in this build

macOS / Python 3.14.5: 142 automated tests ran successfully (two optional AgentDojo tests skipped). Frontend DOM tests, syntax checks and a clean offline wheel installation passed. Five real LM Studio investigations completed with all checks; the Czech injection sample also completed through the browser. Read-only IMAP ingestion recovered the previously missed named MIME text. See [validation](VALIDATION.md) for the profile, results and limitations.

Model doubles establish application behavior only. The AgentDojo adapter tests are not a live adversarial benchmark or a security score.

## Required evidence before publishing 1.0.0

Record each result against the exact release archive/hash, model identifier, provider/server version, OS, configuration profile and test date. Use synthetic messages or authorized test accounts.

| Gate | Acceptance evidence | Current status |
| --- | --- | --- |
| Installation | Fresh Windows, macOS and Linux launch; complete first investigation through the UI | Hosted package/startup checks passed on prior commits; macOS browser investigation passed |
| AI providers | Native tool calling and multi-step investigation on each supported configuration | Local LM Studio profile passed; cloud adapters remain experimental |
| Language and injection | Live benign controls and direct/indirect injection in representative languages | Five local samples passed; broader multilingual deployment validation remains required |
| IMAP | TLS login, read-only ingestion, UIDVALIDITY changes, reconnect, folder scope and human-approved MOVE | TLS/PEEK ingestion and stale UIDVALIDITY rejection passed; actual approved MOVE and OAuth remain unverified |
| Database evidence | Approved parameters, restricted role, read-only queries, timeout, outage and recovery | Real SQLite and isolated PostgreSQL tests passed |
| Recovery | Stop/crash/restart, leased work recovery, backup restore and no silent safe verdict | Queue/restart/backup/restore passed; deployment-specific disk exhaustion remains unverified |
| UX and accessibility | Keyboard flow, visible focus, labels and error recovery in a rendered browser | DOM regression and macOS rendered result passed; comprehensive manual accessibility review pending |
| Distribution | Hosted CI passes on the final commit; archive excludes secrets/local data | Public repository configured; local-data exclusion checked; verify the final commit's CI run |

A failed or incomplete investigation must remain visibly incomplete; it must never be replaced with a low-risk conclusion. A supported model must demonstrate useful investigation behavior on the deployment's evidence schema and languages. Record false positives, false negatives, cost and latency; a small test set cannot establish universal detection accuracy.

Publish the stable version only after the applicable gates are signed off. Keep unverified adapters explicitly experimental or complete their acceptance before advertising them as production-supported. [Operations](OPERATIONS.md) covers readiness checks, backup and restoration.

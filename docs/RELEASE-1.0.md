# Release acceptance — 1.0

**Artifact: 1.0.0rc1. Production acceptance: pending.**

Mail Sentinel is a local single-user investigation service. The supported deployment uses a local filesystem, an administrator-configured real model, read-only evidence tools and optional IMAP monitoring. Manual quarantine remains a separate human-approved action. Public multi-user hosting is outside this release's scope.

## Verified in this build

Linux / Python 3.12: 105 automated tests passed with the optional AgentDojo dependency installed. Frontend DOM tests and syntax checks passed. An offline wheel install in a new virtual environment successfully exported demo inputs, loaded the authenticated UI, stopped on SIGTERM, restarted and backed up its database. See [validation](VALIDATION.md).

Model doubles establish application behavior only. The AgentDojo adapter tests are not a live adversarial benchmark or a security score.

## Required evidence before publishing 1.0.0

Record each result against the exact release archive/hash, model identifier, provider/server version, OS, configuration profile and test date. Use synthetic messages or authorized test accounts.

| Gate | Acceptance evidence | Current status |
| --- | --- | --- |
| Installation | Fresh Windows, macOS and Linux launch; complete first investigation through the UI | Linux package/startup passed; Windows/macOS and real first inference pending |
| AI providers | Native tool calling and multi-step investigation on every advertised provider configuration | Protocol tests passed; live runs pending |
| Language and injection | Run `python -m evaluation.semantic_eval`; evaluate direct/indirect injection in representative languages, including benign controls | Application guard tests passed; live model evaluation pending |
| IMAP | TLS login, read-only ingestion, UIDVALIDITY changes, reconnect, folder scope and human-approved MOVE on a disposable mailbox | Protocol tests passed; live mailbox pending |
| Database evidence | Approved parameters, restricted database role, read-only queries, timeout, outage and recovery | Real SQLite passed; PostgreSQL driver tests passed; PostgreSQL server pending |
| Recovery | Stop/crash/restart, leased work recovery, backup restore, disk-full handling and no silent safe verdict | Automated queue/restart/backup tests passed; deployment restore/outage drill pending |
| UX and accessibility | First-time user on each OS, keyboard-only flow, visible focus, screen-reader labels and error recovery in a rendered browser | DOM regression passed; rendered-browser/manual acceptance pending |
| Distribution | Hosted CI passes on the final commit, archive excludes secrets/local data, maintainer selects repository and support channel | CI definition supplied; hosted run and repository publication pending |

A failed or incomplete investigation must remain visibly incomplete; it must never be replaced with a low-risk conclusion. A supported model must demonstrate useful investigation behavior on the deployment's evidence schema and languages. Record false positives, false negatives, cost and latency; a small test set cannot establish universal detection accuracy.

Publish the stable version only after the applicable gates are signed off. Keep unverified adapters explicitly experimental or complete their acceptance before advertising them as production-supported. [Operations](OPERATIONS.md) covers readiness checks, backup and restoration.

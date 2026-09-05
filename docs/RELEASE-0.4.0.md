# Release 0.4.0 — implementation and acceptance

| Capability | Delivered behavior | Acceptance boundary |
| --- | --- | --- |
| Administrator check rules | Required, model-selected, disabled and conditional payment/policy checks; host completion checklist | Pattern-based applicability can miss payment phrasing. |
| Prompt injection | Separate local indicator tool; EN/CZ body and attachment-name demos; low-risk downgrade | Not a complete semantic defense or attachment-content scanner. |
| Large mailbox | Durable reference queue, UID windows/cursors, claim leases, retry/backoff, rate and concurrency controls, pagination | Tested with 10,000 synthetic references, not 10,000 real model investigations. |
| Budgets and cancellation | Shared parent/child call, time and byte budgets; output-token cap; rolling daily call ledger; cancellation fencing | In-flight requests wait for timeout; no exact monetary budget. |
| Model picker and connection state | Models loaded from saved provider; editable ID; in-process test status | API model-list support and native tool support vary; live test required. |
| Report UX | Readable summaries, check outcomes, uncertainty and recommendations; paginated history; technical details collapsed | Full browser visual and assistive-technology acceptance remains outstanding. |
| Runtime skills | Local manifest/Markdown loader, reviewed enablement, hashes in reports | Trusted administrator instructions; no automatic learning or installation. |
| Specialist agents | Model-selected scoped children with shared budget, no recursion or actions | Same-provider assessments, not independent verification. |
| IMAP OAuth2 | SASL XOAUTH2 access-token authentication | Token issuance/renewal and tenant authorization remain with the identity administrator. |
| Codex / Claude Code / Cursor | Single-message MCP tools and guarded completion | External-client login and capabilities belong to that client; no embedded CLI providers. |
| AgentDojo | Custom suite and real-agent adapter retained | No live-model attack-success rate: no credentials or running local model available. |
| Platforms | Windows/macOS/Linux launchers and EN/CZ guides | Linux Python execution tested; Windows/macOS scripts reviewed, not executed there. |

No GitHub repository was published by this release. The source archive is ready to commit to the maintainer's repository. Complete live model, IMAP, client integration and target-platform acceptance before describing a deployment as verified.

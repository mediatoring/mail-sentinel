# Security model

This initial release is a local single-user review assistant for controlled pilots. It is not a mail gateway, malware sandbox, calibrated phishing classifier or guaranteed prompt-injection defense.

## Enforced by host code

- Model calls only registered tools with validated argument schemas.
- The current message is bound by the host; model arguments cannot name arbitrary mailboxes/files.
- Built-in analysis tools are read-only. No shell, arbitrary SQL, outbound email or URL fetch tool exists.
- Quarantine is a separate authenticated human action, bound to a report, message, mailbox and UIDVALIDITY. The approval token never enters model context.
- IMAP reads use TLS, read-only folder selection and BODY.PEEK. UID MOVE is the only supported mutation.
- The local server binds only to 127.0.0.1, validates Host and Origin, and requires a random session token for every API request. The token is given in a URL fragment, removed from the address bar, and stored in sessionStorage.
- Browser output uses textContent; a restrictive CSP blocks inline scripts and external resources. No message HTML is rendered.
- Redirects and ambient HTTP proxies are disabled in the model transport. Local endpoints must use a loopback host.
- Outbound initial content, observations and persisted model reports go through the privacy layer.
- LOW_RISK completion is downgraded when required checks are absent, conditional checks remain unresolved, or plugin evidence contains blockers. These narrow rules do not verify the truth of the narrative.
- Failure has no safe verdict fallback. Model call and output sizes and iteration count are bounded.

## Limits to understand

- Python plugins are fully trusted code and run with the application's OS privileges. Their read-only behavior cannot be guaranteed by a Python registry. Only install reviewed plugins; use a dedicated OS account/container for untrusted extensions. Dynamic installation by the model is absent.
- Prompt instructions can reduce risk but do not prevent all semantic manipulation. A model can still produce an incorrect report or recommend an inappropriate action. Evidence ID validation proves a reference exists, not that the conclusion follows.
- Pseudonymization is heuristic. It cannot recognize every name, business secret, legal matter, health detail or contextual identifier. Local policy text also crosses the boundary when selected. Use local inference when these residual disclosures are unacceptable.
- LLM semantic judgments depend on the selected model and language. Local pattern indicators are supplemental and incomplete; validate representative languages and attacks on your deployment.
- Sender domain matching does not verify the From header. Authentication-Results supplied inside a message is not accepted as verified authentication. Independent DKIM/SPF/DMARC validation is absent.
- Attachments are hashed, not opened or scanned. HTML text extraction may include hidden content as evidence. Unsupported or truncated content limits the conclusion.
- Raw messages and pseudonym mappings are held in process memory. OS swap, crash dumps and administrator access are outside this application's controls. SQLite reports are not encrypted by the application. Use disk encryption and appropriate OS ACLs. POSIX chmod is best effort; Windows ACLs are administrator-managed.
- Deleting records by retention does not guarantee forensic erasure from SQLite pages, backups or storage media. Apply organizational retention and destruction policy separately.
- The UI is single-user and its bearer URL grants local access. Do not publish it through a tunnel or bind it to a public interface. No enterprise SSO/RBAC is implemented.
- Time budget is checked between blocking calls; one configured HTTP timeout can bound an in-flight call. Arbitrary administrator plugins can exceed it. No monetary quota enforcement is implemented beyond step/output limits.
- A quarantine move can succeed while recording its audit entry fails (e.g. full disk). Such errors need mailbox verification; the UI must not be treated as a transactional mail server.

## Reporting

Do not post credentials, real email or exploit payloads containing sensitive data in public issues. Use the repository's private vulnerability reporting feature once enabled by its maintainer. Until that channel exists, request a private contact without including the sensitive details.

## Version 0.4.0 boundaries

Queue references, leases, retry state and cursors are persistent; bodies are fetched per worker. Cancelled or superseded claims cannot commit results. Recovery is at-least-once inference and can repeat paid calls after a crash. Rate/call limits are shared in SQLite; per-run budgets include specialists. Blocking administrator plugins can exceed runtime budgets.

Check modes are host enforced and disabled tools are not registered. Prompt-injection pattern matching is a local indicator source, not a complete defense. Runtime skills are trusted local procedures with content hashes. Specialists cannot recurse or perform mailbox actions; they inherit the configured read-only evidence catalog.

The stdio MCP transport exposes one startup-selected message and shares completion validation. It does not constrain other tools or free-text claims available in the external AI client. It has no quarantine operation. Real-message data exposure requires explicit startup authorization.


## Evidence queries and semantic relevance

Conditional relevance is a recorded model judgment. Missing/uncertain judgments leave checks required; text withheld or truncated prevents a semantic waiver. Required checks cannot be waived by the model. These controls do not make model classification infallible.

Database queries are administrator-approved templates with bound model-selected parameters. SQLite uses a read-only connection and authorizer. PostgreSQL requires a restricted database role and uses read-only transactions and timeouts. Database functions and Python plugins remain trusted administrator code. Query results pass through pseudonymization and are treated as untrusted evidence. See [data sources](docs/DATA-SOURCES.md).

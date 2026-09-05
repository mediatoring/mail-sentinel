# Security, UX and installation review — 0.3.0

## Security findings

The review covered model transport, agent completion, tool execution, privacy, MIME/IMAP handling, local HTTP authorization and the frontend. This is a focused source review with regression tests, not an exhaustive security audit.

| Finding | Change or remaining limitation |
| --- | --- |
| LOW_RISK could be returned after checking an unrelated tool while skipping message/payment evidence | Host now downgrades LOW_RISK to INCONCLUSIVE when basic checks are absent, payment prerequisites are incomplete, or a checked account does not match the order vendor. Tool order remains model-selected. Three regression tests cover omitted checks, mismatches and matching controls. |
| Importing an email during an investigation could switch the visible message while displaying the previous job's report | Message selection and import are blocked in the UI during an active job; IMAP loading is also disabled. |
| Consent visibility could remain stale after switching local/cloud settings | The selected message's consent control refreshes after saving settings. |
| Prompt injection can still distort a summary or action recommendation | Not solved by the new completion checks. The AgentDojo custom suite is ready for actual model evaluation; no live result was obtained. |
| Pseudonymization can miss sensitive prose; trusted Python plugins have full process privileges | Existing limitations remain. No claim of irreversible anonymization or plugin sandboxing. |

## UX changes

Removed the mandatory terminal setup from launchers. The first run opens the local service so users can configure it in the browser. Model settings appear first; optional mailbox/organization fields are collapsible. The author and support links are present, with the support destination following the interface language. A configured cloud provider no longer prompts for an API key in the terminal when starting the browser UI.

Remaining useful improvements: selectable model IDs obtained from the provider, a persistent connection-test state, actionable localized errors for common API/IMAP failures, readable report history instead of raw JSON, cancellation with provider-aware interruption, and a queue for larger mailboxes. These are not included in this release.

## Installation assessment

The previous quickstart assumed terminal experience and Python command naming. Separate EN/CZ instructions now cover extraction, Windows double-click/PowerShell, macOS Terminal, Linux, first model connection, shutdown/restart and common errors. Launchers reject Python older than 3.11; Windows tries `py -3` then `python`. macOS/Linux instructions use `sh start.sh` to avoid ZIP execute-permission issues.

Python 3.12 source execution and local HTTP integration were tested on Linux. Windows and macOS launch instructions and scripts were reviewed but not executed on those operating systems. Full browser visual/accessibility acceptance and live IMAP/model tests remain outstanding.

## Verification

40 tests passed in the optional AgentDojo environment: 38 core/regression tests and two AgentDojo adapter tests. Python compilation, JavaScript syntax and shell syntax passed. Six AgentDojo fixtures validated. No live model was available; the live runner refused to start without one. See [AGENTDOJO.md](AGENTDOJO.md) for the scope and reproducible commands.

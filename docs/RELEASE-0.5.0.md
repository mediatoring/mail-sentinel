# Release acceptance — 0.5.0

The local EN/CZ application supports a complete single-message review flow, real AI connections, configurable checks and persistent read-only mailbox processing. MIT source, installation instructions and extension guides are included.

## Acceptance covered by regression tests

- Draft model discovery does not save settings or expose another provider's key.
- Verified connection settings retain their verification state after saving; changing connection identity invalidates it.
- A host downgrade replaces contradictory low-risk advice and suppresses the proposed action.
- Message text is served only through the authenticated local API and rendered as text. Evidence-only model previews withhold that text.
- Browser reload can recover an active job; temporary polling failure retains the busy state.
- Queue start requires mailbox credentials and a date or explicit whole-folder selection.
- Queue results and history remain linked by stable message references; pages and IMAP search responses are bounded.
- Runtime states explain rate limits, retries and paused work.

## Live acceptance before deployment

Run a real connection test and the included messages with the chosen provider and model. Verify IMAP access on the intended server. Evaluate detection quality and privacy with representative authorized messages. Check installation on each target operating system. The automated suite uses synthetic inputs and test-only model doubles; it does not establish a prompt-injection defense score or production throughput.

See [validation record](VALIDATION.md), [installation](INSTALL.md), [queue operations](QUEUE.md) and [security boundaries](../SECURITY.md).

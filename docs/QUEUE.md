# Persistent mailbox queue

The review panel loads a small recent selection for manual work. The mailbox processing queue is separate and walks the whole configured folder, with an explicit received-since date or confirmation to include the entire folder in the web UI.

## Start from the UI

1. Configure and test the AI connection. Configure the review mailbox and your organization JSON file.
2. Set **Processing scope and limits**: received-since date, concurrent investigations, maximum attempts per hour and attempts per message. Set model-call, time, input-byte and output-token limits.
3. Save. For external AI, review the privacy mode, check rules, organization policy and installed tool code, then authorize ongoing queue processing.
4. Open **Mailbox monitoring**, review the displayed folder and limits, and confirm the entire-folder scope if no date was selected. Press **Start / resume**. The dashboard shows waiting, running, completed, failed, cancelled and skipped items. Both queue and report history are paginated.

**Pause new work** stops new discovery and claims. Already-running investigations finish. **Cancel** revokes an item's claim and requests cancellation at the next agent boundary. An in-flight model request or IMAP operation can continue until its timeout. A cancelled worker cannot persist a completed result under its old claim.

The browser service starts with the queue paused on each process start. Items and cursor positions survive. Resume explicitly after reviewing settings. Closing a browser tab does not stop the server. To stop the application, use Ctrl+C in the terminal.

## Unattended mode

```sh
python3 -m sentinel watch
# External AI requires explicit startup authorization:
python3 -m sentinel watch --allow-external
```

Use `py -3` on Windows. A supervisor can restart this command after failure. The watcher resumes saved work and never quarantines messages. Use one server/watcher process for each data directory; separate installations should use separate directories. SQLite transactions protect claims, but multiple independently configured services sharing a directory are not a supported deployment pattern.

## How discovery and recovery work

Each scan checks a bounded window of up to 500 UID values, constrained by UIDNEXT. It checkpoints that window and enqueues matching references in one transaction. While further windows remain, discovery continues on the next worker cycle. Once caught up, it uses the configured polling interval. Sparse UID spaces can require more windows. The optional date filter uses IMAP SINCE, which applies to the server's internal message date, not an untrusted Date header.

References include mailbox host, port, account, folder, UIDVALIDITY and UID. No raw bodies are stored in the queue. Each worker fetches its message with BODY.PEEK immediately before analysis and checks UIDVALIDITY. Missing, oversized or obsolete references become skipped items. Before changing mailbox identity, folder or start date in the UI, finish or cancel pending items. Changing the start date can restart enumeration; the reference identity deduplicates already queued messages. A changed UIDVALIDITY creates a separate scope.

Claims are atomic and have an owner token and lease. A process crash leaves a running item recoverable after its lease expires (investigation limit + HTTP/IMAP timeout + 120 seconds). Recovery counts toward the attempt limit. Retries back off from 30 seconds, capped at an hour. Failed/cancelled items can be manually retried. A crash after model inference but before committing a result can cause another paid model call: processing is not exactly-once billing.

## Limits and retention

- Concurrency: 1–8 queue investigations. Manual UI investigations are separate; all application agent calls share the rolling daily call ledger.
- Rate: investigation attempts per rolling hour, including retries.
- Daily budget: model calls in a rolling 24-hour period. Specialist calls consume the same allowance. Web connection tests consume this allowance; model-list requests do not perform inference.
- Per investigation: parent and child share model-call count, elapsed time and serialized input bytes. Each provider request also has an output-token limit. Input bytes are not billed tokens; these controls are not a precise currency quota.
- Retention removes old reports and terminal queue items. Cursors remain, so deletion does not automatically reprocess an old archive. Back up the database and configuration together. Deletion is not forensic erasure.

The service supports one configured mailbox/folder per installation. It is not a mail gateway: delivery is unaffected while an email waits for investigation. Python plugins run in-process and can exceed time limits if they block; only deploy reviewed plugins.

## Review and result navigation

Interactive loading searches bounded recent UID windows and fetches up to the configured message limit. Use monitoring to enumerate the entire selected scope. Input messages can be removed from the local list after review; this does not delete mailbox content or saved results.

Manual and queued IMAP input use the same stable mailbox-reference hash. Reports display this reference; messages still loaded in the current session also display their subject in history. Queue rows link to their saved result. Raw subjects and bodies are not added to persistent history metadata. Refreshing the browser reconnects to the active manual job while the server remains running.

History and queue pages are bounded, backed by database indexes, and fetch detailed reports on demand. Model throughput still depends on the provider, message content, selected checks and configured limits.

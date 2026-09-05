# Operations

Use a dedicated local account, a review mailbox folder and reviewed organization data. Keep the HTTP service on loopback. The UI is single-user; there is no enterprise SSO/RBAC or public hosting mode.

For queue startup, limits, restart semantics, cancellation, retention and supervisors, follow [QUEUE.md](QUEUE.md). For installation, follow [INSTALL.md](INSTALL.md) or [INSTALL.cs.md](INSTALL.cs.md).

## Secrets

The default variables are `SENTINEL_API_KEY`, `SENTINEL_IMAP_PASSWORD` and, for `imap_auth = "oauth2"`, `SENTINEL_IMAP_ACCESS_TOKEN`. Use your OS/supervisor secret management. Browser-entered keys and passwords remain in the process only. OAuth token issuance and refresh require an identity service or administrator; provide a fresh token to a restarted process when it expires. Never commit secrets or real email samples.

Settings and pseudonymized reports persist under the configured directory. Queue references also contain the mailbox account, folder and UID identity. They do not include raw bodies. Apply filesystem ACLs and disk encryption appropriate to the machine; Windows ACLs are administrator-managed. Back up configuration and database consistently.

## Acceptance

Run `doctor` against the chosen real model. Validate native tool calls, privacy settings and known clean/suspicious messages. Test IMAP authentication, UIDVALIDITY, PEEK behavior and optional human-approved MOVE on a dedicated mailbox. Check the [release acceptance table](RELEASE-0.6.0.md) before rollout. The queue never performs MOVE.

Review plugin code and skill changes as trusted configuration. The process is not a sandbox for Python plugins. Timed-out network/model requests can already have incurred charges. Cancellation is cooperative between blocking calls; application limits are not an exact billing quota.



## Readiness, backup and restore

Run `python -m sentinel check` with the same configuration and environment as the service. This loads trusted plugins and validates their registration, source definitions and enabled skills. It does not execute evidence queries or make a model request. With quarantine enabled, it connects to IMAP and verifies UID MOVE support and the exact destination folder name without reading or moving messages. Create that folder in your mail client first (some servers require an `INBOX.` prefix). The same check runs before saving enabled quarantine settings and immediately before an approved move. Required local reference data must be populated or its check mode changed. Exit code 2 means settings require attention. A passing check does not replace `doctor` or deployment acceptance.

Create a consistent database snapshot while the application is running:

```sh
python -m sentinel --config /path/to/sentinel.toml backup /secure/backups/sentinel-2026-09-05.sqlite3
```

The destination must not exist. The command uses SQLite's backup API and checks integrity. It copies reports, queue references, cursors and usage counters; it does not copy configuration, administrator SQL definitions, evidence databases, skills, plugins or secrets. Back up those dependencies separately with appropriate access controls. Reports and queue references can contain sensitive information.

To restore:

1. Stop every Mail Sentinel process using that data directory. Preserve the existing database separately for rollback.
2. Restore the matching configuration and extension files. Restore credentials through the organization's secret provisioning method.
3. Copy the snapshot to `reports.sqlite3` in the configured data directory. Restrict its permissions to the service account.
4. Start `serve`. The queue starts paused. Review the source folder, received-since date, pending work and model limits before resuming.
5. Open an existing report and run one authorized test investigation. Restoring an older cursor can repeat inference; expired in-flight claims are recovered through the queue's normal lease mechanism.

Do not copy a live SQLite file with a file manager. Use the backup command. Keep the data directory on a local filesystem with working OS file locks. One `serve`, `watch` or `scan` process may own it at a time. The OS releases ownership after a crash; do not delete the lock file to bypass a running owner.

For `watch`, set `queue_since` or pass `--entire-folder`. A read-only IMAP connection is checked before workers start. Ctrl+C and SIGTERM request cancellation and stop new work. Blocking third-party plugins still require OS-level supervision.

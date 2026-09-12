# Runtime skills and specialists

## Skills

Configure `enabled_skills = ["payment-review"]` or enter installed IDs in **Agent extensions**. Each skill is a directory under `skills_dir` with `SKILL.md` and `manifest.toml`. The bundled example is ready to enable.

```toml
version = 1
id = "payment-review"
tools = ["inspect_message", "verify_payment", "search_policy"]
```

The manifest's tool names are prerequisites, not new permissions. Disabled or unknown prerequisites reject skill loading. IDs must match the directory name; traversal, escaping symlinks, files larger than 16 KB and more than ten enabled skills are rejected. Restart after changing skill files to keep deployment changes explicit, although each investigation reloads the configured files. Each completed report records the skill IDs and hashes of both files.

Skills are administrator-trusted instructions appended to the system context. They cannot add tool permissions or override host completion/approval checks. Install them through normal reviewed code changes and keep them under version control. The agent does not create or install skills from email content. `AGENTS.md` and editor entry points remain separate contributor guidance.

## Specialists

Enable **Allow scoped specialist agents** in Settings to allow the role-based delegation described below.

## 1.0.0rc2 specialist roles

`consult_specialist` now accepts `area` from `payments`, `manipulation`, `policy`,
`critic`, and an optional `question`. Unknown roles are rejected. Each role is
intersected with the parent's enabled tools; unrelated tools and plugins are
removed from the child's executable registry, including non-check tools.

| Role | Tools (only when parent permits them) |
| --- | --- |
| payments | inspect_message, verify_payment, verify_sender |
| manipulation | inspect_message, inspect_prompt_injection, inspect_links, inspect_attachments |
| policy | inspect_message, search_policy |
| critic | inspect_message, inspect_prompt_injection |

The child gets a fresh conversation, protected parent observations as explicitly
untrusted evidence, and no parent verdict to obey. Child references remain scoped
to its returned assessment. A child has at most four model calls, with one call
reserved for the parent, and shares global byte/call/time/cancellation limits.
The parent can choose a specialist when an unresolved question merits the cost;
there is no mandatory fleet or recursive delegation. Specialists cannot approve
quarantine, add tools, or satisfy the parent's checklist with their summary.
A critic is advisory reasoning, not an independent source or automatic proof.

## Human-reviewed historical memory

Set `reviewed_cases_file = "reviewed-cases.json"` in the administrator TOML file.
The JSON is a list with entries of this form (use actual review/expiry dates):

```json
[{
  "id": "case-001",
  "lesson": "Confirm account changes using an independently recorded contact.",
  "source_report": "local-report-id",
  "reviewed_by": "authorized operator",
  "reviewed_at": "2026-09-12T12:00:00+00:00",
  "expires_at": "2026-12-12T12:00:00+00:00"
}]
```

Only an operator edits this file after verifying the original case. Missing
review metadata, invalid dates and oversized files are rejected. Expired entries
are omitted. `recall_reviewed_cases` reads bounded pages and pseudonymizes them;
it is unavailable for demo inputs. Its result is optional historical context,
not an authorization, a current vendor/account registry, or a substitute for
required checks. The model cannot write, approve or install memories. The file
is administrator-trusted, not a cryptographically verified identity record.
Do not commit real case data. Changes to the file invalidate reusable evidence
checkpoints and are recorded by hash in reports.

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

Enable **Allow scoped specialist agents**. The parent supplies a descriptive focus to `consult_specialist`. The child uses the same real provider with a fresh transcript and the current configured tool catalog, including approved plugins and evidence queries. Focus does not grant new permissions.

There is one delegation level, no recursion and no mailbox actions in the child. Parent and child share cancellation, call count, input-byte allowance and elapsed-time budget. Child results and evidence are nested under their own evidence IDs. The parent still has to satisfy its own required checks; a child summary is not a substitute for the parent's host-enforced evidence requirements.

Specialist checks are advisory except mandatory message inspection. Enable specialists only when their additional model calls help the investigation. A specialist assessment is a second model assessment, not independently authenticated evidence.

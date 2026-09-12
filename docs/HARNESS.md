# Harness and provider extensions

The harness is the host code around the model: message scope, transcript, available tools, execution limits, output validation and events. It is implemented by `Agent.run`, `harness.py` and `recovery.py` together with `Registry` and `Provider`; there is no separate harness plugin loader.

## Investigation lifecycle

1. The caller creates a `Registry` for one parsed message, the correct organization dataset, privacy policy and configuration.
2. `Agent` builds the initial protected message and offers the registry definitions plus `finish_investigation`.
3. `Provider.decide(system, context, definitions)` makes a real model request and returns `{"name": ..., "arguments": ...}`. One selection is executed per turn.
4. `Registry.execute` validates arguments, runs the tool and protects its output. The host adds an evidence ID and appends the observation to the transcript.
5. The model chooses the next operation. A completion must cite observed successful evidence. Exhausted budgets or provider failures produce an incomplete result.
6. Quarantine approval happens outside this loop through the existing application approval path.

## Replace the provider in Python

`Agent(registry, provider=adapter)` accepts an object exposing `decide(system, context, definitions)`. This is dependency injection for embedded integrations and tests. Normal CLI/UI execution constructs `Provider` from configuration; a new selectable transport also needs configuration validation and UI changes.

The adapter must return a parsed native tool choice, never execute tools itself. Do not grant the model shell, filesystem or mailbox access via a surrounding CLI. Preserve the protected context and do not add raw message content to transport logs. Enforce request timeouts and response-size limits; host elapsed-time checks cannot interrupt an adapter that blocks indefinitely.

For a new transport, inspect the existing methods in `providers.py`, then test native tool selection parsing, malformed arguments, missing tool selections, connection failures and error-message sanitization. Run an actual `doctor` request against the intended provider before claiming live support.

## Change orchestration

Modify `Agent.run` only when its existing single-tool loop cannot express the behavior. Preserve the completion schema, evidence provenance, event contract, privacy boundary and incomplete status. Update server/CLI consumers if event shapes change. Test unknown tools, invalid evidence references and budget exhaustion before testing successful paths.

The [MCP adapter](MCP.md) lets an external harness select evidence tools and request guarded completion. Direct CLI subprocess providers are not included. External client tool permissions are outside the MCP server's enforcement boundary.

### Completion progress

Each model turn includes `completion_checklist`, computed by the host from validated tool observations, and `remaining_steps`. Checks that failed validation remain outstanding. Unverifiable reference data remains a visible gap; the checklist does not fabricate missing evidence or weaken final completion validation. The applicability tool explicitly lists all conditional check IDs so models can classify the entire catalog.

### Context and output budgets

Set `context_tokens` to the window actually loaded in the model server (default 8,192). Before a request, the host estimates input tokens from UTF-8 size at three bytes per token, adds 512 tokens for protocol overhead, and reserves `max_output_tokens`. This is an estimate, not an exact tokenizer; provider-side context errors are also classified safely. `max_input_bytes` separately limits cumulative traffic over the investigation. The model server's context setting must be changed in the server itself.

After `inspect_message`, the initial message is replaced with a reference to that observation to avoid sending the same body twice. Evidence is otherwise retained in full; the host does not silently discard earlier conflicts to fit the context. Oversized investigations stop visibly without a verdict. Reduce input size or increase both configured and loaded context. Model reasoning counts toward the server's output limit; slow local models may also need a larger request timeout. Lowering step limits below the required checks plus completion is not a solution.

## 1.0.0rc2: host-owned orchestration

The default `automatic_checks = true` runs enabled, required built-in message,
injection, sender, link and attachment checks before the first model request.
These pass through `Registry.execute`, receive `B01`–`B05` evidence IDs and emit
the same tool events as model-selected checks. Optional/disabled checks and
third-party plugins are never executed by this preflight. Model-selected steps
have `E` IDs. Model call limits count inference, not these local checks.

`harness.py` computes `case_state` (pending checks, unavailable references,
conflicts, phase) from the evidence. A premature non-INCONCLUSIVE finish returns
`completion_rejected` with missing checks and the first unread policy offset.
The model can obtain more evidence or explicitly abstain. All policy pages must
be covered, including gaps between fetched pages. An explicit INCONCLUSIVE
handoff is possible without inventing reference data. Risk and coverage are
separate: `coverage`, `checks_complete`, and `requires_human_review` describe the
scope alongside the verdict. Missing references do not make an email malicious.

Every finish includes `claims`: statement, supporting evidence IDs, counter-
evidence IDs, and limitations. Every finish request requires at least one claim,
including an observed fact when abstaining. If the host downgrades an unsafe
LOW_RISK verdict, it clears the original claims along with the reassuring text.
The host validates all references; this does not prove semantic entailment.
Reviewers can inspect claims in the UI. A model that repeats an identical call
more than twice stops with no final verdict. Fixed tool errors remain safe to
show; arbitrary provider/plugin errors are suppressed.

### Recovery

UI, CLI scans and queue workers use a disposable `investigation_cache` in the
existing private SQLite database. Checkpoints expire after 15 minutes. They
contain protected evidence and call/input-byte counters, never raw email,
credentials or pseudonym reversal maps. Each key binds the message, organization,
configuration, plugin entry hashes, skills, data source hash and reviewed-memory
hash. Resumption re-executes deterministic bundled checks and requires identical
protected observations before reusing their IDs; model calls already reserved
remain charged. IDs stay unique. Successful completion removes the checkpoint.

Only bundled checks with no arguments, plus policy offsets, are replayable.
Specialist, historical-memory and custom query/plugin steps start a fresh run
because their freshness/reconstruction is not guaranteed. A provider call in
flight may repeat after a crash; resumption is not exactly-once execution. A new
attempt receives a fresh wall-clock deadline but retains the saved call and byte
budget. Queue lease ownership/cancellation remains authoritative. Raw inputs
still need to be fetched or imported again after a process restart.

### Design references

This implementation takes inspiration from [Hermes delegation patterns](https://hermes-agent.nousresearch.com/docs/guides/delegation-patterns)
(clean child context, bounded task) and [OpenClaw runtime separation](https://docs.openclaw.ai/agent-runtime-architecture)
(run lifecycle, evidence/tool dispatch, session state). Neither runtime is a
new dependency. No shell, unrestricted browsing or model-managed permission
changes were introduced. Concurrency remains at the message queue level; local
specialists run on demand and sequentially to avoid overloading a local model.

# Harness and provider extensions

The harness is the host code around the model: message scope, transcript, available tools, execution limits, output validation and events. In this release it is implemented by `Agent.run` together with `Registry` and `Provider`; there is no separate harness plugin loader.

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

# Extending Mail Sentinel

Tools are explicit Python registrations. A tool declares a name, purpose, input schema and callable. The model sees these definitions and chooses which to call. The application assigns evidence IDs, applies outbound pseudonymization and bounds serialized results.

Example: add `plugins = ["examples.vendor_tool"]` to `sentinel.toml` when running from the repository. The included `registry_health` tool reports whether organization data exists. Its invocation order is selected by the model. Restart after changing plugin configuration.

Keep extension functions read-only. Never expose arbitrary commands, SQL, URLs or file paths as model arguments. Fetch credentials from administrator-owned configuration, not tool input. Network tools should validate exact permitted destinations, size/timeout limits and every redirect. Do not submit full URLs with tokens or upload attachments to public scanners by default.

The schema validator supports declared objects, strings, enums, integers, finite numbers, booleans and typed arrays. Nested objects must declare their properties; unknown keys are rejected. Limits are 8 nesting levels, 100 object properties or array items, 4,000 characters per string and 32,000 UTF-8 bytes for the complete arguments. `minimum`, `maximum`, `maxLength` and `maxItems` can tighten these limits. Unsupported schema types fail closed. All tool metadata is administrator-trusted; do not put secrets into descriptions or schemas. Preview eligibility is declared in tool metadata; administrator review is required for installed plugin behavior.

Python modules are not sandboxed. A malicious plugin can bypass the privacy layer, access environment variables or perform writes. Do not confuse a tool registry with OS isolation.

## Organization JSON

A vendor entry uses `id`, `name`, `domains`, `accounts`, `contacts`. An order uses `id`, `vendor_id`, `amount` (string), `currency`. A policy uses `id`, `title`, `text`. An indicator uses `domain`, `status`, `source`.

`examples/organization.json` is intentionally empty. Populate it from your approved sources. The bundled demo dataset shows this optional adapter shape and must not be used as real evidence. For other structures, configure [SQL evidence queries](DATA-SOURCES.md).

## Providers and transports

`Provider.decide(system, context, definitions)` must return one real native tool selection: `{name, arguments}`. A response that only contains prose fails closed. Every response is validated before execution. Add protocol tests when extending this interface.

The [stdio MCP adapter](MCP.md) exposes current-message evidence and guarded completion to external clients. Their authentication stays in the client. The web application does not wrap CLI subscription credentials.

## Add and activate a tool

1. Copy `examples/vendor_tool.py` to an importable Python module and give the tool a unique name.
2. In `register(registry)`, define a read-only callable and register `Tool(name, description, schema(...), callable)` with `registry.add`.
3. Use `registry.message` for the current parsed message and `registry.org` for approved local data. Return a small JSON-serializable object. Return uncertainty explicitly when data is missing.
4. Add the module name to the `plugins` array in `sentinel.toml`, then restart. Source-checkout modules must be importable from the process working directory; a wheel install needs separately installed plugin modules.
5. Instantiate the registry with synthetic input and call `registry.execute` to verify the output and pseudonymization. Test invalid arguments and missing registry data. Do not test only the callable: that bypasses the host boundary.
6. Run a real model investigation to verify the definition is usable. Tool selection is the model's decision, so a successful investigation does not guarantee every plugin was exercised.

The bundled `examples.vendor_tool` is executable as shipped; it reports registry counts and needs no API credentials of its own. The investigation still needs a configured model. See [the developer guide](DEVELOPMENT.md) for harness, skills and subagent extension points.

## Plugin check contract

Built-in checks are registered by `sentinel.builtin_checks` using the same `Tool` interface as external plugins. Define each check in its plugin:

```python
registry.add(Tool(
    name="verify_case",
    description="Verify that the requested case disclosure has approval.",
    parameters=schema({"case_code": {"type": "string"}}, ["case_code"]),
    run=lookup_case,
    title={"en": "Case approval", "cs": "Schválení případu"},
    default_mode="conditional",
    applicability="The message requests access to case information, in any language.",
    available=lambda result: result.get("record_found", False),
    blockers=lambda result: ["Disclosure denied"] if result.get("denied") else [],
    preview=False,
))
```

`run` returns a JSON object. `available` determines whether the returned evidence can satisfy the check, and `blockers` returns explanatory strings that prevent LOW_RISK. The host computes these values from the original plugin output, redacts content and blocker descriptions, then attaches the `_check` envelope. Plugin output cannot replace that envelope. Tool IDs, evidence IDs, check state and verdict enums stay outside text redaction. The serialized observation is limited to 20,000 UTF-8 bytes. A plugin may implement a business check, database lookup or another evidence source; it must not interpret email instructions as authorization.

Set `preview=False` for queries needing model-selected parameters or calls that should execute only during an authorized investigation. The outgoing preview lists these tools and their schemas; exact results are obtained at runtime under the saved privacy policy. `reference_keys` can identify required keys in the optional local JSON adapter for preflight guidance. `check=False` is reserved for orchestration utilities that do not themselves satisfy an evidence check.

Register plugins through the administrator-owned `plugins` list. The web UI builds controls from their metadata. Unknown configured check IDs fail configuration validation. Reports include hashes of plugin entry files and administrator requirements; these hashes do not attest to all transitive dependencies.

[SQL source configuration](DATA-SOURCES.md) creates evidence tools from approved queries and does not require writing a Python plugin. [Semantic applicability](CHECKS.md) applies to both query tools and Python checks.

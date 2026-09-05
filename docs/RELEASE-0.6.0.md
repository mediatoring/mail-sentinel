# Release acceptance — 0.6.0

The distribution implements a local single-user email investigation service with real model calls, semantic applicability, a unified check-plugin contract, administrator requirements and database evidence tools. It retains authenticated loopback access, read-only investigation and separate human approval for manual quarantine.

## Automated acceptance

- Regression tests cover multilingual text routing and conservative applicability decisions, plugin completion metadata, configuration provenance and database integration.
- Actual SQLite tests cover arbitrary business schema, parameter binding, read-only restrictions, undeclared tables, output limits and pseudonym resolution.
- PostgreSQL transport tests verify bound parameters, read-only configuration, timeouts and server-side cursor selection with a driver double.
- UI regression tests cover connection setup, message review, dynamic check catalogs, result navigation and reconnect behavior.
- Existing agent, queue, MCP, authorization and optional AgentDojo adapter tests remain included.

## Deployment acceptance still required

Run the real model connection test and `python -m evaluation.semantic_eval` on the intended model. Evaluate prompt-injection resistance and representative authorized messages. Verify IMAP, database role privileges, remote TLS and operation on the target OS. Test restores and monitored operation under the intended limits. No live inference credentials or PostgreSQL server were available during this build, so those integrations have not been accepted as production-ready here.

Production acceptance depends on the actual model, server, data configuration and operating environment. Passing source tests is not a substitute for that acceptance. See [validation](VALIDATION.md), [data sources](DATA-SOURCES.md) and [operations](OPERATIONS.md).

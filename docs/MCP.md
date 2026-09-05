# Codex, Claude Code and Cursor through MCP

Mail Sentinel can expose evidence tools and guarded completion to an external AI harness over stdio. The external client supplies the actual model and handles its own supported login. Mail Sentinel neither extracts browser cookies nor receives the client's subscription credentials.

From the project folder:

```sh
python3 -m sentinel mcp --demo 4
```

For a real exported message, select it at startup and explicitly authorize exposing its protected evidence:

```sh
python3 -m sentinel --config sentinel.toml mcp --file review.eml --allow-client-data
```

Use `py -3` on Windows. Register the equivalent executable/argument array in your client's stdio MCP settings, with the project as its working directory. For clients without a working-directory option, install the project into that client's Python environment with `python -m pip install /absolute/path/to/mail-sentinel` and use that interpreter as the executable. With an installed package, pass an absolute `--config` path and an absolute EML path. Follow the client's supported MCP setup and authentication flow.

The adapter implements the [2025-06-18 lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle) and [tools protocol](https://modelcontextprotocol.io/specification/2025-06-18/server/tools). It is a legacy handshake transport; it does not implement newer stateless MCP protocol versions. The client must support negotiation of 2025-06-18.

It exposes enabled built-in checks for one startup-selected message. Each observation has an evidence ID. `finish_investigation` applies the same host completion rules as the web application. There are no arbitrary file paths in model arguments, mailbox-changing tools, plugins, runtime skills or child agents in this adapter. The separate external harness can itself have other capabilities; this server does not sandbox that harness. A client's free-text answer that bypasses `finish_investigation` is not a Mail Sentinel-validated report.

MCP mode does not populate the web application's history or use its provider selection. The web UI and persistent queue use configured API/local-model providers. Direct embedded Codex/Claude CLI subprocess providers and direct ChatGPT/Claude web-session authentication are not included. This integration has local protocol tests; actual client versions and account logins still require live acceptance on the target machine.

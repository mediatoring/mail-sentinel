# Organization rules and evidence sources

Mail Sentinel separates three administrator inputs:

- **Investigation requirements** describe what must be established before acting on a message. Enter these in Settings → Check rules, in ordinary language.
- **Evidence queries** expose selected facts from the organization's database. Each query becomes a registered tool with parameters, an applicability description and a completion rule.
- **Check modes** determine whether a tool is always required, selected by the model, conditional on semantic relevance, or disabled.

For example: “Before disclosing case information, verify that the case owner approved disclosure. Treat an absent record as unverified and recommend contacting the owner.” These requirements apply regardless of message language. Set the corresponding query to Required when it must run for every message, or When applicable with a description of the relevant requests.

## Configure a database

Open **Settings → Agent extensions → Database evidence queries**. Start from [the SQLite example](../examples/data-sources.sqlite.json) or [the PostgreSQL example](../examples/data-sources.postgresql.json). Replace the connection location, schema notes, SQL, parameters and descriptions with your own approved data model, then save settings. Queries appear automatically in Check rules and in the model's tool catalog.

The JSON file is an administrator configuration document. It contains approved SQL and environment-variable names, never a model-generated destination or SQL statement. Saving the editor creates an immutable document in the data directory and atomically switches the application configuration to it. The read-only path field identifies that document. Terminal deployments can instead set `data_sources_file` in TOML to an administrator-managed JSON file.

Each query has:

| Field | Meaning |
| --- | --- |
| `name` | Unique tool ID across installed plugins and evidence queries. |
| `description` | Purpose, interpretation of returned columns and parameter meaning, supplied to the model. |
| `sql` | One administrator-approved SELECT/WITH statement. |
| `parameters` | JSON Schema definitions for named string, integer or boolean parameters. |
| `required` | Parameter names that must be supplied. |
| `mode` | `required`, `conditional`, `auto` or `off`. |
| `when` | Semantic applicability description for a conditional check. |
| `require_rows` | Defaults to true: no matching rows means evidence is unavailable. Set false if an empty result is meaningful evidence for this query. |
| `title` | Optional `en` and `cs` labels for the interface. |

`schema_notes` on the source describes relevant tables, columns and field meanings. It is shared with the model along with tool descriptions. Only describe approved evidence fields. SQL can map an existing schema directly; no vendor/order schema is required. The LLM chooses the query and supplies values, while the adapter binds those values as parameters. Query results are untrusted evidence and pass through pseudonymization before reaching the model or reports.

Pseudonym tokens used as parameters are resolved within the current investigation before the local query. Original values are not inserted into the model transcript. Return only columns needed for verification; pseudonymization remains best effort.

## SQLite

SQLite uses the Python standard library. `path` points to an existing database; use an absolute path to avoid ambiguity. Named SQL parameters use `:parameter_name`.

The adapter opens the database in read-only mode and enables query-only behavior. An authorizer restricts reads to the declared `tables` and a small set of built-in SQL functions, and denies mutations, attachment of other databases and extension loading. Views require their underlying tables to be approved as well. A progress handler bounds query execution; returned row counts and serialized output sizes are limited. Narrow oversized results in the approved query.

## PostgreSQL

Install the optional driver in the application's Python environment:

```sh
python3 -m pip install '.[postgresql]'
```

On Windows use `py -3 -m pip install ".[postgresql]"` from the extracted project folder. `dsn_env` names an environment variable holding the connection string. Configure TLS and server identity verification in that connection string for remote servers.

Use a dedicated database login with SELECT privileges only on approved evidence views. PostgreSQL access restrictions are enforced by database grants; a SQLite-style `tables` list is not accepted for this driver. Review the functions and views called by approved SQL as well as their underlying privileges.

The adapter uses a read-only transaction, statement and connection timeouts, bound `%(parameter_name)s` parameters and a server-side cursor. It retrieves a bounded result rather than buffering the entire query result in the client. Read-only transaction mode is additional protection; it does not replace correct database privileges or review of server-side functions.

## Other systems and the vendor adapter

Python plugins can implement another database or API connector using the same [tool contract](EXTENDING.md). Only installed drivers are supported. Keep credentials and destinations in administrator configuration, apply time/result limits, and register the tool through `Registry.add`.

The bundled vendor/order JSON adapter remains available for organizations using that layout. Its account matching supports compact IBAN and Czech account formats. Disable those registry checks when using different evidence tools, and configure the relevant new queries in Check rules. The message, link, attachment-metadata and supplemental injection-pattern checks work independently of the vendor adapter.

Sample emails do not execute the configured real database queries. Test database integration with an authorized `.eml` input or a dedicated test mailbox.

## Verification

Automated tests execute actual SQLite queries, reject writes and undeclared tables, check parameter binding and verify pseudonym handling. PostgreSQL transport has a protocol-level test; test its actual connection, TLS and permissions against the intended server before deployment.

Implementation references: [Python SQLite API](https://docs.python.org/3/library/sqlite3.html), [Psycopg connections](https://www.psycopg.org/psycopg3/docs/api/connections.html), [PostgreSQL transaction and statement settings](https://www.postgresql.org/docs/current/runtime-config-client.html).

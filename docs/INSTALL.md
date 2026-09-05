# Installation

[Česky](INSTALL.cs.md)

You need Python 3.11 or newer, a browser, and either a local model server with tool-call support or an API key and model identifier. IMAP is optional for the first run. No Python packages need installing to run the application from this folder.

## Windows

1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/). Enable the installer option to add Python to PATH when offered.
2. Extract the ZIP completely (right-click → Extract All). Open the extracted `mail-sentinel` folder. Do not run inside the ZIP viewer.
3. Double-click `START.bat`. Leave its terminal window open.
4. Open the full local URL printed in the terminal in your browser, including `#token=…`.

If double-clicking fails, open PowerShell in the extracted folder and run:

```powershell
py -3 --version
py -3 -m sentinel serve
```

If `py` is unavailable but Python is installed, use `python --version` and `python -m sentinel serve`. The launcher tries both. A version below 3.11 must be upgraded. Reopen the terminal after installation if the command is not found.

## macOS

Install Python 3.11+ from [python.org](https://www.python.org/downloads/macos/) if needed. Extract the ZIP, open Terminal, type `cd `, drag the extracted `mail-sentinel` folder into Terminal and press Return. Then run:

```sh
python3 --version
sh start.sh
```

Leave Terminal open and open the complete local URL it prints. Using `sh start.sh` works even when the ZIP extraction did not preserve executable permissions.

## Linux

Use your distribution's package manager to install Python 3.11+ if needed. Extract the ZIP and open a terminal in the `mail-sentinel` folder:

```sh
python3 --version
sh start.sh
```

If the distribution provides an older Python, install a supported version using its documented method. Do not replace the system Python executable manually. No `sudo` is needed to run Mail Sentinel.

## Connect AI and investigate the first message

1. Choose **Try a sample email**, **Open an .eml file**, or **Connect a mailbox**. Sample emails include their own fictional reference data.
2. Open **Settings → AI connection**. Choose the provider. For a local model, start its server and select **LM Studio**, **Ollama**, or your own loopback address. For cloud AI, enter an API key and enable external processing.
3. Click **Load available models**, then select a model, or enter its exact identifier. The button uses the details currently entered in the form.
4. Choose **Local evidence only** to share local findings while withholding the email text, or **Pseudonymized text** for analysis of masked text. Masking can miss sensitive information. Select the report language.
5. Click **Verify and save AI connection**. This makes a real model request and can incur provider charges. Success verifies connectivity and tool calling; it does not measure detection accuracy. **Save connection** saves without making an inference request.
6. Open **Review messages** and select a message. Read its text and the analysis scope. For external AI, click **Review outgoing data**, review the items and confirm consent, then click **Investigate with AI**.
7. Read the conclusion, check coverage and recommendations. Expand **Investigation trace** for technical evidence. **Recent investigations** retains saved results; refreshing the page reconnects to an active investigation.

For mailbox input, configure **Settings → Mailbox and organization data** and save settings. Create the review folder on the mail server first. TLS IMAP accepts a password/app password or an administrator-issued OAuth2 access token. Token issuance and renewal are managed by the identity administrator.

In **Check rules**, select **General security checks** for local indicators or **Security and organization checks** when approved reference data is available. Save settings to apply the profile. Required registry checks need the organization JSON file; missing reference data appears before analysis and prevents a low-risk conclusion when required checks cannot be verified. General checks do not verify vendor identities or payment accounts against a registry.

Use **Mailbox monitoring** for ongoing processing. Set a received-since date under **Processing scope and limits**, or explicitly include the entire folder on the monitoring screen. Review the displayed scope and limits before starting. Results are linked from queue rows. The service shows when it is processing, waiting for allowance, retrying, or watching for new mail.

## Stop and restart

Press Ctrl+C in the terminal to stop. Start the same launcher again and use the newly printed URL. Non-secret settings and reports remain in the project folder; keys and passwords entered in the browser must be entered again after restart. Keep the extracted project folder to preserve your settings.

For unattended operation and secret environment variables, see [OPERATIONS.md](OPERATIONS.md). For the optional terminal setup, run `python3 -m sentinel setup` (`py -3 -m sentinel setup` on Windows) before starting the server. Existing settings are not overwritten by that wizard.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named sentinel` | Open the folder containing the `sentinel` subfolder and `pyproject.toml`, then run the command again. |
| Missing `tomllib` | The interpreter is older than Python 3.11. Check its version and install a supported one. |
| Address already in use | Stop the previous instance, or run `python3 -m sentinel serve --port 8766` (`py -3` on Windows). |
| Unauthorized / empty queue | Open the complete current URL from the terminal. A previous session's token will not work. |
| Connection refused | Start the local AI server, load a model and check the endpoint and port. |
| Native tool call test fails | Check the exact model ID and whether the model/server supports native tool calls. An ordinary chat response does not satisfy this test. |
| External processing denied | Save the external-processing setting, supply a key, preview outgoing data and confirm consent. |
| IMAP login fails | Check host, username and password/app-password. Ask the mail administrator whether password-based IMAP is enabled. |

The service is local to the computer running it. Use its browser; opening the address on a phone will not reach the desktop application.

[Check rules / Pravidla kontrol](CHECKS.md) · [Queue / Fronta](QUEUE.md) · [MCP](MCP.md)


## Organization requirements and SQL evidence

Enter your requirements in **Check rules → Investigation requirements**. Configure **Agent extensions → Database evidence queries** using the [SQLite](../examples/data-sources.sqlite.json) or [PostgreSQL](../examples/data-sources.postgresql.json) example. Use your own tables, columns and parameter meanings. Saved queries appear in Check rules.

Disable local vendor-adapter checks you do not use and configure the new query modes. Store PostgreSQL credentials in the configured environment variable; enter only its name in the source document. Database permissions are administered on the database server. See [data sources](DATA-SOURCES.md).

## Configuration checks and backups

Run `python3 -m sentinel check` (`py -3 -m sentinel check` on Windows) from the extracted folder. It checks configured extensions and required local evidence without sending email to AI. Follow any failing checks, then verify the model connection in Settings.

Only one process can use the same data folder. Stop the existing process before restarting. If the HTTP port belongs to another application, choose another port with `serve --port 8766`.

Use `python3 -m sentinel backup backup.sqlite3` (`py -3` on Windows) to save reports and queue state. The file must not already exist. See [backup and restoration](OPERATIONS.md).

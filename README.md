# Mail Sentinel

A local AI agent for investigating suspicious email. The model selects evidence tools and produces a report with references, missing checks and recommendations. Mailbox changes require separate human approval.

**Version 1.0.0rc2 — release candidate.** [Česky](README.cs.md)

## Start in minutes

1. On [GitHub](https://github.com/mediatoring/mail-sentinel), choose **Code → Download ZIP**, then extract the entire archive. The folder is usually named `mail-sentinel-main`.
2. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/) if needed.
3. Windows: double-click `START.bat`. macOS/Linux: open a terminal in the extracted folder and run `sh start.sh`.
4. Keep the terminal open. Open the **complete local address** it prints, including `#token=…`.
5. Follow the [AI setup walkthrough](docs/INSTALL.md#your-first-local-ai-model), verify the connection in Settings, then investigate a sample message. You do not need a mailbox or an API key for local AI.

On macOS, subsequent openings can use **Open Mail Sentinel.command**; it uses an existing virtual environment or Python 3.11+ and opens the current session. After restarting the service, reconnect using the launcher or the newly printed address; an old bookmarked session token no longer works.

[Installation and troubleshooting](docs/INSTALL.md) · [User guide](docs/USER-GUIDE.md) · [Security boundaries](SECURITY.md)

## Development and evaluation

```sh
python3 -m unittest discover -s tests -v
python3 -m evaluation.full_eval --config sentinel.toml
```

The first command checks application behavior. The second runs **all 28 live scenarios**, including multilingual and adversarial cases; it requires a configured model. It reports completion, guard behavior and expected findings separately. External AI additionally requires `--allow-external`. Optional AgentDojo adapter tests require `evaluation/requirements.txt`; frontend tests use `jsdom@26`. See [validation](docs/VALIDATION.md).

[Architecture and harness](docs/HARNESS.md) · [Specialists and reviewed memory](docs/SKILLS-AND-SUBAGENTS.md) · [Developer guide](docs/DEVELOPMENT.md) · [Changelog](CHANGELOG.md)

LOW_RISK means no identified concern in the performed checks, not proof of safety or payment approval. The application does not independently authenticate senders or scan attachment contents for malware. Pseudonymization is best effort.

MIT · Michal Kubíček · [Mediatoring](https://mediatoring.cz/en/cybersecurity/)

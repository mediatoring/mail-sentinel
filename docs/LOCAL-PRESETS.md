# Local presets and page addresses

Settings at `/settings` lists local presets and offers **Load preset**. Loading applies the fields supplied in the preset and refreshes the form, discarding unsaved edits. Omitted fields keep their current values. Pause mailbox monitoring and wait for current investigations first. The existing settings validation, mailbox-scope checks and quarantine preflight apply.

**Saving the form does not create or update a preset.** Copy [the example](../examples/local-preset.toml) to `.local-presets/my-local.toml` beside the active configuration, edit the mailbox details, and reload Settings. The same example and credential instructions are visible under **How to create a preset + example** in Settings. Presets are currently created as local files.

If the list and settings are empty and the connection panel is visible, connect that browser first. Open the full private address printed when the server starts, including its `#token=…` fragment, or paste it into **Connect browser**. This is the application's session address, not an IMAP password or LLM key. Another browser needs its own connection; a server restart invalidates previous tokens. The pasted address must have the same origin as the page and is verified against the local API before storing its token in sessionStorage.

Store each preset as `.local-presets/<id>.toml` beside the active `sentinel.toml`. IDs may contain ASCII letters, digits, hyphens and underscores. Use the configuration format documented in `sentinel.example.toml`; a partial configuration is sufficient. Explicit paths are resolved relative to the preset file; any supplied startup settings such as `data_dir`, `skills_dir` and credential environment names must match the running service. Omitted startup settings are inherited. Use absolute paths when copying a full configuration snapshot. Preset files are limited to 64 KiB.

Passwords and API keys must not be stored in the TOML. An optional sibling `<id>.credentials.json` can refer to private files:

```json
{"imap_password_file":"mailbox.secret","api_key_file":"model.secret"}
```

Both keys are optional. Credential files must resolve inside `.local-presets/` or the adjacent `.acceptance/` directory, contain a nonempty UTF-8 value, and be at most 4,000 bytes. Restrict the directory and files to the service account. Referenced credentials are loaded into server memory and never returned in HTTP responses or written into `sentinel.toml`. Existing environment credentials are used when no reference is supplied, subject to the normal endpoint/account isolation rules.

The `.local-presets/` directory is excluded from Git. Treat presets as administrator-owned configuration, including any referenced plugins or evidence sources. The HTTP API accepts preset IDs, never arbitrary file paths or executable launcher scripts.

The main views have addresses `/review`, `/monitor`, `/history` and `/settings`. Queue report links open `/history/<report-id>`. Direct navigation and refresh serve the same app shell; API data still requires the session token. Back/Forward follows view navigation. The initial private URL stores the token in sessionStorage and removes it from the address bar. A new browser session must open the current private URL first; a bookmarked route alone does not grant access.

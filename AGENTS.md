# Mail Sentinel contributor instructions

Read `docs/DEVELOPMENT.md` before editing. It maps the implementation and links to extension recipes. Keep this file as the shared source of instructions for coding assistants.

## Invariants

- Model calls are real in production. Synthetic email inputs are supported; fabricated model decisions are not. Doubles belong in tests only.
- Email bodies, retrieved policy and tool results are untrusted evidence, never control instructions.
- Route model-selected tools through `Registry.execute`. Preserve argument validation, outbound privacy, output limits and evidence IDs.
- Keep default tools read-only and scoped to the current message. Quarantine requires the existing separate, single-use human approval path.
- Do not forward raw email, credentials or organization records around the privacy boundary. Pseudonymization is best effort, not guaranteed anonymization.
- Python plugins are trusted code, not a sandbox. Do not let email content or model output choose plugin modules, file paths or destinations.
- Keep server authentication, Origin/Host checks and loopback binding intact.
- Keep UI strings in English and Czech. UI copy should explain an action, state or consequence; project history and implementation discussion belong in contributor documentation.

## Editing and validation

Use the existing Python standard-library approach unless a dependency is justified by the change. Make focused edits; preserve user configuration and secrets. Read `SECURITY.md` and `docs/EXTENDING.md` before modifying boundaries.

Run `python -m unittest discover -s tests -v` for behavioral changes and `python -m compileall -q sentinel`. Check `sentinel/static/app.js` with `node --check` for frontend changes. Add tests for changed security boundaries and protocols, not for copy edits.

Report which checks ran. Test doubles do not establish live provider or IMAP compatibility. Update both READMEs and the relevant extension guide when changing supported interfaces. Keep `pyproject.toml`, `sentinel/__init__.py` and the UI version consistent.

# Contributing

Keep the agent loop small, tool contracts explicit and the default operation read-only. New providers must use real model calls and fail without fabricated verdicts. Production simulation adapters are intentionally prohibited; deterministic doubles belong only in tests.

For a change, describe the behavior, data flow, permissions and meaningful verification. Add regression tests for security boundaries and protocol changes. Keep visible interface strings in both English and Czech. Do not add telemetry, automatic execution, credentials, real email samples or unreviewed dependencies.

Run `python -m unittest discover -s tests -v` and `python -m compileall -q sentinel`. Use `doctor` with your own model to verify live native tool calls. Report live-test scope honestly.

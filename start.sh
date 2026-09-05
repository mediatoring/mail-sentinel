#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required. See docs/INSTALL.md (or docs/INSTALL.cs.md)." >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11+ is required. Upgrade Python, then run this launcher again." >&2
  exit 1
fi
exec python3 -m sentinel serve

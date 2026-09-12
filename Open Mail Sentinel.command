#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    sentinel_python=.venv/bin/python
else
    sentinel_python=python3
fi
if ! "$sentinel_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo 'Python 3.11+ is required. Install from python.org; see docs/INSTALL.md or docs/INSTALL.cs.md.'
    exit 1
fi
exec "$sentinel_python" -m sentinel open "$@"

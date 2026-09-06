#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo 'First install Mail Sentinel using the README instructions.'
    read -r _reply
    exit 1
fi
exec .venv/bin/python -m sentinel open

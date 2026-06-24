#!/usr/bin/env bash
set -euo pipefail
python3 -m py_compile src/dockhand/cli.py
PYTHONPATH=src python3 -m dockhand.cli \
  --project-name dockhand-smoke \
  --application-name sample-api \
  --setting-name port \
  --start-port 41000 \
  --end-port 41010 \
  --reserved-ports-file /tmp/dockhand-smoke-reserved.json \
  --json

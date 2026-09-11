#!/usr/bin/env bash
# Run the WikiArt Data API with uvicorn on 127.0.0.1.
# Port comes from WIKIART_API_PORT (default 8001).
# exec keeps uvicorn as PID 1 so signals pass through (systemd-friendly).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

exec "$SCRIPT_DIR/.venv/bin/uvicorn" api.main:app \
  --host 127.0.0.1 --port "${WIKIART_API_PORT:-8001}" --log-level info
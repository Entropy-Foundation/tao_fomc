#!/usr/bin/env bash
set -euo pipefail

# Runs the FOMC RSS monitor and launches the Supra integration test with the
# resulting announcement link.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

link_output="$($PYTHON_BIN "$SCRIPT_DIR/fomc_rss_feed.py" "$@" | tail -n 1 | tr -d '\r')"

if [[ -z "$link_output" ]]; then
  echo "Error: No link received from fomc_rss_feed.py" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/integration_test.py" "$link_output"

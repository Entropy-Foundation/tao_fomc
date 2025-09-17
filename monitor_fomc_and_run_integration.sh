#!/usr/bin/env bash
set -euo pipefail

# Runs the FOMC RSS monitor and launches the Supra integration test with the
# resulting announcement link.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

test_latest=0
declare -a monitor_args=()

for arg in "$@"; do
  case "$arg" in
    --test-latest)
      test_latest=1
      ;;
    *)
      monitor_args+=("$arg")
      ;;
  esac
done

if [[ $test_latest -eq 1 ]]; then
  monitor_args+=("--test-latest")
fi

link_output="$($PYTHON_BIN "$SCRIPT_DIR/fomc_rss_feed.py" "${monitor_args[@]}" | tail -n 1 | tr -d '\r')"

if [[ -z "$link_output" ]]; then
  echo "Error: No link received from fomc_rss_feed.py" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/threshold_integration_supra.py" "$link_output"

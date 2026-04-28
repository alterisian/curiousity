#!/usr/bin/env bash
set -euo pipefail
# run_live_tests.sh — lightweight wrapper to source .envrc (when direnv isn't active)
# and run the live test suite. This does not modify test_harness.py.

ROOT_DIR=$(dirname -- "${BASH_SOURCE[0]}")
cd "$ROOT_DIR"

# If .envrc exists, source it to populate variables.
if [ -f .envrc ]; then
  # Export any variables defined in .envrc into the environment for this script.
  # This handles files that contain assignments but not `export` statements.
  set -a
  # shellcheck disable=SC1091
  source .envrc
  set +a
fi

if [ -z "${MISTRAL_API_KEY:-}" ]; then
  echo "MISTRAL_API_KEY is not set. You can set it in .envrc or export it in your shell."
  exit 1
fi

echo "Running live tests with MISTRAL_API_KEY set (CURIOSITY_LIVE_API=1)"
CURIOSITY_LIVE_API=1 python3 test_harness.py

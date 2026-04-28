#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(dirname -- "${BASH_SOURCE[0]}")/..
cd "$ROOT_DIR"
if [ -f .envrc ]; then
  set -a
  # shellcheck disable=SC1091
  source .envrc
  set +a
fi
if [ -z "${MISTRAL_API_KEY:-}" ]; then
  echo "MISTRAL_API_KEY not set. Set it in .envrc or export it." >&2
  exit 1
fi
python3 web/run_malaga.py "$@"

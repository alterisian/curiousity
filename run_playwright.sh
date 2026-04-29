#!/usr/bin/env bash
set -euo pipefail
ROOT=$(dirname -- "$0")
cd "$ROOT"
echo "Installing dev requirements (you may skip if already installed)..."
python3 -m pip install -r requirements-dev.txt
echo "Installing playwright browsers..."
python3 -m playwright install chromium
echo "Running playwright pytest..."
pytest -q tests/test_grid_visible.py::test_grid_shows_nodes

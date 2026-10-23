#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "Using active virtual environment: $VIRTUAL_ENV"
elif [[ -f ".venv/bin/activate" ]]; then
  source ".venv/bin/activate"
elif [[ -f "venv/bin/activate" ]]; then
  source "venv/bin/activate"
else
  echo "No Python virtual environment found. Create .venv or venv first." >&2
  exit 1
fi

exec python run.py
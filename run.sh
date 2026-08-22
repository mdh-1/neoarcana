#!/usr/bin/env bash
# Run Neoarcana locally. First run sets up the venv; later runs just start.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
PORT="${PORT:-8001}"

# A virtualenv bakes absolute paths into its scripts, so moving or
# renaming the project directory leaves .venv/bin/* present but broken.
# Check that it actually runs, not just that it exists.
if [ ! -x .venv/bin/uvicorn ] || ! .venv/bin/python -c "" 2>/dev/null; then
  [ -e .venv ] && echo "Virtualenv is stale (project moved?) — rebuilding..." && rm -rf .venv
  echo "Creating virtualenv and installing dependencies..."
  "$PYTHON" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "No .env found — running keyless (local entropy + mock interpreter)."
  echo "Copy .env.example to .env and add keys for real readings."
fi

echo "Neoarcana → http://localhost:$PORT"
exec .venv/bin/uvicorn app.main:app --reload --port "$PORT"

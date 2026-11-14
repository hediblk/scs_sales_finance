#!/usr/bin/env bash
# Starts the Chrome & Oak prototype on Mac / Linux: API on :8000, UI on :5173.
# First run: installs the Python and Node dependencies and asks for the Anthropic API key
# (saved to .env next to this script; .env is gitignored and never committed).
set -e
cd "$(dirname "$0")"
if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env 2>/dev/null; then
  read -r -s -p "Anthropic API key (saved to .env, never committed): " KEY; echo
  printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" > .env
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -q -r api/requirements.txt
fi
[ -d ui/node_modules ] || (cd ui && npm install)
.venv/bin/python -m uvicorn api.main:app --port 8000 &
API_PID=$!
trap 'kill $API_PID' EXIT
echo "API on http://localhost:8000, UI on http://localhost:5173"
cd ui && npm run dev

#!/usr/bin/env bash
# Starts the Chrome & Oak prototype on Mac / Linux: API on :8000, UI on :5173.
# First run installs the Python and Node dependencies.
set -e
cd "$(dirname "$0")"
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

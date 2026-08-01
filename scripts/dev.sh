#!/usr/bin/env bash
# Start main API (8000) and LLM service (8001). Run from repo root or anywhere.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV_PY="$BACKEND/venv/bin/python3"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtual env not found. Run:"
  echo "  cd $BACKEND && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "$BACKEND/.env" ]]; then
  echo "Missing $BACKEND/.env — copy .env.example to .env and set your keys."
  exit 1
fi

cd "$BACKEND"

cleanup() {
  trap - EXIT INT TERM
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${LLM_PID:-}" ]] && kill "$LLM_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting LLM service on http://127.0.0.1:8001 ..."
"$VENV_PY" -m uvicorn LLM_Model.llm_service:app --host 127.0.0.1 --port 8001 --reload &
LLM_PID=$!

echo "Starting API on http://127.0.0.1:8000 ..."
"$VENV_PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "Press Ctrl+C to stop both."
wait

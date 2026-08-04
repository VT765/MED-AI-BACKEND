#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Med-AI Dev Runner
# Starts ALL three services with a single command:
#   1. Frontend  (Vite)          → http://localhost:5173
#   2. Backend   (FastAPI/8000)  → http://127.0.0.1:8000
#   3. LLM Model (FastAPI/8001)  → http://127.0.0.1:8001
#
# Usage:   ./scripts/dev.sh          (from repo root)
#          bash scripts/dev.sh       (from repo root)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Resolve paths ────────────────────────────────────────────
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV_PY="$BACKEND/venv/bin/python3"

# Frontend lives in a sibling directory
FRONTEND_ROOT="$ROOT/../med-ai frontend/MED-AI/frontend-vite"

# ── Colors for log prefixes ──────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
MAGENTA='\033[0;35m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ── Pre-flight checks ───────────────────────────────────────
echo -e "${YELLOW}╔══════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║        Med-AI Dev Environment        ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════╝${NC}"
echo ""

# 1. Python venv
if [[ ! -x "$VENV_PY" ]]; then
  echo -e "${RED}✗ Python virtual env not found at $BACKEND/venv${NC}"
  echo "  Run:"
  echo "    cd $BACKEND && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi
echo -e "${GREEN}✓ Python venv found${NC}"

# 2. .env file
if [[ ! -f "$BACKEND/.env" ]]; then
  echo -e "${RED}✗ Missing $BACKEND/.env${NC}"
  echo "  Copy .env.example to .env and set your keys."
  exit 1
fi
echo -e "${GREEN}✓ Backend .env found${NC}"

# 3. Frontend node_modules
if [[ ! -d "$FRONTEND_ROOT/node_modules" ]]; then
  echo -e "${RED}✗ Frontend node_modules not found.${NC}"
  echo "  Run:"
  echo "    cd \"$FRONTEND_ROOT\" && npm install"
  exit 1
fi
echo -e "${GREEN}✓ Frontend node_modules found${NC}"

echo ""

# ── Cleanup on exit ─────────────────────────────────────────
FRONTEND_PID=""
API_PID=""
LLM_PID=""

cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo -e "${YELLOW}Shutting down all services...${NC}"
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$API_PID" ]]      && kill "$API_PID"      2>/dev/null || true
  [[ -n "$LLM_PID" ]]      && kill "$LLM_PID"      2>/dev/null || true
  wait 2>/dev/null || true
  echo -e "${GREEN}All services stopped.${NC}"
}
trap cleanup EXIT INT TERM

# ── Start LLM Service (port 8001) ───────────────────────────
echo -e "${MAGENTA}🧠 Starting LLM Service → http://127.0.0.1:8001${NC}"
cd "$BACKEND"
"$VENV_PY" -m uvicorn LLM_Model.llm_service:app \
  --host 127.0.0.1 --port 8001 --reload \
  2>&1 | sed "s/^/$(printf "${MAGENTA}[LLM]${NC} ")/" &
LLM_PID=$!

# ── Start Backend API (port 8000) ───────────────────────────
echo -e "${CYAN}🚀 Starting Backend API → http://127.0.0.1:8000${NC}"
"$VENV_PY" -m uvicorn main:app \
  --host 127.0.0.1 --port 8000 --reload \
  2>&1 | sed "s/^/$(printf "${CYAN}[API]${NC} ")/" &
API_PID=$!

# ── Start Frontend (Vite dev server, port 5174) ─────────────
echo -e "${GREEN}⚡ Starting Frontend    → http://localhost:5174${NC}"
cd "$FRONTEND_ROOT"
npx vite --port 5174 --host 2>&1 | sed "s/^/$(printf "${GREEN}[FE]${NC}  ")/" &
FRONTEND_PID=$!

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ⚡ Frontend${NC}   → http://localhost:5174"
echo -e "${CYAN}  🚀 Backend${NC}    → http://127.0.0.1:8000"
echo -e "${MAGENTA}  🧠 LLM Model${NC}  → http://127.0.0.1:8001"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Press ${RED}Ctrl+C${NC} to stop all services."
echo ""

wait

#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/harsha/Downloads/optimal-market-maker-avellaneda-stoikov"

if ! ss -ltn | grep -q ':8000 '; then
  cd "$ROOT"
  source .venv/bin/activate
  nohup uvicorn api.server:app --host 127.0.0.1 --port 8000 >/tmp/omm_backend.log 2>&1 &
fi

if ! ss -ltn | grep -q ':5173 '; then
  export NVM_DIR="$HOME/.nvm"
  source "$NVM_DIR/nvm.sh"
  cd "$ROOT/frontend"
  nohup npm run dev -- --host 127.0.0.1 --port 5173 >/tmp/omm_frontend.log 2>&1 &
fi

sleep 1
ss -ltnp | grep -E ':5173|:8000' || true
echo "Open: http://127.0.0.1:5173"

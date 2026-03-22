#!/usr/bin/env bash
set -euo pipefail
pkill -f "uvicorn api.server:app" || true
pkill -f "vite --host 127.0.0.1 --port 5173" || true
sleep 1
ss -ltnp | grep -E ':5173|:8000' || true
echo "Stopped local dev services."

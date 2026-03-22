#!/usr/bin/env bash
set -euo pipefail
ss -ltnp | grep -E ':5173|:8000' || true
echo "Backend log: /tmp/omm_backend.log"
echo "Frontend log: /tmp/omm_frontend.log"

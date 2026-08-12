#!/usr/bin/env bash
# Plan 07-005 — canary traffic + drain-safe agent restart
set -euo pipefail

PERCENT="${1:-10}"
BASE="${SPEAKSY_UI:-http://127.0.0.1:8000}"

echo "[canary] setting ENGINE_CANARY_PERCENT=$PERCENT (export in .env / process env)"
export ENGINE_CANARY_PERCENT="$PERCENT"

echo "[canary] waiting for active calls to drain…"
for i in $(seq 1 120); do
  active=$(curl -sf "$BASE/api/health/active-calls" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active',0))" 2>/dev/null || echo "?")
  echo "  active=$active (try $i)"
  if [ "$active" = "0" ]; then
    break
  fi
  sleep 5
done

echo "[canary] restart agent process (supervisord / docker compose)"
if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ]; then
  docker compose restart agent || true
fi
echo "[canary] done — monitor is_canary in call extracted_info / logs"

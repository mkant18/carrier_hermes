#!/usr/bin/env bash
# External watchdog (outside Hermes). Alert if Vigil heartbeat is stale.
set -euo pipefail
HB="$HOME/.hermes/carrier/VIGIL_HEARTBEAT"
WEBHOOK="${CARRIER_ALERTS_WEBHOOK:-}"
if [[ ! -f "$HB" ]]; then
  msg="Carrier Hermes: no Vigil heartbeat file yet"
else
  # macOS stat
  mtime=$(stat -f %m "$HB" 2>/dev/null || stat -c %Y "$HB")
  now=$(date +%s)
  age=$((now - mtime))
  if [[ "$age" -lt 720 ]]; then
    exit 0
  fi
  msg="Carrier Hermes: Vigil heartbeat stale (${age}s)"
fi
echo "$msg"
if [[ -n "$WEBHOOK" ]]; then
  curl -sS -X POST -H 'Content-Type: application/json' \
    -d "{\"content\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$msg")}" \
    "$WEBHOOK" >/dev/null || true
fi

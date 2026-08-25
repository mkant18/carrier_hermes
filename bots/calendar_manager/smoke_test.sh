#!/usr/bin/env bash
# Smoke: Chronos home has google-workspace skill + calendar gate + optional live read.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${HERMES_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
GAPI="$ROOT/scripts/gapi_fleet.py"
HOME_P="$HOME/.hermes/profiles/calendar_manager"

echo "=== calendar_manager (Chronos) google wire smoke ==="

[[ -f "$ROOT/bots/calendar_manager/SOUL.md" ]] && [[ -f "$HOME_P/SOUL.md" ]] && echo "PASS soul" || { echo "FAIL soul"; exit 1; }
[[ -e "$HOME_P/skills/productivity/google-workspace/SKILL.md" ]] && echo "PASS skill_linked" || { echo "FAIL skill_linked"; exit 1; }
[[ -e "$HOME_P/google_client_secret.json" ]] && echo "PASS client_secret_link" || { echo "FAIL client_secret_link"; exit 1; }

# mail must be blocked for chronos
set +e
"$PY" "$GAPI" chronos gmail search 'is:unread' >/tmp/chronos_mail_block.out 2>&1
rc=$?
set -e
[[ $rc -ne 0 ]] && echo "PASS mail_blocked (rc=$rc)" || { echo "FAIL mail_blocked"; exit 1; }

if [[ -f "$HOME/.hermes/google_token.json" ]]; then
  export HERMES_HOME="$HOME/.hermes"
  set +e
  "$PY" "$GAPI" chronos calendar list >/tmp/chronos_cal_smoke.out 2>&1
  crc=$?
  set -e
  if [[ $crc -eq 0 ]]; then
    echo "PASS calendar_read_smoke"
  else
    echo "WARN calendar_read_smoke rc=$crc (token present but API failed — see /tmp/chronos_cal_smoke.out)"
  fi
else
  echo "SKIP calendar_read_smoke (no token — run scripts/google_personal_oauth.py)"
fi

echo "=== calendar_manager smoke done ==="

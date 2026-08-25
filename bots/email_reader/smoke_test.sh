#!/usr/bin/env bash
# Smoke: Inbox home has google-workspace skill + no-send gate + optional live read.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${HERMES_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
GAPI="$ROOT/scripts/gapi_fleet.py"
HOME_P="$HOME/.hermes/profiles/email_reader"

echo "=== email_reader (Inbox) google wire smoke ==="

[[ -f "$ROOT/bots/email_reader/SOUL.md" ]] && [[ -f "$HOME_P/SOUL.md" ]] && echo "PASS soul" || { echo "FAIL soul"; exit 1; }
[[ -e "$HOME_P/skills/productivity/google-workspace/SKILL.md" ]] && echo "PASS skill_linked" || { echo "FAIL skill_linked"; exit 1; }
[[ -e "$HOME_P/google_client_secret.json" ]] && echo "PASS client_secret_link" || { echo "FAIL client_secret_link"; exit 1; }

# send must hard-fail
set +e
"$PY" "$GAPI" inbox gmail send --to x@y.z --subject s --body b >/tmp/inbox_send_block.out 2>&1
rc=$?
set -e
[[ $rc -ne 0 ]] && echo "PASS send_blocked (rc=$rc)" || { echo "FAIL send_blocked"; exit 1; }

if [[ -f "$HOME/.hermes/google_token.json" ]]; then
  export HERMES_HOME="$HOME/.hermes"
  set +e
  "$PY" "$GAPI" inbox gmail search 'newer_than:14d' --max 1 >/tmp/inbox_gmail_smoke.out 2>&1
  grc=$?
  set -e
  if [[ $grc -eq 0 ]]; then
    echo "PASS gmail_read_smoke"
  else
    echo "WARN gmail_read_smoke rc=$grc (token present but API failed — see /tmp/inbox_gmail_smoke.out)"
  fi
else
  echo "SKIP gmail_read_smoke (no token — run scripts/google_personal_oauth.py)"
fi

echo "=== email_reader smoke done ==="

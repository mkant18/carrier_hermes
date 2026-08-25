#!/usr/bin/env bash
# Wire personal Gmail + Calendar onto Inbox (email_reader) and Chronos (calendar_manager).
# Safe: no mail send path; OAuth scopes exclude gmail.send.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_ROOT="${HERMES_ROOT:-$HOME/.hermes}"
SKILL_SRC="$HERMES_ROOT/skills/productivity/google-workspace"
PY="${HERMES_PYTHON:-$HERMES_ROOT/hermes-agent/venv/bin/python}"
OAUTH="$ROOT/scripts/google_personal_oauth.py"
GAPI="$ROOT/scripts/gapi_fleet.py"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -x "$PY" || -f "$PY" ]] || die "Hermes python not found at $PY"
[[ -d "$SKILL_SRC" ]] || die "google-workspace skill missing at $SKILL_SRC"
[[ -f "$HERMES_ROOT/google_client_secret.json" ]] || die "Missing $HERMES_ROOT/google_client_secret.json — place Desktop OAuth client JSON there first"

echo "=== wire personal Google Workspace (Inbox + Chronos) ==="

# 1) deps
"$PY" "$OAUTH" --install-deps

# 2) install skill into consumer profiles (symlink; stay current with shared skill)
for bot in email_reader calendar_manager; do
  dest="$HOME/.hermes/profiles/$bot/skills/productivity"
  mkdir -p "$dest"
  link="$dest/google-workspace"
  if [[ -L "$link" || -e "$link" ]]; then rm -rf "$link"; fi
  ln -s "$SKILL_SRC" "$link"
  echo "OK skill -> $link"
done

# 3) symlink shared secret (+ token if present) into profile homes
"$PY" "$OAUTH" --sync-profiles

# 4) enable narrow terminal so agents can run gapi_fleet / google_api
#    (SOUL documents allowed commands only; gapi_fleet.py enforces no-send)
for bot in email_reader calendar_manager; do
  hermes -p "$bot" tools enable terminal skills file memory session_search clarify todo kanban --platform cli >/dev/null 2>&1 || true
  # keep dangerous MCP off
  for srv in todoist hugging_face kiwi vercel dropbox obsidian-second-brain; do
    hermes -p "$bot" config set "mcp_servers.${srv}.enabled" false --force >/dev/null 2>&1 || true
  done
  echo "OK tools terminal+skills on $bot"
done

# 5) auth status
set +e
"$PY" "$OAUTH" --check
auth_rc=$?
set -e

if [[ $auth_rc -ne 0 ]]; then
  echo ""
  echo "OAUTH_REQUIRED: Michael must complete one browser consent (personal Gmail+Calendar only)."
  echo "Steps:"
  echo "  1) $PY $OAUTH --auth-url"
  echo "  2) Open printed URL; approve personal account only (never firm/Paul Weiss)."
  echo "  3) Browser fails on http://localhost:1 — expected. Copy full redirect URL."
  echo "  4) $PY $OAUTH --auth-code 'PASTE_URL_OR_CODE'"
  echo "  5) $PY $OAUTH --check && $PY $OAUTH --sync-profiles"
  echo "  6) Smoke:"
  echo "       HERMES_HOME=$HERMES_ROOT $PY $GAPI inbox gmail search 'newer_than:7d' --max 3"
  echo "       HERMES_HOME=$HERMES_ROOT $PY $GAPI chronos calendar list"
  exit 2
fi

echo "=== AUTHENTICATED — running read smokes (no send) ==="
export HERMES_HOME="$HERMES_ROOT"
set +e
"$PY" "$GAPI" inbox gmail search 'newer_than:7d' --max 3
inbox_rc=$?
"$PY" "$GAPI" chronos calendar list
cal_rc=$?
# prove send is blocked
"$PY" "$GAPI" inbox gmail send --to nobody@example.com --subject x --body y >/tmp/gapi_send_block.out 2>&1
send_rc=$?
set -e

echo "smoke inbox_rc=$inbox_rc cal_rc=$cal_rc send_block_rc=$send_rc (want send_block != 0)"
[[ $send_rc -ne 0 ]] || die "send path was NOT blocked"
[[ $inbox_rc -eq 0 ]] || die "gmail read smoke failed"
[[ $cal_rc -eq 0 ]] || die "calendar read smoke failed"

echo "=== wire_google_personal PASS ==="

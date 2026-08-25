#!/usr/bin/env bash
# Append one JSON line to the vault audit log. Never rewrite.
set -euo pipefail
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
AUDIT="$VAULT/_agent/audit/events.jsonl"
mkdir -p "$(dirname "$AUDIT")"
agent="${1:-unknown}"
event="${2:-event}"
detail="${3:-}"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# minimal JSON escape
json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
line=$(printf '{"ts":%s,"agent":%s,"event":%s,"detail":%s}\n' \
  "$(json_escape "$ts")" "$(json_escape "$agent")" "$(json_escape "$event")" "$(json_escape "$detail")")
printf '%s' "$line" >>"$AUDIT"
echo "$AUDIT"

#!/usr/bin/env bash
# osb — thin wrapper around mcp_call.py for the obsidian-second-brain MCP server.
# Defaults to the vault_librarian home (read-only). Override with CARRIER_OSB_PROFILE.
#
# Examples:
#   bash osb.sh search "Harvard Law" 5
#   bash osb.sh read "Archive/claude-ai/conversations/....md"
#   bash osb.sh health
#   bash osb.sh list                         # tools available to this home
#   CARRIER_OSB_PROFILE=obsidian_archivist bash osb.sh save "Title" "Body"   # Clerk write
set -euo pipefail
HPY="${HERMES_PYTHON:-C:/Users/micha/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# normalize MSYS path for native python
case "$HERE" in /?/*) d="${HERE:1:1}"; HERE="${d^^}:/${HERE:3}";; esac
CALL="$HERE/mcp_call.py"
PROFILE="${CARRIER_OSB_PROFILE:-vault_librarian}"
export OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-C:/Users/micha/Documents/Obsidian Vault}"

sub="${1:-}"; shift || true
case "$sub" in
  search)  q="${1:-}"; lim="${2:-6}"; args="{\"query\": $(printf '%s' "$q" | "$HPY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))'), \"limit\": $lim}"; tool=obsidian_search ;;
  read)    p="${1:-}"; args="{\"path\": $(printf '%s' "$p" | "$HPY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}"; tool=obsidian_read_note ;;
  health)  args='{}'; tool=obsidian_vault_health ;;
  backlinks) t="${1:-}"; args="{\"target\": $(printf '%s' "$t" | "$HPY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}"; tool=obsidian_backlinks ;;
  list)    exec "$HPY" "$CALL" --profile "$PROFILE" --server obsidian-second-brain --list ;;
  save)    ti="${1:-}"; bo="${2:-}"; args="{\"title\": $(printf '%s' "$ti" | "$HPY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))'), \"content\": $(printf '%s' "$bo" | "$HPY" -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}"; tool=obsidian_save_note ;;
  *) echo "usage: osb.sh {search <q> [limit]|read <path>|health|backlinks <note>|list|save <title> <body>}" >&2; exit 2 ;;
esac
exec "$HPY" "$CALL" --profile "$PROFILE" --server obsidian-second-brain --tool "$tool" --args "$args"

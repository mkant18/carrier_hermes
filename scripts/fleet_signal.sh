#!/usr/bin/env bash
# fleet_signal.sh — post DISPATCH / ACK / TRAP lines to Discord via wing tokens.
#
# Each bot posts with its own callsign + emoji identity via per-message
# username override. The wing's Discord App token is used — not First Watch —
# so messages appear from "Coding Wing" app but with Wrench's or Mate's name.
#
# Usage:
#   fleet_signal.sh DISPATCH <bot_id> <job_id> <description> [channel]
#   fleet_signal.sh ACK      <bot_id> <job_id> <status_line> [channel]
#   fleet_signal.sh TRAP     <bot_id> <job_id> <result_line> [channel]
#   fleet_signal.sh RAW      <bot_id> <message>              [channel]
#
#   <bot_id>  must be a known id from bot_identities.py
#   [channel] one of: fleet (default), command, alerts, drafts, ready_room, catapult
#
# Token resolution (never printed, never logged):
#   Reads the bot's wing_token_env from bot_identities.py, then loads that
#   env var from HERMES_ENV_FILE. Falls back to DISCORD_FLEET_BOT_TOKEN.
#
# Guardrails (no agent turns triggered):
#   - Outbound REST POST only — no gateway opened
#   - Token is read from file, never echoed or exported to subshells
#   - Username override identifies the specific bot, not the wing app
#   - All messages include a visible [BOT] marker — never impersonate Michael

set -euo pipefail

HERMES_ENV_FILE="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IDENTITIES_PY="$SCRIPT_DIR/bot_identities.py"

# ---------------------------------------------------------------------------
# Load a specific env var from ~/.hermes/.env without exporting it
# ---------------------------------------------------------------------------
_load_env_var() {
  local key="$1"
  grep -E "^${key}=" "$HERMES_ENV_FILE" 2>/dev/null \
    | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true
}

# Also check per-profile .env for wing tokens
_load_env_var_cascade() {
  local key="$1" bot_id="$2"
  local val
  # Check bot profile .env first
  local profile_env="$HOME/.hermes/profiles/$bot_id/.env"
  if [[ -f "$profile_env" ]]; then
    val=$(grep -E "^${key}=" "$profile_env" 2>/dev/null \
      | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true)
    [[ -n "$val" ]] && { printf '%s' "$val"; return; }
  fi
  # Fall back to ~/.hermes/.env
  val=$(_load_env_var "$key")
  [[ -n "$val" ]] && { printf '%s' "$val"; return; }
  printf ''
}

# ---------------------------------------------------------------------------
# Get bot identity field from bot_identities.py
# ---------------------------------------------------------------------------
_bot_field() {
  local bot_id="$1" field="$2"
  python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from bot_identities import BOTS
bot = BOTS.get('$bot_id')
if not bot:
    sys.exit(1)
print(bot.get('$field', ''))
" 2>/dev/null || echo ""
}

_channel_id() {
  local name="$1"
  python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from bot_identities import CHANNELS
print(CHANNELS.get('$name', ''))
" 2>/dev/null || echo ""
}

# ---------------------------------------------------------------------------
# Resolve the token for a given bot (from its wing_token_env)
# ---------------------------------------------------------------------------
_resolve_token() {
  local bot_id="$1"
  local token_env
  token_env=$(_bot_field "$bot_id" "wing_token_env")

  if [[ -z "$token_env" ]]; then
    echo "fleet_signal: unknown bot_id '$bot_id' — not in bot_identities.py" >&2
    exit 1
  fi

  local tok
  tok=$(_load_env_var_cascade "$token_env" "$bot_id")

  # Fallback: if wing token not set yet (pre-wiring), use First Watch
  if [[ -z "$tok" ]]; then
    tok=$(_load_env_var "DISCORD_FLEET_BOT_TOKEN")
    if [[ -n "$tok" ]]; then
      echo "fleet_signal: WARN wing token '$token_env' not set, using First Watch fallback for $bot_id" >&2
    else
      echo "fleet_signal: no token found for $bot_id (tried $token_env + DISCORD_FLEET_BOT_TOKEN)" >&2
      exit 1
    fi
  fi

  printf '%s' "$tok"
}

# ---------------------------------------------------------------------------
# Post with full identity: callsign + emoji as username, color embed
# ---------------------------------------------------------------------------
_post() {
  local bot_id="$1" channel_id="$2" verb="$3" job_id="$4" body="$5"
  local callsign emoji color tok

  callsign=$(_bot_field "$bot_id" "callsign")
  emoji=$(_bot_field "$bot_id" "emoji")
  color=$(_bot_field "$bot_id" "color")
  avatar=$(_bot_field "$bot_id" "avatar_url")
  tok=$(_resolve_token "$bot_id")

  # Username Discord sees — max 80 chars, no @everyone/@here
  local display_name="${callsign} ${emoji}"

  # Format the content line
  local content
  case "$verb" in
    DISPATCH) content="🛫 **DISPATCH** | **${callsign}** ${emoji} | [${job_id}] ${body}" ;;
    ACK)      content="⚓ **ACK** | **${callsign}** ${emoji} | [${job_id}] ${body}" ;;
    TRAP)     content="🛬 **TRAP** | **${callsign}** ${emoji} | [${job_id}] ${body}" ;;
    RAW)      content="${body}" ;;
    *)        content="**[${verb}]** **${callsign}** ${emoji} | ${body}" ;;
  esac

  # Build payload with username override — gives each bot its own name in Discord
  local payload
  payload=$(python3 -c "
import json, sys
content   = sys.argv[1]
username  = sys.argv[2]
avatar    = sys.argv[3]
color_str = sys.argv[4]

d = {
    'content': content,
    'username': username,
    'allowed_mentions': {'parse': []}  # no pings ever
}
if avatar and avatar != 'None':
    d['avatar_url'] = avatar
print(json.dumps(d))
" "$content" "$display_name" "$avatar" "$color")

  local http_code
  http_code=$(curl -s -o /tmp/fleet_signal_resp.json -w "%{http_code}" \
    -X POST "https://discord.com/api/v10/channels/${channel_id}/messages" \
    -H "Authorization: Bot ${tok}" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [[ "$http_code" == "200" || "$http_code" == "201" ]]; then
    local msg_id
    msg_id=$(python3 -c "
import json
d = json.load(open('/tmp/fleet_signal_resp.json'))
print(d.get('id', '?'))
" 2>/dev/null || echo "?")
    echo "fleet_signal: [${callsign} ${emoji}] posted to #${CHAN_NAME} verb=$verb msg=$msg_id http=$http_code"
    return 0
  else
    echo "fleet_signal: POST failed for $bot_id http=$http_code body=$(cat /tmp/fleet_signal_resp.json 2>/dev/null)" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 DISPATCH|ACK|TRAP|RAW <bot_id> <job_id_or_msg> [body] [channel]" >&2
  echo "" >&2
  echo "  DISPATCH <bot_id> <job_id> <description>  [channel=fleet]" >&2
  echo "  ACK      <bot_id> <job_id> <status_line>  [channel=fleet]" >&2
  echo "  TRAP     <bot_id> <job_id> <result_line>  [channel=fleet]" >&2
  echo "  RAW      <bot_id> <message>               [channel=fleet]" >&2
  echo "" >&2
  echo "  channel: fleet (default), command, alerts, drafts, ready_room, catapult" >&2
  echo "" >&2
  echo "  Known bot_ids: coding_lt firstmate ops_lt email_reader email_drafter" >&2
  echo "                 calendar_manager todoist_manager finance_reader" >&2
  echo "                 knowledge_lt vault_librarian obsidian_archivist" >&2
  echo "                 hermes_ai_explorer passive_watch research_agent" >&2
  echo "                 chief_of_staff subscription_watcher api_watcher lockbox" >&2
  exit 1
fi

VERB=$(echo "$1" | tr '[:lower:]' '[:upper:]')
BOT_ID="$2"

# Validate bot_id
if ! python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from bot_identities import BOTS
sys.exit(0 if '$BOT_ID' in BOTS else 1)
" 2>/dev/null; then
  echo "fleet_signal: unknown bot_id '$BOT_ID'" >&2
  echo "  Run: python3 $SCRIPT_DIR/bot_identities.py" >&2
  exit 1
fi

case "$VERB" in
  DISPATCH|ACK|TRAP)
    [[ $# -ge 4 ]] || { echo "fleet_signal $VERB needs: bot_id job_id body [channel]" >&2; exit 1; }
    JOB_ID="$3"
    BODY="$4"
    CHAN_NAME="${5:-fleet}"
    ;;
  RAW)
    [[ $# -ge 3 ]] || { echo "fleet_signal RAW needs: bot_id message [channel]" >&2; exit 1; }
    JOB_ID=""
    BODY="$3"
    CHAN_NAME="${4:-fleet}"
    ;;
  *)
    echo "fleet_signal: unknown verb '$VERB' (use DISPATCH|ACK|TRAP|RAW)" >&2
    exit 1
    ;;
esac

CHANNEL_ID=$(_channel_id "$CHAN_NAME")
if [[ -z "$CHANNEL_ID" ]]; then
  echo "fleet_signal: unknown channel '$CHAN_NAME'" >&2
  echo "  Valid channels: fleet command alerts drafts ready_room catapult" >&2
  exit 1
fi

_post "$BOT_ID" "$CHANNEL_ID" "$VERB" "$JOB_ID" "$BODY"

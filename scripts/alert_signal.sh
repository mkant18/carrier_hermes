#!/usr/bin/env bash
# alert_signal.sh — post a structured alert to #alerts via webhook or First Watch REST.
#
# Usage:
#   alert_signal.sh <callsign> <level> <message> [color_hex]
#   alert_signal.sh Vigil WARN "Subscription quota at 90%"
#   alert_signal.sh Ledger HARD "OpenRouter spend exceeded $10 threshold" ff0000
#
# Level conventions:
#   SOFT   — informational (yellow 0xffcc00)
#   WARN   — attention needed (orange 0xff8800)
#   HARD   — immediate action required (red 0xff0000)
#   INFO   — status update (blue 0x0088ff)
#   OK     — cleared / resolved (green 0x00cc44)
#
# Token / webhook priority:
#   1. CARRIER_ALERTS_WEBHOOK in ~/.hermes/.env (webhook, zero token exposure)
#   2. DISCORD_FLEET_BOT_TOKEN in ~/.hermes/.env (First Watch REST fallback)
#
# Never prints token values. Exits 0 on success, non-zero on failure.

set -euo pipefail

ALERTS_CHANNEL_ID="1541866423427801148"  # #alerts
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"

_load_env_var() {
  local key="$1"
  grep -E "^${key}=" "$HERMES_ENV_FILE" 2>/dev/null \
    | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Level → color
# ---------------------------------------------------------------------------
_color_for_level() {
  case "$(echo "$1" | tr '[:lower:]' '[:upper:]')" in
    HARD)  echo "16711680"  ;; # red
    WARN)  echo "16744448"  ;; # orange
    SOFT)  echo "16763904"  ;; # yellow
    OK)    echo "52292"     ;; # green
    INFO)  echo "34943"     ;; # blue
    *)     echo "8421504"   ;; # grey
  esac
}

# ---------------------------------------------------------------------------
# Post via webhook (preferred — no token in environment)
# ---------------------------------------------------------------------------
_post_webhook() {
  local webhook="$1" callsign="$2" level="$3" msg="$4" color="$5"
  local payload
  payload=$(python3 -c "
import json, sys
callsign, level, msg, color = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
print(json.dumps({
    'embeds': [{
        'title': f'[{level}] {callsign}',
        'description': msg,
        'color': color,
        'footer': {'text': 'Carrier Fleet Alert'}
    }]
}))
" "$callsign" "$level" "$msg" "$color")

  local http_code
  http_code=$(curl -s -o /tmp/alert_resp.json -w "%{http_code}" \
    -X POST "$webhook" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [[ "$http_code" == "204" || "$http_code" == "200" ]]; then
    echo "alert_signal: posted via webhook (http=$http_code)"
    return 0
  else
    echo "alert_signal: webhook failed http=$http_code body=$(cat /tmp/alert_resp.json 2>/dev/null)" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Post via First Watch REST (fallback)
# ---------------------------------------------------------------------------
_post_rest() {
  local tok="$1" callsign="$2" level="$3" msg="$4" color="$5"
  local content="**[${level}] ${callsign}:** ${msg}"
  local payload
  payload=$(python3 -c "
import json, sys
callsign, level, msg, color = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
print(json.dumps({
    'embeds': [{
        'title': f'[{level}] {callsign}',
        'description': msg,
        'color': color,
        'footer': {'text': 'Carrier Fleet Alert'}
    }]
}))
" "$callsign" "$level" "$msg" "$color")

  local http_code
  http_code=$(curl -s -o /tmp/alert_resp.json -w "%{http_code}" \
    -X POST "https://discord.com/api/v10/channels/${ALERTS_CHANNEL_ID}/messages" \
    -H "Authorization: Bot ${tok}" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [[ "$http_code" == "200" || "$http_code" == "201" ]]; then
    local msg_id
    msg_id=$(python3 -c "import json; d=json.load(open('/tmp/alert_resp.json')); print(d.get('id','?'))" 2>/dev/null || echo "?")
    echo "alert_signal: posted via REST (msg_id=$msg_id, http=$http_code)"
    return 0
  else
    echo "alert_signal: REST failed http=$http_code body=$(cat /tmp/alert_resp.json 2>/dev/null)" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <callsign> <level> <message> [color_decimal]" >&2
  echo "  Levels: SOFT WARN HARD INFO OK" >&2
  exit 1
fi

CALLSIGN="$1"
LEVEL="$2"
MESSAGE="$3"
COLOR="${4:-$(_color_for_level "$LEVEL")}"

# Model footprint footer (§15.2) — appended when caller sets FLEET_MODEL_FOOTPRINT
# Format:  FLEET_MODEL_FOOTPRINT="google/gemini-2.5-flash · OpenRouter · ~$0.0004"
if [[ -n "${FLEET_MODEL_FOOTPRINT:-}" ]]; then
  FOOTPRINT_BLOCK=""
  while IFS= read -r line; do
    FOOTPRINT_BLOCK="${FOOTPRINT_BLOCK}
> 🤖 \`${line}\`"
  done <<< "${FLEET_MODEL_FOOTPRINT}"
  MESSAGE="${MESSAGE}${FOOTPRINT_BLOCK}"
fi

if [[ ! -f "$HERMES_ENV_FILE" ]]; then
  echo "alert_signal: env file not found: $HERMES_ENV_FILE" >&2
  exit 1
fi

WEBHOOK=$(_load_env_var "CARRIER_ALERTS_WEBHOOK")
if [[ -n "$WEBHOOK" ]]; then
  _post_webhook "$WEBHOOK" "$CALLSIGN" "$LEVEL" "$MESSAGE" "$COLOR"
  exit $?
fi

# Webhook not set — fall back to First Watch REST
TOKEN=$(_load_env_var "DISCORD_FLEET_BOT_TOKEN")
if [[ -n "$TOKEN" ]]; then
  echo "alert_signal: CARRIER_ALERTS_WEBHOOK not set — using First Watch REST fallback"
  _post_rest "$TOKEN" "$CALLSIGN" "$LEVEL" "$MESSAGE" "$COLOR"
  exit $?
fi

echo "alert_signal: neither CARRIER_ALERTS_WEBHOOK nor DISCORD_FLEET_BOT_TOKEN found in $HERMES_ENV_FILE" >&2
exit 1

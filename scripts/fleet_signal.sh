#!/usr/bin/env bash
# fleet_signal.sh — post DISPATCH / ACK / TRAP lines to #fleet via First Watch REST.
#
# Usage:
#   fleet_signal.sh DISPATCH <callsign> <emoji> <job_id> <description>
#   fleet_signal.sh ACK      <callsign> <emoji> <job_id> <status_line>
#   fleet_signal.sh TRAP     <callsign> <emoji> <job_id> <result_line>
#   fleet_signal.sh RAW      <message>           (post freeform line)
#
# The script reads DISCORD_FLEET_BOT_TOKEN from ~/.hermes/.env at runtime.
# It never prints the token. It exits 0 on success, non-zero on failure.
#
# Channel: #fleet (1541866443765977138) — fleet-wide dispatch & receipt board.
# Token:   First Watch (DISCORD_FLEET_BOT_TOKEN) — outbound REST only, no gateway.
#
# Environment (override if needed):
#   FLEET_CHANNEL_ID   default: 1541866443765977138 (#fleet)
#   HERMES_ENV_FILE    default: ~/.hermes/.env

set -euo pipefail

FLEET_CHANNEL_ID="${FLEET_CHANNEL_ID:-1541866443765977138}"
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"

# ---------------------------------------------------------------------------
# Load First Watch token from ~/.hermes/.env without echoing it
# ---------------------------------------------------------------------------
_load_token() {
  if [[ ! -f "$HERMES_ENV_FILE" ]]; then
    echo "fleet_signal: env file not found: $HERMES_ENV_FILE" >&2
    exit 1
  fi
  # Read only the DISCORD_FLEET_BOT_TOKEN line; strip comments and whitespace
  local tok
  tok=$(grep -E '^DISCORD_FLEET_BOT_TOKEN=' "$HERMES_ENV_FILE" \
        | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true)
  if [[ -z "$tok" ]]; then
    echo "fleet_signal: DISCORD_FLEET_BOT_TOKEN not found in $HERMES_ENV_FILE" >&2
    exit 1
  fi
  printf '%s' "$tok"
}

# ---------------------------------------------------------------------------
# Post a message to #fleet; mask the token in any output/logs
# ---------------------------------------------------------------------------
_post() {
  local content="$1"
  local tok
  tok=$(_load_token)

  local http_code
  http_code=$(curl -s -o /tmp/fleet_signal_resp.json -w "%{http_code}" \
    -X POST "https://discord.com/api/v10/channels/${FLEET_CHANNEL_ID}/messages" \
    -H "Authorization: Bot ${tok}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys; print(json.dumps({'content': sys.argv[1]}))" "$content")")

  if [[ "$http_code" == "200" || "$http_code" == "201" ]]; then
    local msg_id
    msg_id=$(python3 -c "import json,sys; d=json.load(open('/tmp/fleet_signal_resp.json')); print(d.get('id','?'))" 2>/dev/null || echo "?")
    echo "fleet_signal: posted to #fleet (msg_id=$msg_id, http=$http_code)"
    return 0
  else
    echo "fleet_signal: POST failed http=$http_code body=$(cat /tmp/fleet_signal_resp.json 2>/dev/null)" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------
_dispatch_msg() {
  # 🛫 DISPATCH | <Callsign> <emoji> | [JOB-ID] <description>
  local callsign="$1" emoji="$2" job_id="$3" desc="$4"
  printf '🛫 **DISPATCH** | %s %s | [%s] %s' "$callsign" "$emoji" "$job_id" "$desc"
}

_ack_msg() {
  # ⚓ ACK | <Callsign> <emoji> | [JOB-ID] <status>
  local callsign="$1" emoji="$2" job_id="$3" status="$4"
  printf '⚓ **ACK** | %s %s | [%s] %s' "$callsign" "$emoji" "$job_id" "$status"
}

_trap_msg() {
  # 🛬 TRAP | <Callsign> <emoji> | [JOB-ID] <result>
  local callsign="$1" emoji="$2" job_id="$3" result="$4"
  printf '🛬 **TRAP** | %s %s | [%s] %s' "$callsign" "$emoji" "$job_id" "$result"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 DISPATCH|ACK|TRAP|RAW <args...>" >&2
  echo "  DISPATCH <callsign> <emoji> <job_id> <description>" >&2
  echo "  ACK      <callsign> <emoji> <job_id> <status_line>" >&2
  echo "  TRAP     <callsign> <emoji> <job_id> <result_line>" >&2
  echo "  RAW      <message>" >&2
  exit 1
fi

verb=$(echo "$1" | tr '[:lower:]' '[:upper:]')
shift

case "$verb" in
  DISPATCH)
    [[ $# -ge 4 ]] || { echo "fleet_signal DISPATCH needs: callsign emoji job_id description" >&2; exit 1; }
    _post "$(_dispatch_msg "$1" "$2" "$3" "$4")"
    ;;
  ACK)
    [[ $# -ge 4 ]] || { echo "fleet_signal ACK needs: callsign emoji job_id status" >&2; exit 1; }
    _post "$(_ack_msg "$1" "$2" "$3" "$4")"
    ;;
  TRAP)
    [[ $# -ge 4 ]] || { echo "fleet_signal TRAP needs: callsign emoji job_id result" >&2; exit 1; }
    _post "$(_trap_msg "$1" "$2" "$3" "$4")"
    ;;
  RAW)
    [[ $# -ge 1 ]] || { echo "fleet_signal RAW needs a message" >&2; exit 1; }
    _post "$1"
    ;;
  *)
    echo "fleet_signal: unknown verb '$verb' (use DISPATCH|ACK|TRAP|RAW)" >&2
    exit 1
    ;;
esac

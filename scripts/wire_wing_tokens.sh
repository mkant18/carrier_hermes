#!/usr/bin/env bash
# wire_wing_tokens.sh — pull wing Discord tokens from Doppler and write them
# to each wing member's bot home .env file. Run after creating the 4 Discord Apps.
#
# Requires: doppler CLI authenticated with carrier-ops/prd
# Never prints token values. Writes with chmod 600.
#
# Also writes gateway guardrails to every non-gateway bot .env:
#   DISCORD_REQUIRE_MENTION=true
#   DISCORD_ALLOWED_USERS=<michael_id>
#   DISCORD_GATEWAY_ENABLED=false  (belt-and-suspenders guard)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MICHAEL_DISCORD_ID="174349224870150144"

# ---------------------------------------------------------------------------
# Pull a secret from Doppler (carrier-ops/prd), return just the value
# ---------------------------------------------------------------------------
_doppler_get() {
  local key="$1"
  local val
  val=$(doppler secrets get "$key" --project carrier-ops --config prd --plain 2>/dev/null || true)
  if [[ -z "$val" ]]; then
    echo "wire_wing_tokens: '$key' not found in Doppler carrier-ops/prd — skipping" >&2
    echo ""
    return
  fi
  printf '%s' "$val"
}

# ---------------------------------------------------------------------------
# Write a token to a bot profile .env (without printing the value)
# ---------------------------------------------------------------------------
_write_token_env() {
  local bot_id="$1" token_env_key="$2" token_val="$3"
  local env_file="$HOME/.hermes/profiles/$bot_id/.env"

  if [[ -z "$token_val" ]]; then
    echo "  SKIP $bot_id — token not available"
    return
  fi

  touch "$env_file"
  chmod 600 "$env_file"

  # Remove any existing line for this key
  grep -v "^${token_env_key}=" "$env_file" > /tmp/_env_wing_tmp 2>/dev/null || true
  mv /tmp/_env_wing_tmp "$env_file"

  # Append
  echo "${token_env_key}=${token_val}" >> "$env_file"
  echo "  wired $bot_id <- ${token_env_key} (${#token_val} chars)"
}

# ---------------------------------------------------------------------------
# Write gateway guardrails to a bot .env (no-gateway bots only)
# ---------------------------------------------------------------------------
_write_guardrails() {
  local bot_id="$1"
  local env_file="$HOME/.hermes/profiles/$bot_id/.env"

  touch "$env_file"
  chmod 600 "$env_file"

  # Remove any existing guardrail lines we manage
  grep -v -E '^(DISCORD_REQUIRE_MENTION|DISCORD_ALLOWED_USERS|DISCORD_GATEWAY_ENABLED|DISCORD_FREE_RESPONSE_CHANNELS)=' \
    "$env_file" > /tmp/_env_guard_tmp 2>/dev/null || true
  mv /tmp/_env_guard_tmp "$env_file"

  {
    echo "# Gateway guardrails — written by wire_wing_tokens.sh"
    echo "DISCORD_REQUIRE_MENTION=true"
    echo "DISCORD_ALLOWED_USERS=$MICHAEL_DISCORD_ID"
    echo "DISCORD_FREE_RESPONSE_CHANNELS="    # empty = no free-response anywhere
    echo "DISCORD_GATEWAY_ENABLED=false"      # belt-and-suspenders
  } >> "$env_file"
}

# ---------------------------------------------------------------------------
# Load wing membership from bot_identities.py
# ---------------------------------------------------------------------------
_wing_members() {
  local token_env_key="$1"
  python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from bot_identities import WINGS
members = WINGS.get('$token_env_key', [])
print(' '.join(members))
" 2>/dev/null || echo ""
}

# ---------------------------------------------------------------------------
# Main — iterate over 4 wing tokens + command-tier
# ---------------------------------------------------------------------------
WING_KEYS=(
  "CODING_WING_DISCORD_TOKEN"
  "OPS_WING_DISCORD_TOKEN"
  "KNOWLEDGE_WING_DISCORD_TOKEN"
  "RECON_WING_DISCORD_TOKEN"
)

echo "=== wire_wing_tokens ==="
echo "Pulling wing tokens from Doppler (carrier-ops/prd)..."
echo ""

for token_key in "${WING_KEYS[@]}"; do
  echo "── $token_key ──"
  tok=$(_doppler_get "$token_key")
  if [[ -z "$tok" ]]; then
    echo "  Not in Doppler yet — skip (create the Discord App first per docs/DISCORD_WING_APPS.md)"
    echo ""
    continue
  fi
  members=$(_wing_members "$token_key")
  if [[ -z "$members" ]]; then
    echo "  No members registered in bot_identities.py"
    echo ""
    continue
  fi
  for bot_id in $members; do
    _write_token_env "$bot_id" "$token_key" "$tok"
    _write_guardrails "$bot_id"
  done
  echo ""
done

# Command tier — subscription_watcher, api_watcher, lockbox use First Watch
echo "── DISCORD_FLEET_BOT_TOKEN (command tier: Vigil, Ledger, LockBox) ──"
ft_tok=$(_doppler_get "DISCORD_FLEET_BOT_TOKEN" 2>/dev/null || true)
if [[ -z "$ft_tok" ]]; then
  # Try loading from default .env (may already be there)
  ft_tok=$(grep -E '^DISCORD_FLEET_BOT_TOKEN=' "$HOME/.hermes/.env" 2>/dev/null \
    | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || true)
fi
for bot_id in subscription_watcher api_watcher lockbox; do
  _write_token_env "$bot_id" "DISCORD_FLEET_BOT_TOKEN" "$ft_tok"
  _write_guardrails "$bot_id"
done
echo ""

# All specialist bots (not chief_of_staff) get guardrails regardless
echo "── Gateway guardrails (all non-gateway bots) ──"
NON_GW_BOTS=(
  coding_lt firstmate ops_lt email_reader email_drafter
  calendar_manager todoist_manager knowledge_lt vault_librarian
  obsidian_archivist research_agent finance_reader
  hermes_ai_explorer passive_watch
  subscription_watcher api_watcher lockbox
)
for bot_id in "${NON_GW_BOTS[@]}"; do
  _write_guardrails "$bot_id"
  echo "  guardrails: $bot_id"
done

echo ""
echo "=== done ==="
echo ""
echo "Next steps:"
echo "  1. bash ~/carrier_hermes/scripts/apply_bot_matrix.sh"
echo "  2. bash ~/carrier_hermes/scripts/smoke_fleet.sh"
echo ""
echo "To verify identity resolution:"
echo "  python3 ~/carrier_hermes/scripts/bot_identities.py coding_lt"

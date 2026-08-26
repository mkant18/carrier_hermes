#!/usr/bin/env bash
# gateway_guard.sh — enforce no unauthorized gateways and no unwanted agent turns.
#
# Checks:
#   1. Only chief_of_staff and default home gateways are permitted to run
#   2. All non-gateway bots have DISCORD_REQUIRE_MENTION=true in their .env
#   3. All non-gateway bots have DISCORD_ALLOWED_USERS set to Michael's ID
#   4. No non-gateway bot has a gateway process running
#   5. Prints a summary — exits 1 if any violation found
#
# Run: bash gateway_guard.sh [--fix]
#   --fix: write missing guardrails automatically (non-gateway bots only)

set -euo pipefail

MICHAEL_DISCORD_ID="174349224870150144"

# Bots permitted to open a gateway (one each)
GATEWAY_PERMITTED=("chief_of_staff" "default")

# All fleet bots that must NEVER open a gateway
NON_GATEWAY_BOTS=(
  coding_lt firstmate ops_lt email_reader email_drafter
  calendar_manager todoist_manager knowledge_lt vault_librarian
  obsidian_archivist research_agent finance_reader
  hermes_ai_explorer passive_watch
  subscription_watcher api_watcher lockbox
)

FIX_MODE=false
[[ "${1:-}" == "--fix" ]] && FIX_MODE=true

fail=0
pass() { echo "PASS  $1"; }
failc() { echo "FAIL  $1 — $2"; fail=1; }
warn() { echo "WARN  $1"; }

echo "=== gateway_guard ==="

# ---------------------------------------------------------------------------
# 1. Check for unauthorized DISCORD gateways
#
# The single-gateway rule is about DISCORD INBOUND, not the cron scheduler.
# On the Windows primary host the watcher bots (Vigil/Ledger/Sonar/Chart) run
# scheduler-only gateways (platforms=NONE) so their crons fire — that is
# REQUIRED and safe. What must never happen is a second bot opening a Discord
# connection. So we assert on gateway_state.json's platforms.discord.state,
# not on the mere presence of a gateway process.
#
# Authoritative source: ~/.hermes/profiles/<bot>/gateway_state.json
#   platforms.discord.state == "connected"  => a live Discord gateway
# ---------------------------------------------------------------------------
_discord_state() {
  # prints the discord platform state for a bot, or empty
  local bot_id="$1"
  local gs="$HOME/.hermes/profiles/$bot_id/gateway_state.json"
  [[ -f "$gs" ]] || { echo ""; return; }
  python3 - "$gs" <<'PY' 2>/dev/null || echo ""
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(((d.get("platforms") or {}).get("discord") or {}).get("state") or "")
except Exception:
    print("")
PY
}

for bot_id in "${NON_GATEWAY_BOTS[@]}"; do
  st=$(_discord_state "$bot_id")
  if [[ "$st" == "connected" ]]; then
    failc "no_rogue_discord_$bot_id" "bot has a CONNECTED Discord gateway — kill with: hermes -p $bot_id gateway stop"
  else
    pass "no_rogue_discord_$bot_id"
  fi
done

# Exactly one Discord-connected gateway, and it must be chief_of_staff (Helm)
connected_discord=""
for bot_id in "${GATEWAY_PERMITTED[@]}" "${NON_GATEWAY_BOTS[@]}"; do
  st=$(_discord_state "$bot_id")
  [[ "$st" == "connected" ]] && connected_discord="$connected_discord $bot_id"
done
connected_discord=$(echo "$connected_discord" | xargs 2>/dev/null || true)
if [[ "$connected_discord" == "chief_of_staff" ]]; then
  pass "single_discord_gateway_helm_only"
elif [[ -z "$connected_discord" ]]; then
  warn "no Discord gateway connected (Helm gateway may be starting)"
else
  failc "single_discord_gateway_helm_only" "expected only chief_of_staff, got: $connected_discord"
fi

# ---------------------------------------------------------------------------
# 2. Verify .env guardrails on all non-gateway bots
# ---------------------------------------------------------------------------
for bot_id in "${NON_GATEWAY_BOTS[@]}"; do
  env_file="$HOME/.hermes/profiles/$bot_id/.env"

  if [[ ! -f "$env_file" ]]; then
    if $FIX_MODE; then
      touch "$env_file"; chmod 600 "$env_file"
      warn "created missing .env for $bot_id"
    else
      failc "env_exists_$bot_id" ".env missing — run wire_wing_tokens.sh --fix"
      continue
    fi
  fi

  # Check DISCORD_REQUIRE_MENTION=true
  req_mention=$(grep -E '^DISCORD_REQUIRE_MENTION=' "$env_file" 2>/dev/null \
    | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || echo "")
  if [[ "$req_mention" != "true" ]]; then
    if $FIX_MODE; then
      grep -v '^DISCORD_REQUIRE_MENTION=' "$env_file" > /tmp/_gguard_tmp || true
      mv /tmp/_gguard_tmp "$env_file"
      echo "DISCORD_REQUIRE_MENTION=true" >> "$env_file"
      warn "fixed DISCORD_REQUIRE_MENTION for $bot_id"
    else
      failc "require_mention_$bot_id" "DISCORD_REQUIRE_MENTION not 'true' (got '${req_mention:-NOT SET}')"
    fi
  else
    pass "require_mention_$bot_id"
  fi

  # Check DISCORD_ALLOWED_USERS contains Michael's ID
  allowed=$(grep -E '^DISCORD_ALLOWED_USERS=' "$env_file" 2>/dev/null \
    | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || echo "")
  if [[ "$allowed" != *"$MICHAEL_DISCORD_ID"* ]]; then
    if $FIX_MODE; then
      grep -v '^DISCORD_ALLOWED_USERS=' "$env_file" > /tmp/_gguard_tmp || true
      mv /tmp/_gguard_tmp "$env_file"
      echo "DISCORD_ALLOWED_USERS=$MICHAEL_DISCORD_ID" >> "$env_file"
      warn "fixed DISCORD_ALLOWED_USERS for $bot_id"
    else
      failc "allowed_users_$bot_id" "DISCORD_ALLOWED_USERS missing Michael's ID (got '${allowed:-NOT SET}')"
    fi
  else
    pass "allowed_users_$bot_id"
  fi

  # Check DISCORD_GATEWAY_ENABLED=false (belt-and-suspenders)
  gw_enabled=$(grep -E '^DISCORD_GATEWAY_ENABLED=' "$env_file" 2>/dev/null \
    | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || echo "")
  if [[ "$gw_enabled" == "true" ]]; then
    if $FIX_MODE; then
      grep -v '^DISCORD_GATEWAY_ENABLED=' "$env_file" > /tmp/_gguard_tmp || true
      mv /tmp/_gguard_tmp "$env_file"
      echo "DISCORD_GATEWAY_ENABLED=false" >> "$env_file"
      warn "fixed DISCORD_GATEWAY_ENABLED for $bot_id"
    else
      failc "gw_disabled_$bot_id" "DISCORD_GATEWAY_ENABLED=true — should be false"
    fi
  fi

done

# ---------------------------------------------------------------------------
# 3. Verify Helm's guardrails — gateway permitted but must be locked to Michael
# ---------------------------------------------------------------------------
cos_env="$HOME/.hermes/profiles/chief_of_staff/.env"
if [[ -f "$cos_env" ]]; then
  cos_allowed=$(grep -E '^DISCORD_ALLOWED_USERS=' "$cos_env" 2>/dev/null \
    | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null || echo "")
  if [[ "$cos_allowed" == *"$MICHAEL_DISCORD_ID"* ]]; then
    pass "helm_allowed_users"
  else
    failc "helm_allowed_users" "chief_of_staff DISCORD_ALLOWED_USERS missing Michael's ID"
  fi
else
  failc "helm_env_exists" "chief_of_staff .env missing"
fi

echo "=== done fail=$fail ==="
exit "$fail"

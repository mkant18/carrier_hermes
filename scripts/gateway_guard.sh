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
# 1. Check for unauthorized gateway processes
# ---------------------------------------------------------------------------
for bot_id in "${NON_GATEWAY_BOTS[@]}"; do
  pids=$(pgrep -f "profile ${bot_id} gateway" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    failc "no_rogue_gateway_$bot_id" "gateway process running (pids: $pids) — kill with: hermes -p $bot_id gateway stop"
  fi
done

# Check permitted gateways are actually running (warn only, not a fail)
for bot_id in "${GATEWAY_PERMITTED[@]}"; do
  pids=$(pgrep -f "profile ${bot_id} gateway" 2>/dev/null || \
         (pgrep -f "hermes.*gateway" 2>/dev/null | head -1) || true)
  if [[ -z "$pids" ]]; then
    warn "permitted_gateway_$bot_id not running (expected)"
  fi
done

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

#!/usr/bin/env bash
# Create / refresh the 18-bot roster homes. Product = bot; CLI = profile create.
# Command tier (4) + Recon Wing (3) + Ops Wing (6) + Coding Wing (2) + Knowledge Wing (3).
# Phase A freeze documents LockBox; do not run this until Michael approves Phase B
# if Doppler/HMAC keys are not ready — script itself is safe (copies SOULs only).
set -euo pipefail
ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"

bots=(
  "chief_of_staff|Helm — front door; classify and dispatch job packets"
  "subscription_watcher|Vigil — fleet-wide stalls and subscription quota; DISPATCH_LOCK"
  "api_watcher|Ledger — fleet-wide OpenRouter spend; SPEND_HALT"
  "lockbox|LockBox — Doppler secrets + CoS handshake redeem; no peer sidechannel"
  "coding_lt|Wrench — Coding Wing lead; routes coding jobs to Mate, reviews results"
  "firstmate|Mate — default coding crew (claude-code → codex → opencode)"
  "hermes_ai_explorer|Chart — Recon Wing lead; fleet intelligence synthesis + proposals"
  "passive_watch|Sonar — Recon Wing passive watcher; daily ecosystem signals for Chart"
  "ops_lt|Deck — Ops Wing lead; routes email, calendar, task and finance traffic"
  "email_reader|Inbox — email triage; no send; paid DeepSeek"
  "email_drafter|Quill — drafts only to #drafts; never sends"
  "calendar_manager|Chronos — calendar only; hands tasks to Tasker"
  "todoist_manager|Tasker — all Todoist mutations"
  "knowledge_lt|Stacks — Knowledge Wing lead; intake gate and vault routing"
  "vault_librarian|Librarian — vault query/health out; not intake"
  "obsidian_archivist|Clerk — vault intake in; Helm keep/discard"
  "research_agent|Probe — Recon Wing on-demand web research"
  "finance_reader|Purse — personal finance read-only Monarch queries"
)

for spec in "${bots[@]}"; do
  id="${spec%%|*}"
  desc="${spec#*|}"
  if [[ ! -d "$HOME/.hermes/profiles/$id" ]]; then
    hermes profile create "$id" --no-skills --no-alias --description "$desc" || true
  fi
  mkdir -p "$HOME/.hermes/profiles/$id"
  cp -f "$ROOT/bots/$id/SOUL.md" "$HOME/.hermes/profiles/$id/SOUL.md"
  # Correct form is `hermes profile describe <bot_id> --text` — the `-p <id> ...
  # profile describe --text` form fails with "profile name is required".
  hermes profile describe "$id" --text "$desc" >/dev/null 2>&1 || true
  echo "bot home ready: $id"
done

# ---------------------------------------------------------------------------
# Discord channel posture — written to each bot's .env file so the Hermes
# gateway/REST layer picks up the correct home channel without a serve restart.
# Rule: no bot except Helm opens a gateway; all use First Watch (DISCORD_FLEET_BOT_TOKEN)
# for outbound only. Channel IDs are frozen per docs/DISCORD_CHANNELS.md.
# ---------------------------------------------------------------------------
FLEET_CH="1541866443765977138"    # #fleet
ALERTS_CH="1541866423427801148"   # #alerts
DRAFTS_CH="1541866401432871002"   # #drafts
COMMAND_CH="1541866378255011980"  # #command

wire_discord_env() {
  # wire_discord_env <bot_id> <home_channel_id> [allowed_channels_csv]
  local bot_id="$1" home_ch="$2" allowed="${3:-}"
  local env_file="$HOME/.hermes/profiles/$bot_id/.env"
  touch "$env_file"
  chmod 600 "$env_file"

  # Remove any pre-existing discord channel lines we manage
  grep -v -E '^(DISCORD_HOME_CHANNEL|DISCORD_HOME_CHANNEL_NAME|DISCORD_ALLOWED_CHANNELS)=' \
    "$env_file" > /tmp/_env_tmp 2>/dev/null || true
  mv /tmp/_env_tmp "$env_file"

  # Append the correct posture
  {
    echo "DISCORD_HOME_CHANNEL=$home_ch"
    [[ -n "$allowed" ]] && echo "DISCORD_ALLOWED_CHANNELS=$allowed"
  } >> "$env_file"
  echo "discord_env: $bot_id home=$home_ch${allowed:+ allowed=$allowed}"
}

# Command tier — Helm speaks in #command (gateway token already in CoS .env)
wire_discord_env chief_of_staff    "$COMMAND_CH" "$COMMAND_CH,$FLEET_CH,$ALERTS_CH,$DRAFTS_CH"

# Vigil / Ledger — post alerts to #command and #alerts
wire_discord_env subscription_watcher "$COMMAND_CH" "$COMMAND_CH,$ALERTS_CH"
wire_discord_env api_watcher          "$COMMAND_CH" "$COMMAND_CH,$ALERTS_CH"

# LockBox — #alerts only (redacted alerts; no other channel)
wire_discord_env lockbox "$ALERTS_CH" "$ALERTS_CH"

# Lts — post DISPATCH/ACK/TRAP to #fleet; Deck also reads #drafts
wire_discord_env coding_lt    "$FLEET_CH" "$FLEET_CH"
wire_discord_env ops_lt       "$FLEET_CH" "$FLEET_CH,$DRAFTS_CH"
wire_discord_env knowledge_lt "$FLEET_CH" "$FLEET_CH"

# Recon Wing
wire_discord_env hermes_ai_explorer "$FLEET_CH" "$FLEET_CH"
wire_discord_env passive_watch      "$FLEET_CH" "$FLEET_CH"

# Specialists — all use #fleet for TRAP confirmations via fleet_signal.sh
for bot_id in firstmate email_reader email_drafter calendar_manager \
              todoist_manager vault_librarian obsidian_archivist \
              research_agent finance_reader; do
  wire_discord_env "$bot_id" "$FLEET_CH" "$FLEET_CH"
done

# Quill also posts to #drafts
wire_discord_env email_drafter "$FLEET_CH" "$FLEET_CH,$DRAFTS_CH"

# Helm roster skill
mkdir -p "$HOME/.hermes/profiles/chief_of_staff/skills/carrier-roster"
cp -f "$ROOT/skills/carrier-roster/SKILL.md" \
  "$HOME/.hermes/profiles/chief_of_staff/skills/carrier-roster/SKILL.md"
# also user-global so Helm sessions can load it
mkdir -p "$HOME/.hermes/skills/carrier-roster"
cp -f "$ROOT/skills/carrier-roster/SKILL.md" "$HOME/.hermes/skills/carrier-roster/SKILL.md"

echo "roster install complete"
hermes profile list

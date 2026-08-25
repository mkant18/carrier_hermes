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

# Helm roster skill
mkdir -p "$HOME/.hermes/profiles/chief_of_staff/skills/carrier-roster"
cp -f "$ROOT/skills/carrier-roster/SKILL.md" \
  "$HOME/.hermes/profiles/chief_of_staff/skills/carrier-roster/SKILL.md"
# also user-global so Helm sessions can load it
mkdir -p "$HOME/.hermes/skills/carrier-roster"
cp -f "$ROOT/skills/carrier-roster/SKILL.md" "$HOME/.hermes/skills/carrier-roster/SKILL.md"

echo "roster install complete"
hermes profile list

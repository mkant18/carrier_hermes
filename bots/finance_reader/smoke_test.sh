#!/usr/bin/env bash
# Smoke test for finance_reader (Purse).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"

echo "=== finance_reader (Purse) smoke ==="

# 1. Check SOUL exists in repo and profile home
if [[ -f "$ROOT/bots/finance_reader/SOUL.md" ]] && [[ -f "$HOME/.hermes/profiles/finance_reader/SOUL.md" ]]; then
  echo "PASS soul_synced"
else
  echo "FAIL soul_synced"
  exit 1
fi

# 2. Check model pin is quality
model=$(hermes -p finance_reader config get model.default 2>/dev/null || hermes -p finance_reader config get model 2>/dev/null || true)
if [[ "$model" == *"claude-sonnet-4-6"* ]]; then
  echo "PASS model_pinned ($model)"
else
  echo "FAIL model_pinned ($model)"
  exit 1
fi

# 3. Check mailbox and finance state directories exist
if [[ -d "$VAULT/_agent/finance" ]] && [[ -d "$VAULT/_agent/mailbox/finance_reader/inbox" ]] && [[ -d "$VAULT/_agent/mailbox/finance_reader/outbox" ]]; then
  echo "PASS directories_exist"
else
  echo "FAIL directories_exist"
  exit 1
fi

echo "=== finance_reader smoke PASS ==="

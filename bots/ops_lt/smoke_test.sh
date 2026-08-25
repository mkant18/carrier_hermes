#!/usr/bin/env bash
# Smoke test for this bot. Run after hermes profile create.
# Fill in an actual test for the bot's primary capability.
set -euo pipefail
BOT_ID="$(basename "$(dirname "$0")")"
echo "[smoke] $BOT_ID — no smoke tests defined yet."
# Example:
# hermes -p "$BOT_ID" run --one-shot "Echo: smoke test" | grep -q "smoke test"
# echo "[smoke] $BOT_ID PASS"

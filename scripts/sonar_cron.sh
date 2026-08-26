#!/usr/bin/env bash
# sonar_cron.sh — no_agent wrapper for Sonar.
# Runs sonar_heartbeat.sh and adapts its exit convention to the no_agent
# contract: stdout IS the message; empty stdout = silent; exit 0 always
# (a genuine ecosystem-change signal is real content, not an error, so it must
# be delivered as a message rather than logged as a failed cron run).
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HB="$SCRIPTS_DIR/sonar_heartbeat.sh"
[[ -f "$HB" ]] || HB="$HOME/.hermes/scripts/sonar_heartbeat.sh"
[[ -f "$HB" ]] || HB="$HOME/carrier_hermes/scripts/sonar_heartbeat.sh"

out="$(bash "$HB" 2>/dev/null)"
rc=$?
# rc 0 = no change (silent). rc 1 = signal detected (out has the summary line +
# the full diff is written to the vault by sonar_heartbeat.sh). Any other rc is
# a real error worth surfacing.
if [[ "$rc" -eq 0 ]]; then
  exit 0                       # silent healthy day
elif [[ "$rc" -eq 1 ]]; then
  [[ -n "$out" ]] && printf '📡 Sonar signal: %s\n' "$out"
  exit 0                       # deliver signal as a message, not an error
else
  printf '⚠️ Sonar heartbeat error (rc=%s): %s\n' "$rc" "$out"
  exit 0                       # surface as message; do not mark cron failed
fi

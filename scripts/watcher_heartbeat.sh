#!/usr/bin/env bash
# Vigil heartbeat — no_agent. Empty stdout = healthy/silent.
# Non-empty stdout = alert text for Discord/cron delivery.
set -euo pipefail
ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
LOG="$VAULT/_agent/watcher/heartbeat.log"
LOCK_HELPER="$ROOT/scripts/dispatch_lock.sh"
HB="$HOME/.hermes/carrier/VIGIL_HEARTBEAT"
mkdir -p "$(dirname "$LOG")" "$(dirname "$HB")" "$VAULT/_agent/watcher"
date -u +%Y-%m-%dT%H:%M:%SZ >"$HB"

alerts=()

if ! pgrep -f 'hermes gateway' >/dev/null 2>&1; then
  if ! pgrep -f 'hermes-agent' >/dev/null 2>&1; then
    alerts+=("gateway_or_hermes_process_not_found")
  fi
fi

# disk free on $HOME (percent used)
used=$(df -P "$HOME" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
if [[ -n "${used:-}" && "$used" -ge 95 ]]; then
  alerts+=("disk_used_${used}pct")
fi

# error storm: recent 429s in hermes logs (best-effort)
if [[ -f "$HOME/.hermes/logs/errors.log" ]]; then
  hits=$(grep -c '429' "$HOME/.hermes/logs/errors.log" 2>/dev/null || true)
  if [[ "${hits:-0}" -ge 20 ]]; then
    alerts+=("error_log_429_count_${hits}")
  fi
fi

if [[ ${#alerts[@]} -gt 0 ]]; then
  reason=$(IFS=,; echo "${alerts[*]}")
  bash "$LOCK_HELPER" set "$reason" >/dev/null
  printf 'VIGIL ALERT: %s\nDISPATCH_LOCK set\n' "$reason"
  printf '%s ALERT %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >>"$LOG"
  bash "$ROOT/scripts/audit_append.sh" subscription_watcher lock "$reason" >/dev/null || true
  exit 0
fi

printf '%s ok\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"
exit 0

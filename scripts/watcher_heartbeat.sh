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

# Portable process-presence check. On macOS/Linux uses pgrep; on Windows
# (Git Bash, no pgrep in the cron runtime) falls back to PowerShell CIM.
# CRITICAL: only alert when a check DEFINITELY finds no process — never when
# the tooling to check is itself missing (that path caused a false
# "gateway_not_found" every run on Windows, which wrongly set DISPATCH_LOCK).
_proc_matches() {
  # _proc_matches <substring> -> prints count, exit 0 if check ran, 2 if no tool
  local pat="$1"
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f "$pat" >/dev/null 2>&1 && echo 1 || echo 0
    return 0
  fi
  if command -v powershell >/dev/null 2>&1; then
    local esc n
    esc=$(printf '%s' "$pat" | sed "s/'/''/g")
    n=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*${esc}*' }).Count" 2>/dev/null | tr -d '
')
    [[ -n "$n" && "$n" -gt 0 ]] && echo 1 || echo 0
    return 0
  fi
  return 2   # no tool to check — do NOT alarm
}

gw=$(_proc_matches 'gateway'); gw_rc=$?
if [[ "$gw_rc" -eq 0 && "$gw" == "0" ]]; then
  ha=$(_proc_matches 'hermes'); ha_rc=$?
  if [[ "$ha_rc" -eq 0 && "$ha" == "0" ]]; then
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

#!/usr/bin/env bash
# mac_to_secondary.sh — run ON THE MAC to (1) print a NON-SECRET migration
# inventory and (2) convert the Mac to SECONDARY: stop the production Discord
# gateway + fleet crons so it never competes with the Windows primary host.
#
# SAFE: prints no secret VALUES. Does not delete config, homes, SOULs, or the
# vault. Fully reversible (see the ROLLBACK section printed at the end).
#
# Usage on the Mac (Terminal):
#   cd ~/carrier_hermes && git pull --ff-only origin main
#   bash scripts/mac_to_secondary.sh            # audit only (dry run)
#   bash scripts/mac_to_secondary.sh --cutover  # actually stop prod + mark secondary
set -uo pipefail

CUTOVER=0
[[ "${1:-}" == "--cutover" ]] && CUTOVER=1
HH="${HERMES_HOME:-$HOME/.hermes}"

echo "================ CARRIER HERMES — MAC AUDIT ================"
echo "host: $(hostname)   user: $(whoami)   date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "HERMES_HOME: $HH"
echo

echo "---- 1. Running Hermes gateways (production Discord inbound) ----"
# List gateways + which are running
hermes gateway list 2>/dev/null || true
echo
echo "Processes that look like a gateway:"
pgrep -fl 'gateway' 2>/dev/null | grep -i hermes || echo "  (none)"
echo

echo "---- 2. Which bot holds a CONNECTED Discord gateway? ----"
for gs in "$HH"/profiles/*/gateway_state.json; do
  [[ -f "$gs" ]] || continue
  bot=$(basename "$(dirname "$gs")")
  st=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(((d.get('platforms') or {}).get('discord') or {}).get('state') or '')" "$gs" 2>/dev/null)
  [[ "$st" == "connected" ]] && echo "  CONNECTED: $bot"
done
echo

echo "---- 3. Fleet cron jobs on the Mac (would double-run vs Windows) ----"
for p in "$HH"/profiles/*/; do
  bot=$(basename "$p")
  n=$(hermes -p "$bot" cron list 2>/dev/null | grep -c 'Name:')
  [[ "${n:-0}" -gt 0 ]] && echo "  $bot: $n cron(s)"
done
echo

echo "---- 4. Gateway login items / launchd (auto-start on boot) ----"
ls "$HOME/Library/LaunchAgents/" 2>/dev/null | grep -i hermes || echo "  no LaunchAgents"
echo

echo "---- 5. Host role marker ----"
cat "$HH/carrier/HOST_ROLE.json" 2>/dev/null || echo "  (no HOST_ROLE.json)"
echo

echo "---- 6. Secret NAMES only (never values) present in default .env ----"
grep -oE '^[A-Z_]+=' "$HH/.env" 2>/dev/null | sed 's/=$//' | sort -u || echo "  (no .env)"
echo

if [[ "$CUTOVER" -eq 0 ]]; then
  echo "================ DRY RUN COMPLETE ================"
  echo "Re-run with --cutover to STOP production on this Mac and mark it SECONDARY."
  exit 0
fi

echo "================ CUTOVER: MAC -> SECONDARY ================"

# 6a. Stop every running gateway on the Mac (Discord inbound + schedulers)
echo "-- stopping all gateways --"
for p in "$HH"/profiles/*/; do
  bot=$(basename "$p")
  hermes -p "$bot" gateway stop 2>/dev/null && echo "  stopped gateway: $bot" || true
done
# default home gateway too
hermes gateway stop 2>/dev/null || true

# 6b. Uninstall gateway auto-start (launchd/login items) so it stays down after reboot
echo "-- uninstalling gateway auto-start --"
for p in "$HH"/profiles/*/; do
  bot=$(basename "$p")
  hermes -p "$bot" gateway uninstall 2>/dev/null && echo "  uninstalled service: $bot" || true
done
hermes gateway uninstall 2>/dev/null || true

# 6c. Pause every fleet cron (do NOT delete — reversible)
echo "-- pausing all fleet crons --"
for p in "$HH"/profiles/*/; do
  bot=$(basename "$p")
  ids=$(hermes -p "$bot" cron list 2>/dev/null | grep -oE '[0-9a-f]{12}')
  for id in $ids; do
    hermes -p "$bot" cron pause "$id" 2>/dev/null && echo "  paused $bot/$id" || true
  done
done

# 6d. Write the SECONDARY host marker
mkdir -p "$HH/carrier"
cat > "$HH/carrier/HOST_ROLE.json" <<'JSON'
{
  "role": "secondary",
  "platform": "macos",
  "fleet": "carrier_hermes",
  "notes": "Fallback/dev host. Production gateway and production crons disabled 2026-08-25 during Windows-primary cutover."
}
JSON
echo "  wrote secondary HOST_ROLE.json"

echo
echo "-- verification: no gateway should be connected now --"
hermes gateway list 2>/dev/null | grep -E '✓' || echo "  (no running gateways — good)"
echo
echo "================ MAC IS NOW SECONDARY ================"
echo "The Mac keeps all config, homes, SOULs, memory, and vault — it is a clean"
echo "fallback. To reactivate it as primary later (ROLLBACK), on the Mac run:"
echo "  hermes -p chief_of_staff gateway install --start-now --start-on-login"
echo "  hermes -p subscription_watcher cron resume <id>   # etc. per bot"
echo "  # and set HOST_ROLE.json role back to primary"
echo
echo "IMPORTANT: never run the Windows primary AND the Mac production gateway at"
echo "the same time — one Discord gateway only."

#!/usr/bin/env bash
# Ledger heartbeat v2 — no_agent. Empty stdout = under cap / silent.
# Sources: ledger_probe.py (Hermes DBs + OpenRouter /api/v1/key)
# Exit codes from probe: 0=ok 2=soft 3=hard
set -euo pipefail

ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
PROBE="$ROOT/scripts/ledger_probe.py"
HALT_HELPER="$ROOT/scripts/spend_halt.sh"
ALERT="$ROOT/scripts/alert_signal.sh"

# Load env
ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      OPENROUTER_API_KEY=*|OBSIDIAN_VAULT_PATH=*|CARRIER_OR_SOFT_DAILY=*|CARRIER_OR_HARD_DAILY=*)
        export "$line" ;;
    esac
  done < "$ENV_FILE"
fi

# Run probe (quiet — we handle output here)
set +e
probe_out=$(python3 "$PROBE" --quiet 2>&1)
probe_exit=$?
set -e

# Read snapshot
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
SNAP="$VAULT/_agent/api_watcher/ledger-snapshot.json"

if [[ ! -f "$SNAP" ]]; then
  echo "⚠️ Ledger: snapshot not written. Probe error: $probe_out"
  exit 0
fi

usage_daily=$(python3 -c "import json; d=json.load(open('$SNAP')); print(d.get('or_balance',{}).get('usage_daily','?'))" 2>/dev/null || echo "?")
limit=$(python3 -c "import json; d=json.load(open('$SNAP')); print(d.get('or_balance',{}).get('limit','?'))" 2>/dev/null || echo "?")
remaining=$(python3 -c "import json; d=json.load(open('$SNAP')); print(d.get('or_balance',{}).get('limit_remaining','?'))" 2>/dev/null || echo "?")
halt_reason=$(python3 -c "import json; d=json.load(open('$SNAP')); print(d.get('thresholds',{}).get('halt_reason','') or '')" 2>/dev/null || echo "")
top_profile=$(python3 -c "
import json
d=json.load(open('$SNAP'))
profiles = [(k,v) for k,v in d.get('by_profile',{}).items() if isinstance(v,dict) and 'error' not in v]
profiles.sort(key=lambda x: x[1].get('inp',0)+x[1].get('out',0), reverse=True)
if profiles: print(f'{profiles[0][0]} ({profiles[0][1].get(\"inp\",0)+profiles[0][1].get(\"out\",0):,} tok)')
else: print('none')
" 2>/dev/null || echo "?")

if [[ "$probe_exit" -eq 3 ]]; then
  # Hard cap — set SPEND_HALT and alert
  bash "$HALT_HELPER" set "openrouter_daily_hard_cap: $halt_reason" 2>/dev/null || true
  msg="⛔ Ledger HARD CAP: \$${usage_daily} / \$${limit} daily OpenRouter limit. SPEND_HALT set. Top bot: ${top_profile}. Remaining: \$${remaining}"
  bash "$ALERT" "#alerts" "$msg" 2>/dev/null || true
  echo "$msg"

elif [[ "$probe_exit" -eq 2 ]]; then
  # Soft cap — alert only (no halt)
  msg="⚠️ Ledger soft cap: \$${usage_daily} / \$${limit} daily OpenRouter (soft=\$${CARRIER_OR_SOFT_DAILY:-8}). Remaining: \$${remaining}. Top: ${top_profile}"
  bash "$ALERT" "#alerts" "$msg" 2>/dev/null || true
  echo "$msg"

else
  # Under cap — silent (no_agent: empty stdout = no delivery)
  exit 0
fi

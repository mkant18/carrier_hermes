#!/usr/bin/env bash
# Ledger heartbeat — no_agent. Empty stdout = under cap / silent.
# Uses GET https://openrouter.ai/api/v1/key (inference key).
set -euo pipefail
ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
STATE="$VAULT/_agent/api_watcher/spend-state.json"
HALT_HELPER="$ROOT/scripts/spend_halt.sh"
mkdir -p "$(dirname "$STATE")"

# Load .env without printing.
# Prefer a line-export loop over `source <(grep …)`: process substitution can be
# scrubbed by agent sandboxes and leave a truncated/empty key.
ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      OPENROUTER_API_KEY=*|OPENROUTER_MANAGEMENT_KEY=*)
        export "$line"
        ;;
    esac
  done < "$ENV_FILE"
fi

SOFT_DAILY="${CARRIER_OR_SOFT_DAILY:-8}"
HARD_DAILY="${CARRIER_OR_HARD_DAILY:-15}"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  python3 - <<PY
import json, datetime
from pathlib import Path
p = Path(r"$STATE")
p.write_text(json.dumps({
  "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "ok": False,
  "error": "OPENROUTER_API_KEY_missing",
  "halt": False,
}, indent=2) + "\n")
PY
  # Missing key is not a spend breach — do not halt the fleet.
  exit 0
fi

tmp="$(mktemp)"
code=$(curl -sS -o "$tmp" -w '%{http_code}' \
  -H "Authorization: Bearer ${OPENROUTER_API_KEY}" \
  https://openrouter.ai/api/v1/key || echo "000")

python3 - "$tmp" "$code" "$STATE" "$SOFT_DAILY" "$HARD_DAILY" "$HALT_HELPER" <<'PY'
import json, sys, datetime, subprocess
from pathlib import Path
raw_path, code, state_path, soft, hard, halt_helper = sys.argv[1:7]
soft = float(soft); hard = float(hard)
try:
    payload = json.loads(Path(raw_path).read_text() or "{}")
except Exception:
    payload = {}
data = payload.get("data") or payload
usage_daily = data.get("usage_daily")
usage_monthly = data.get("usage_monthly")
limit_remaining = data.get("limit_remaining")
ok = code == "200"
halt = False
reason = None
try:
    ud = float(usage_daily) if usage_daily is not None else None
except (TypeError, ValueError):
    ud = None
if ok and ud is not None and ud >= hard:
    halt = True
    reason = f"openrouter_daily_hard_cap usage_daily={ud} hard={hard}"
elif ok and limit_remaining is not None:
    try:
        if float(limit_remaining) <= 0:
            halt = True
            reason = "openrouter_limit_remaining_exhausted"
    except (TypeError, ValueError):
        pass
state = {
    "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ok": ok,
    "http": code,
    "usage_daily": usage_daily,
    "usage_monthly": usage_monthly,
    "limit_remaining": limit_remaining,
    "soft_daily": soft,
    "hard_daily": hard,
    "halt": halt,
    "reason": reason,
}
Path(state_path).write_text(json.dumps(state, indent=2) + "\n")
if halt:
    subprocess.run([halt_helper, "set", reason or "budget"], check=False)
    print(f"LEDGER HALT: {reason}")
    sys.exit(0)
if ok and ud is not None and ud >= soft:
    print(f"LEDGER SOFT: usage_daily={ud} soft={soft}")
PY
rc=$?
rm -f "$tmp"
exit 0

#!/usr/bin/env bash
# LockBox live redeem — grant verify FIRST, then Doppler fetch to a 0600 delivery file.
# Never prints secret values. Requires lockbox bot-home env or explicit DOPPLER_TOKEN.
set -euo pipefail
ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
LB_ENV="${LOCKBOX_ENV:-$HOME/.hermes/profiles/lockbox/.env}"
JTI_DIR="${LOCKBOX_JTI_DIR:-$HOME/.hermes/carrier/lockbox/jti}"
KEY_FILE="${LOCKBOX_HMAC_KEY_FILE:-$HOME/.hermes/carrier/lockbox/keys/helm-grant-v1}"

usage() {
  cat <<EOF
Usage: $0 --grant PATH --subject BOT_ID --ref SECRET_NAME [--delivery-dir DIR] [--access-request PATH]
EOF
  exit 2
}

GRANT=""; SUBJECT=""; REF=""; DELIV_DIR=""; REQ=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --grant) GRANT="$2"; shift 2 ;;
    --subject) SUBJECT="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --delivery-dir) DELIV_DIR="$2"; shift 2 ;;
    --access-request) REQ="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown $1" >&2; usage ;;
  esac
done
[[ -n "$GRANT" && -n "$SUBJECT" && -n "$REF" ]] || usage
[[ -f "$GRANT" ]] || { echo "missing grant $GRANT" >&2; exit 2; }
[[ -f "$LB_ENV" ]] || { echo "missing $LB_ENV" >&2; exit 2; }

# Load env without echoing
set -a
# shellcheck disable=SC1090
source "$LB_ENV"
set +a

if [[ "${LOCKBOX_SHADOW_MODE:-true}" == "true" ]]; then
  echo "REFUSE: LOCKBOX_SHADOW_MODE=true" >&2
  exit 1
fi
[[ -n "${DOPPLER_TOKEN:-}" ]] || { echo "missing DOPPLER_TOKEN" >&2; exit 2; }
PROJECT="${DOPPLER_PROJECT:-carrier-ops}"
CONFIG="${DOPPLER_CONFIG:-prd}"

VERIFY_ARGS=(
  python3 "$ROOT/scripts/lockbox_verify_grant.py" "$GRANT"
  --expect-subject "$SUBJECT"
  --jti-dir "$JTI_DIR"
  --redeem-refs "$REF"
  --key-file "$KEY_FILE"
)
if [[ -n "$REQ" ]]; then
  VERIFY_ARGS+=(--access-request "$REQ")
fi
"${VERIFY_ARGS[@]}"

DELIV_DIR="${DELIV_DIR:-$HOME/.hermes/carrier/lockbox/deliveries/$SUBJECT}"
mkdir -p "$DELIV_DIR"
chmod 700 "$DELIV_DIR"
# unique delivery file
OUT="$DELIV_DIR/$(basename "$REF" | tr -cd 'A-Za-z0-9._-').$$.$RANDOM.env"
umask 077
# Fetch value into file only
if ! doppler secrets get "$REF" -p "$PROJECT" -c "$CONFIG" -t "$DOPPLER_TOKEN" --plain >"$OUT"; then
  rm -f "$OUT"
  echo "ERROR: doppler get failed for ref (name only): $REF" >&2
  exit 1
fi
chmod 600 "$OUT"
# Write KEY=value form if plain value only
if ! grep -q '=' "$OUT"; then
  # rewrite as exportable env assignment without displaying
  python3 - <<PY
from pathlib import Path
p = Path("$OUT")
val = p.read_text()
# strip single trailing newline for assignment cleanliness
if val.endswith("\n"):
    val = val[:-1]
p.write_text("$REF=" + val + "\n")
p.chmod(0o600)
PY
fi

# Redacted audit
python3 - <<PY
import json, os
from datetime import datetime, timezone
from pathlib import Path
vault = os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home()/"Desktop/Existing Folders/OBSIDIAN"))
p = Path(vault)/"_agent/lockbox/audit.jsonl"
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a") as f:
    f.write(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "live_redeem",
        "subject_bot": "$SUBJECT",
        "secret_ref": "$REF",
        "grant": "$GRANT",
        "delivery_path": "$OUT",
        "project": "$PROJECT",
        "config": "$CONFIG",
        "status": "fulfilled"
    }) + "\n")
print("FULFILLED delivery_path=$OUT ref=$REF subject=$SUBJECT")
print("NOTE: secret value written to delivery file only; not printed")
PY

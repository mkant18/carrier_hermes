#!/usr/bin/env bash
# Carrier Hermes — Windows primary fleet wire-up (run in Git Bash AFTER
# windows_primary_bootstrap.ps1 + hermes auth + doppler login).
#
# Usage (Git Bash):
#   export CARRIER_HERMES_ROOT="$HOME/carrier_hermes"
#   bash "$CARRIER_HERMES_ROOT/scripts/windows_primary_fleet_setup.sh"
#
# Safe: no secret printing. MFA Discord token create is human-only.
set -euo pipefail

ROOT="${CARRIER_HERMES_ROOT:-$HOME/carrier_hermes}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export CARRIER_HERMES_ROOT="$ROOT"
export HERMES_HOME

echo "=== windows_primary_fleet_setup ==="
echo "ROOT=$ROOT"
echo "HERMES_HOME=$HERMES_HOME"

if [[ ! -d "$ROOT/.git" ]]; then
  echo "FAIL: carrier_hermes not at $ROOT — clone it first" >&2
  exit 1
fi

cd "$ROOT"
git pull --ff-only origin main || true

# ---------------------------------------------------------------------------
echo ""
echo "=== billing self-test ==="
python3 "$ROOT/scripts/or_billing_policy.py"
python3 "$ROOT/scripts/billing_guard.py" --fix-env --fix-config || {
  echo "billing_guard FAIL — fix before continuing" >&2
  exit 1
}

# ---------------------------------------------------------------------------
echo ""
echo "=== copy scripts to HERMES_HOME/scripts ==="
mkdir -p "$HERMES_HOME/scripts" "$HERMES_HOME/carrier"
cp -f "$ROOT/scripts/"*.sh "$HERMES_HOME/scripts/" 2>/dev/null || true
cp -f "$ROOT/scripts/"*.py "$HERMES_HOME/scripts/" 2>/dev/null || true
chmod +x "$HERMES_HOME/scripts/"*.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
echo ""
echo "=== Doppler inventory (names only) ==="
if command -v doppler >/dev/null 2>&1; then
  if doppler secrets --project carrier-ops --config prd --only-names 2>/dev/null; then
    echo "Doppler OK"
  else
    echo "WARN: doppler not logged in or no access — run: doppler login && doppler setup --project carrier-ops --config prd"
  fi
else
  echo "WARN: doppler CLI missing"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== pull common secrets into homes (length only; never echo values) ==="
pull_secret() {
  local key="$1"
  doppler secrets get "$key" --project carrier-ops --config prd --plain 2>/dev/null || true
}

write_env_key() {
  # write_env_key <file> <KEY> <value>  — never prints value
  local file="$1" key="$2" val="$3"
  [[ -z "$val" ]] && return 0
  mkdir -p "$(dirname "$file")"
  touch "$file"
  chmod 600 "$file" 2>/dev/null || true
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    grep -v "^${key}=" "$file" > "${file}.tmp" || true
    mv "${file}.tmp" "$file"
  fi
  # Use python to append safely (values may contain =)
  KEY="$key" VAL="$val" FILE="$file" python3 - <<'PY'
import os
from pathlib import Path
p = Path(os.environ["FILE"])
k, v = os.environ["KEY"], os.environ["VAL"]
with p.open("a", encoding="utf-8") as f:
    f.write(f"{k}={v}\n")
print(f"  wrote {k} len={len(v)} prefix={v[:4]}...")
PY
}

if command -v doppler >/dev/null 2>&1; then
  # Default home
  for k in OPENROUTER_API_KEY OPENROUTER_MANAGEMENT_KEY TODOIST_API_TOKEN GITHUB_TOKEN \
           DISCORD_FLEET_BOT_TOKEN DISCORD_FIRSTWATCH_BOT_TOKEN; do
    v=$(pull_secret "$k")
    if [[ -n "$v" ]]; then
      # normalize First Watch name
      outk="$k"
      [[ "$k" == "DISCORD_FIRSTWATCH_BOT_TOKEN" ]] && outk="DISCORD_FLEET_BOT_TOKEN"
      write_env_key "$HERMES_HOME/.env" "$outk" "$v"
    else
      echo "  missing in Doppler: $k"
    fi
  done

  # Helm gateway token only on chief_of_staff
  cos_tok=$(pull_secret "DISCORD_BOT_TOKEN")
  [[ -z "$cos_tok" ]] && cos_tok=$(pull_secret "CARRIER_OPS_DISCORD_TOKEN")
  if [[ -n "$cos_tok" ]]; then
    mkdir -p "$HERMES_HOME/profiles/chief_of_staff"
    write_env_key "$HERMES_HOME/profiles/chief_of_staff/.env" "DISCORD_BOT_TOKEN" "$cos_tok"
  else
    echo "  missing: DISCORD_BOT_TOKEN / CARRIER_OPS_DISCORD_TOKEN for Helm"
  fi

  # LockBox Doppler service tokens if present (names may vary)
  mkdir -p "$HERMES_HOME/profiles/lockbox"
  for k in DOPPLER_TOKEN DOPPLER_SERVICE_TOKEN LOCKBOX_DOPPLER_TOKEN; do
    v=$(pull_secret "$k")
    if [[ -n "$v" ]]; then
      write_env_key "$HERMES_HOME/profiles/lockbox/.env" "$k" "$v"
    fi
  done
  # shadow default
  if [[ -f "$HERMES_HOME/profiles/lockbox/.env" ]]; then
    grep -q '^LOCKBOX_SHADOW_MODE=' "$HERMES_HOME/profiles/lockbox/.env" 2>/dev/null \
      || echo 'LOCKBOX_SHADOW_MODE=true' >> "$HERMES_HOME/profiles/lockbox/.env"
  else
    echo 'LOCKBOX_SHADOW_MODE=true' > "$HERMES_HOME/profiles/lockbox/.env"
    chmod 600 "$HERMES_HOME/profiles/lockbox/.env" 2>/dev/null || true
  fi
else
  echo "SKIP secret pull — no doppler"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== install bot homes + SOULs ==="
bash "$ROOT/scripts/install_bot_homes.sh"

# ---------------------------------------------------------------------------
echo ""
echo "=== wing tokens (if in Doppler) ==="
bash "$ROOT/scripts/wire_wing_tokens.sh" || echo "WARN: wire_wing_tokens partial"

# ---------------------------------------------------------------------------
echo ""
echo "=== carrier-roster skill → Helm ==="
mkdir -p "$HERMES_HOME/skills/carrier-roster"
mkdir -p "$HERMES_HOME/profiles/chief_of_staff/skills/carrier-roster"
if [[ -d "$ROOT/skills/carrier-roster" ]]; then
  cp -R "$ROOT/skills/carrier-roster/"* "$HERMES_HOME/skills/carrier-roster/" 2>/dev/null || true
  cp -R "$ROOT/skills/carrier-roster/"* "$HERMES_HOME/profiles/chief_of_staff/skills/carrier-roster/" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== apply_bot_matrix (QUIT Hermes Desktop first if pins drift) ==="
echo "Press Enter to continue, or Ctrl-C to stop and quit Desktop..."
read -r _ || true
bash "$ROOT/scripts/apply_bot_matrix.sh"

# ---------------------------------------------------------------------------
echo ""
echo "=== billing_guard (final) ==="
python3 "$ROOT/scripts/billing_guard.py" --fix-env --fix-config

# ---------------------------------------------------------------------------
echo ""
echo "=== smoke_fleet ==="
bash "$ROOT/scripts/smoke_fleet.sh" || echo "smoke_fleet reported failures — read output above"

# ---------------------------------------------------------------------------
echo ""
echo "=== OPTIONAL: OpenRouter workspace allowlist ==="
if grep -q '^OPENROUTER_MANAGEMENT_KEY=.\+' "$HERMES_HOME/.env" 2>/dev/null; then
  python3 "$ROOT/scripts/sync_or_billing_guardrail.py" || echo "WARN: OR guardrail sync failed"
else
  echo "SKIP sync_or_billing_guardrail (no OPENROUTER_MANAGEMENT_KEY)"
fi

echo ""
echo "=== windows_primary_fleet_setup DONE ==="
echo "Still required from you if missing:"
echo "  - hermes auth: xai-oauth + anthropic OAuth"
echo "  - OBSIDIAN_VAULT_PATH in $HERMES_HOME/.env"
echo "  - OPENROUTER_API_KEY if not in Doppler (create at openrouter.ai/keys)"
echo "  - Discord wing apps MFA tokens per docs/DISCORD_WING_APPS.md"
echo "  - NEVER set ANTHROPIC_API_KEY or XAI_API_KEY"
echo ""
echo "Daily:"
echo "  hermes desktop"
echo "  # or Helm bot chat via Bot Mode"
echo "  bash $ROOT/scripts/smoke_fleet.sh"

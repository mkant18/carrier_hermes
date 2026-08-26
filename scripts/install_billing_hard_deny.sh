#!/usr/bin/env bash
# install_billing_hard_deny.sh — MAXIMUM OpenRouter billing hard-deny for Carrier Hermes
#
# Installs on THIS machine (Mac or Windows Git Bash / WSL):
#   1. Policy scripts already in-repo (or_billing_policy / billing_guard / sync_or)
#   2. carrier-billing-guard Hermes plugin → ~/.hermes/plugins/
#   3. Enable plugin in config.yaml
#   4. Scrub all profile configs
#   5. Push OpenRouter workspace ALLOWLIST (needs OPENROUTER_MANAGEMENT_KEY)
#   6. Patch local hermes-agent core refuse points (survives until next hermes update;
#      re-run this script after updates)
#   7. apply_bot_matrix if present
#
# Usage:
#   bash scripts/install_billing_hard_deny.sh
#   bash scripts/install_billing_hard_deny.sh --skip-or-sync
#   bash scripts/install_billing_hard_deny.sh --skip-core-patch
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKIP_OR=0
SKIP_CORE=0
for arg in "$@"; do
  case "$arg" in
    --skip-or-sync) SKIP_OR=1 ;;
    --skip-core-patch) SKIP_CORE=1 ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
  esac
done

echo "=== Carrier billing HARD DENY install ==="
echo "ROOT=$ROOT"
echo "HERMES_HOME=$HERMES_HOME"

# --- 1. Policy present ---
for f in or_billing_policy.py billing_guard.py billing_policy.py sync_or_billing_guardrail.py; do
  if [[ ! -f "$ROOT/scripts/$f" ]]; then
    echo "FAIL: missing $ROOT/scripts/$f" >&2
    exit 1
  fi
done
python3 "$ROOT/scripts/or_billing_policy.py"
echo "policy self_test OK"

# --- 2. Plugin ---
PLUGIN_SRC="$ROOT/plugins/carrier-billing-guard"
PLUGIN_DST="$HERMES_HOME/plugins/carrier-billing-guard"
if [[ ! -d "$PLUGIN_SRC" ]]; then
  echo "FAIL: plugin source missing at $PLUGIN_SRC" >&2
  exit 1
fi
mkdir -p "$HERMES_HOME/plugins"
rm -rf "$PLUGIN_DST"
cp -R "$PLUGIN_SRC" "$PLUGIN_DST"
# drop pycache if copied
rm -rf "$PLUGIN_DST/__pycache__" 2>/dev/null || true
echo "plugin installed → $PLUGIN_DST"

# Enable plugin in config (default profile)
python3 - <<'PY'
import os
from pathlib import Path
import yaml
home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
cfg_path = home / "config.yaml"
cfg = {}
if cfg_path.exists():
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
plugins = cfg.setdefault("plugins", {})
if not isinstance(plugins, dict):
    plugins = {}
    cfg["plugins"] = plugins
enabled = plugins.setdefault("enabled", [])
if not isinstance(enabled, list):
    enabled = []
    plugins["enabled"] = enabled
if "carrier-billing-guard" not in enabled:
    enabled.append("carrier-billing-guard")
entries = plugins.setdefault("entries", {})
if not isinstance(entries, dict):
    entries = {}
    plugins["entries"] = entries
entries.setdefault("carrier-billing-guard", {})["allow_tool_override"] = False
# Ensure disabled list does not include it
dis = plugins.get("disabled")
if isinstance(dis, list) and "carrier-billing-guard" in dis:
    dis.remove("carrier-billing-guard")
cfg_path.parent.mkdir(parents=True, exist_ok=True)
cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False), encoding="utf-8")
print(f"enabled carrier-billing-guard in {cfg_path}")
PY

# Also try hermes CLI enable if available
if command -v hermes >/dev/null 2>&1; then
  hermes plugins enable carrier-billing-guard 2>/dev/null || true
fi

# --- 3. Scrub configs ---
python3 "$ROOT/scripts/billing_guard.py" --hermes-home "$HERMES_HOME" --fix-env --fix-config
echo "billing_guard PASS"

# --- 4. OpenRouter workspace allowlist ---
if [[ "$SKIP_OR" -eq 0 ]]; then
  if python3 "$ROOT/scripts/sync_or_billing_guardrail.py"; then
    echo "OR guardrail synced"
  else
    echo "WARN: OR guardrail sync failed — set OPENROUTER_MANAGEMENT_KEY in $HERMES_HOME/.env" >&2
  fi
else
  echo "skip OR sync"
fi

# --- 5. Core hermes-agent patches ---
if [[ "$SKIP_CORE" -eq 0 ]]; then
  python3 "$ROOT/scripts/apply_hermes_core_billing_patches.py" || {
    echo "WARN: core patch apply had issues — plugin + OR allowlist still protect" >&2
  }
else
  echo "skip core patch"
fi

# --- 6. Matrix (optional) ---
if [[ -x "$ROOT/scripts/apply_bot_matrix.sh" ]]; then
  echo "Running apply_bot_matrix.sh (pins + final billing gate)..."
  bash "$ROOT/scripts/apply_bot_matrix.sh" || {
    echo "WARN: apply_bot_matrix returned non-zero" >&2
  }
fi

echo ""
echo "=== DONE — billing HARD DENY installed ==="
echo "Restart Hermes desktop / gateway / bot sessions so the plugin loads."
echo "Re-run this script after every 'hermes update' (core patches can be wiped)."
echo "Verify anytime:"
echo "  python3 $ROOT/scripts/or_billing_policy.py"
echo "  python3 $ROOT/scripts/billing_guard.py"
echo "  python3 $ROOT/scripts/sync_or_billing_guardrail.py"

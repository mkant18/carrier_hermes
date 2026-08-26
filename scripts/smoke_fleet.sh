#!/usr/bin/env bash
# Fleet smokes. Prints PASS/FAIL per check. Exit 1 if any required check fails.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Windows/MSYS: `pwd` returns /c/Users/... which native python/git misread as
# C:\c\Users\... . Normalize to a native path when pwd -W is available (Git Bash).
if command -v cygpath >/dev/null 2>&1; then
  ROOT="$(cygpath -m "$ROOT")"
elif [[ "$ROOT" =~ ^/([a-zA-Z])/ ]]; then
  drive="${BASH_REMATCH[1]}"
  ROOT="${drive^^}:/${ROOT:3}"
fi
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
fail=0
pass() { echo "PASS  $1"; }
failc() { echo "FAIL  $1 — $2"; fail=1; }
skip() { echo "SKIP  $1 — $2"; }

echo "=== carrier_hermes smoke ==="

# 1 classify golden
if python3 "$ROOT/scripts/classify_golden.py" >/tmp/carrier_classify.out 2>/tmp/carrier_classify.err; then
  pass "classify_golden ($(tail -1 /tmp/carrier_classify.out))"
else
  failc "classify_golden" "$(tr '\n' ' ' </tmp/carrier_classify.err)"
fi

# 2 lock + spend halt refuse
bash "$ROOT/scripts/dispatch_lock.sh" clear >/dev/null
bash "$ROOT/scripts/spend_halt.sh" clear >/dev/null
if bash "$ROOT/scripts/dispatch_preflight.sh" | grep -q PREFLIGHT_OK; then
  pass "preflight_open"
else
  failc "preflight_open" "expected OK"
fi
bash "$ROOT/scripts/dispatch_lock.sh" set "smoke-lock" >/dev/null
if bash "$ROOT/scripts/dispatch_preflight.sh" >/tmp/pf.out; then
  failc "lock_refuse" "preflight succeeded under lock"
else
  grep -q REFUSE /tmp/pf.out && pass "lock_refuse" || failc "lock_refuse" "$(cat /tmp/pf.out)"
fi
bash "$ROOT/scripts/dispatch_lock.sh" clear >/dev/null
bash "$ROOT/scripts/spend_halt.sh" set "smoke-halt" >/dev/null
if bash "$ROOT/scripts/dispatch_preflight.sh" >/tmp/pf.out; then
  failc "halt_refuse" "preflight succeeded under halt"
else
  grep -q REFUSE /tmp/pf.out && pass "halt_refuse" || failc "halt_refuse" "$(cat /tmp/pf.out)"
fi
bash "$ROOT/scripts/spend_halt.sh" clear >/dev/null

# 3 aipass round-trip Helm → Clerk
if out=$(python3 "$ROOT/scripts/aipass_send.py" --from chief_of_staff --to obsidian_archivist --mission "smoke-intake" --body $'## REPORT\n\nok\n' --vault "$VAULT" 2>/tmp/aipass.err); then
  if [[ -f "$out" ]]; then
    pass "aipass_send ($out)"
  else
    failc "aipass_send" "no file $out"
  fi
else
  failc "aipass_send" "$(cat /tmp/aipass.err)"
fi

# 4 OSB read
if [[ -d "$VAULT" ]]; then
  if ls "$VAULT" >/dev/null 2>&1; then
    pass "osb_vault_readable"
  else
    failc "osb_vault_readable" "cannot list vault"
  fi
else
  failc "osb_vault_readable" "missing $VAULT"
fi

# 5 model pings (one-shot, short timeout)
# Windows-robust: resolve the hermes launcher (may be hermes.cmd/.exe), route
# via shutil.which, feed stdin=DEVNULL (else the CLI can block), and write
# capture files into a tmp dir that exists on this OS.
PING_TMP="${TMPDIR:-${TEMP:-/tmp}}"
mkdir -p "$PING_TMP" 2>/dev/null || PING_TMP="/tmp"
ping_model() {
  local name="$1" provider="$2" model="$3"
  if python3 - "$provider" "$model" "$PING_TMP/ping_${name}.out" "$PING_TMP/ping_${name}.err" <<'PY'
import subprocess, sys, shutil, os
provider, model, outp, errp = sys.argv[1:5]
hermes = shutil.which("hermes") or shutil.which("hermes.cmd") or shutil.which("hermes.exe") or "hermes"
try:
    r = subprocess.run(
        [hermes, "-z", "Reply with the single word PONG.", "--provider", provider, "-m", model],
        capture_output=True, text=True, timeout=90,
        stdin=subprocess.DEVNULL, shell=(os.name == "nt" and hermes.lower().endswith(".cmd")),
    )
    open(outp, "w").write(r.stdout or "")
    open(errp, "w").write(r.stderr or "")
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    open(errp, "w").write("timed out")
    sys.exit(124)
except Exception as e:
    open(errp, "w").write(f"launch error: {e}")
    sys.exit(125)
PY
  then
    if grep -qi pong "$PING_TMP/ping_$name.out"; then
      pass "ping_$name"
    else
      failc "ping_$name" "no PONG in $(head -c 120 "$PING_TMP/ping_$name.out")"
    fi
  else
    failc "ping_$name" "$(tr '\n' ' ' <"$PING_TMP/ping_$name.err" | head -c 200)"
  fi
}
ping_model grok xai-oauth grok-4.5
ping_model claude anthropic claude-sonnet-4-6
# DeepSeek requires OPENROUTER_API_KEY
if grep -qE '^OPENROUTER_API_KEY=.' "${HERMES_HOME:-$HOME/.hermes}/.env" 2>/dev/null; then
  ping_model deepseek openrouter deepseek/deepseek-chat-v3-0324
else
  skip "ping_deepseek" "OPENROUTER_API_KEY not set (commented/missing)"
fi

# 6 Chronos does not claim Todoist
if grep -qi 'todoist' "$ROOT/bots/calendar_manager/SOUL.md" && grep -qi 'do not' "$ROOT/bots/calendar_manager/SOUL.md"; then
  if grep -q 'todoist_manager' "$ROOT/bots/calendar_manager/SOUL.md" || grep -q 'Tasker' "$ROOT/bots/calendar_manager/SOUL.md"; then
    pass "chronos_handoff_tasker"
  else
    failc "chronos_handoff_tasker" "no Tasker pointer"
  fi
else
  # still require Tasker mention
  grep -q 'Tasker' "$ROOT/bots/calendar_manager/SOUL.md" && pass "chronos_handoff_tasker" || failc "chronos_handoff_tasker" "Chronos SOUL missing Tasker handoff"
fi

# 7 twenty bots defined (canonical roster per bots/BOT_MATRIX.md — 18 core + Marshal + Yeoman)
n=$(ls "$ROOT"/bots/*/SOUL.md | wc -l | tr -d ' ')
[[ "$n" == "20" ]] && pass "twenty_souls" || failc "twenty_souls" "count=$n"

# 7b no SOUL left as an unfilled scaffold stub
stubs=$(grep -l "TODO: fill in purpose" "$ROOT"/bots/*/SOUL.md 2>/dev/null | wc -l | tr -d ' ')
[[ "$stubs" == "0" ]] && pass "no_stub_souls" || failc "no_stub_souls" "$stubs scaffold SOUL(s) unfilled"

# 8 bot homes
homes=0
missing_homes=""
while read -r id; do
  if [[ -d "$HOME/.hermes/profiles/$id" ]]; then
    homes=$((homes + 1))
  else
    missing_homes="$missing_homes $id"
  fi
done <<'IDS'
chief_of_staff
marshal
subscription_watcher
api_watcher
lockbox
coding_lt
firstmate
git_yeoman
hermes_ai_explorer
passive_watch
ops_lt
email_reader
email_drafter
calendar_manager
todoist_manager
knowledge_lt
vault_librarian
obsidian_archivist
research_agent
finance_reader
IDS
[[ "$homes" == "20" ]] && pass "twenty_bot_homes" || failc "twenty_bot_homes" "homes=$homes missing:$missing_homes"

# 8b Lieutenants model check via hermes config get (serve-based, may lag apply script)
# NOTE: check #11 (lt_pin_disk_*) reads directly from YAML and is authoritative.
# This check is kept as a secondary signal for live serve state.
for lt in coding_lt ops_lt knowledge_lt; do
  m=$(hermes -p "$lt" config get model.default 2>/dev/null \
    || hermes -p "$lt" config get model 2>/dev/null || true)
  if [[ "$m" == *"claude-sonnet-4-6"* ]]; then
    pass "lt_model_$lt"
  else
    failc "lt_model_$lt" "expected claude-sonnet-4-6, got '$m' (check lt_pin_disk_* for authoritative YAML state)"
  fi
done

# 8c Lt SOULs must declare their squadron (routing node, not executor)
if grep -q 'firstmate' "$ROOT/bots/coding_lt/SOUL.md" \
  && grep -q 'email_reader' "$ROOT/bots/ops_lt/SOUL.md" \
  && grep -q 'vault_librarian' "$ROOT/bots/knowledge_lt/SOUL.md"; then
  pass "lt_squadrons_declared"
else
  failc "lt_squadrons_declared" "an Lt SOUL is missing its squadron refs"
fi

# 9 lockbox grant verify (shadow fixture if present)
if [[ -f "$HOME/.hermes/carrier/lockbox/keys/helm-grant-v1" ]]; then
  if python3 "$ROOT/scripts/lockbox_verify_grant.py" --help >/dev/null 2>&1; then
    pass "lockbox_verify_help"
  else
    failc "lockbox_verify_help" "script broken"
  fi
else
  skip "lockbox_hmac_key" "key not generated yet"
fi

# 10 fleet_signal.sh — identity-aware smoke (Helm posting to #fleet)
if [[ -f "$ROOT/scripts/fleet_signal.sh" ]]; then
  if bash "$ROOT/scripts/fleet_signal.sh" RAW chief_of_staff \
      "**[smoke]** fleet_signal identity smoke — $(date -u +%Y-%m-%dT%H:%M:%SZ)" fleet \
      2>/tmp/fleet_signal_smoke.err; then
    pass "fleet_signal_post"
  else
    failc "fleet_signal_post" "$(cat /tmp/fleet_signal_smoke.err)"
  fi
else
  failc "fleet_signal_post" "scripts/fleet_signal.sh not found"
fi

# 10b identity registry — all 18 bots registered in bot_identities.py
if [[ -f "$ROOT/scripts/bot_identities.py" ]]; then
  reg_count=$(python3 -c "
import sys; sys.path.insert(0, '$ROOT/scripts')
from bot_identities import BOTS
print(len(BOTS))
" 2>/dev/null || echo "0")
  if [[ "$reg_count" == "20" ]]; then
    pass "bot_identities_registry (20 bots)"
  else
    failc "bot_identities_registry" "expected 20, got $reg_count"
  fi
else
  failc "bot_identities_registry" "scripts/bot_identities.py not found"
fi

# 10c gateway guard — no unauthorized gateways, guardrails in place
if [[ -f "$ROOT/scripts/gateway_guard.sh" ]]; then
  if bash "$ROOT/scripts/gateway_guard.sh" 2>/tmp/gw_guard.err; then
    pass "gateway_guard"
  else
    failc "gateway_guard" "$(grep FAIL /tmp/gw_guard.err 2>/dev/null | head -3 | tr '\n' ' ')"
  fi
else
  failc "gateway_guard" "scripts/gateway_guard.sh not found"
fi

# 11 Lt model pins on disk (direct YAML read — bypasses serve clobber)
for lt_bot in coding_lt ops_lt knowledge_lt; do
  lt_model=$(python3 -c "
import yaml, pathlib, sys
p = pathlib.Path.home() / '.hermes/profiles' / sys.argv[1] / 'config.yaml'
cfg = yaml.safe_load(p.read_text()) if p.exists() else {}
print((cfg or {}).get('model', {}).get('default', ''))
" "$lt_bot" 2>/dev/null || true)
  lt_prov=$(python3 -c "
import yaml, pathlib, sys
p = pathlib.Path.home() / '.hermes/profiles' / sys.argv[1] / 'config.yaml'
cfg = yaml.safe_load(p.read_text()) if p.exists() else {}
print((cfg or {}).get('model', {}).get('provider', ''))
" "$lt_bot" 2>/dev/null || true)
  if [[ "$lt_model" == "claude-sonnet-4-6" && "$lt_prov" == "anthropic" ]]; then
    pass "lt_pin_disk_$lt_bot"
  else
    failc "lt_pin_disk_$lt_bot" "wanted anthropic/claude-sonnet-4-6, got $lt_prov/$lt_model"
  fi
done

# GitHub auth (never prints tokens)
if bash "$ROOT/scripts/smoke_github_auth.sh" --quiet; then
  pass "github_auth"
else
  failc "github_auth" "run: bash scripts/smoke_github_auth.sh for full report"
fi

# Billing hard-guard: never Anthropic/Grok via API token or OpenRouter
if [[ -f "$ROOT/scripts/billing_guard.py" ]]; then
  if python3 "$ROOT/scripts/billing_guard.py" --quiet-ok; then
    pass "billing_guard_no_anthropic_grok_api"
  else
    failc "billing_guard_no_anthropic_grok_api" "Anthropic/Grok API token or OpenRouter frontier route detected"
  fi
else
  failc "billing_guard_no_anthropic_grok_api" "scripts/billing_guard.py missing"
fi

echo "=== done fail=$fail ==="
exit "$fail"

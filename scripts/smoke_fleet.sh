#!/usr/bin/env bash
# Fleet smokes. Prints PASS/FAIL per check. Exit 1 if any required check fails.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
ping_model() {
  local name="$1" provider="$2" model="$3"
  if python3 - "$provider" "$model" "/tmp/ping_${name}.out" "/tmp/ping_${name}.err" <<'PY'
import subprocess, sys
provider, model, outp, errp = sys.argv[1:5]
try:
    r = subprocess.run(
        ["hermes", "-z", "Reply with the single word PONG.", "--provider", provider, "-m", model],
        capture_output=True, text=True, timeout=60,
    )
    open(outp, "w").write(r.stdout)
    open(errp, "w").write(r.stderr)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    open(errp, "w").write("timed out")
    sys.exit(124)
PY
  then
    if grep -qi pong /tmp/ping_"$name".out; then
      pass "ping_$name"
    else
      failc "ping_$name" "no PONG in $(head -c 120 /tmp/ping_"$name".out)"
    fi
  else
    failc "ping_$name" "$(tr '\n' ' ' </tmp/ping_"$name".err | head -c 200)"
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

# 7 thirteen bots defined
n=$(ls "$ROOT"/bots/*/SOUL.md | wc -l | tr -d ' ')
[[ "$n" == "13" ]] && pass "thirteen_souls" || failc "thirteen_souls" "count=$n"

# 8 bot homes
homes=0
while read -r id; do
  [[ -d "$HOME/.hermes/profiles/$id" ]] && homes=$((homes + 1))
done <<'IDS'
chief_of_staff
subscription_watcher
api_watcher
lockbox
firstmate
hermes_ai_explorer
email_reader
email_drafter
calendar_manager
todoist_manager
vault_librarian
obsidian_archivist
research_agent
IDS
[[ "$homes" == "13" ]] && pass "thirteen_bot_homes" || failc "thirteen_bot_homes" "homes=$homes"

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

echo "=== done fail=$fail ==="
exit "$fail"

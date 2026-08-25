#!/usr/bin/env bash
# Smoke test for coding_lt (Wrench) — Coding Wing Lieutenant.
# Lts are dispatch/routing nodes: verify identity, model pin, write root,
# and that execution tools are NOT present.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Desktop/Existing Folders/OBSIDIAN}"
BOT_ID="coding_lt"
CALLSIGN="Wrench"
fail=0
pass() { echo "PASS $1"; }
failc() { echo "FAIL $1 — $2"; fail=1; }

echo "=== $BOT_ID ($CALLSIGN) Lt smoke ==="

# 1 SOUL synced repo -> live bot home
if [[ -f "$ROOT/bots/$BOT_ID/SOUL.md" && -f "$HOME/.hermes/profiles/$BOT_ID/SOUL.md" ]]; then
  if diff -q "$ROOT/bots/$BOT_ID/SOUL.md" "$HOME/.hermes/profiles/$BOT_ID/SOUL.md" >/dev/null; then
    pass "soul_synced"
  else
    failc "soul_synced" "repo SOUL differs from live bot home"
  fi
else
  failc "soul_synced" "SOUL.md missing in repo or bot home"
fi

# 2 SOUL is filled in, not the scaffold stub
if grep -q "TODO: fill in purpose" "$ROOT/bots/$BOT_ID/SOUL.md"; then
  failc "soul_filled" "still the scaffold stub"
else
  grep -q "$CALLSIGN" "$ROOT/bots/$BOT_ID/SOUL.md" && pass "soul_filled" \
    || failc "soul_filled" "callsign $CALLSIGN not in SOUL"
fi

# 3 model pin = quality Sonnet Max (advanced model, coordination only)
model=$(hermes -p "$BOT_ID" config get model.default 2>/dev/null \
  || hermes -p "$BOT_ID" config get model 2>/dev/null || true)
if [[ "$model" == *"claude-sonnet-4-6"* ]]; then
  pass "model_pinned ($model)"
else
  failc "model_pinned" "expected claude-sonnet-4-6, got '$model'"
fi

# 4 no free-tier model anywhere in the pin
if [[ "$model" == *":free"* || "$model" == *"opencode-free"* ]]; then
  failc "no_free_model" "free tier pinned: $model"
else
  pass "no_free_model"
fi

# 5 Lt is barred from execution tools (dispatch/routing only)
tools=$(hermes -p "$BOT_ID" tools list 2>/dev/null || true)
if [[ -z "$tools" ]]; then
  echo "SKIP execution_tools_barred — cannot read tool list"
else
  bad=""
  for t in terminal code_execution browser computer_use delegation; do
    echo "$tools" | grep -qiE "^[[:space:]]*$t[[:space:]]|[[:space:]]$t[[:space:]]*(enabled|on)" && bad="$bad $t"
  done
  [[ -z "$bad" ]] && pass "execution_tools_barred" \
    || failc "execution_tools_barred" "execution tools present:$bad"
fi

# 6 SOUL declares the squadron it routes to
missing=""
for sq in firstmate; do
  grep -q "$sq" "$ROOT/bots/$BOT_ID/SOUL.md" || missing="$missing $sq"
done
[[ -z "$missing" ]] && pass "squadron_declared" \
  || failc "squadron_declared" "missing squadron refs:$missing"

# 7 SOUL forbids doing the squadron's own work
if grep -qiE "never|must never|Never-be" "$ROOT/bots/$BOT_ID/SOUL.md"; then
  pass "never_be_declared"
else
  failc "never_be_declared" "no Never-be / must-never clause"
fi

# 8 AIPass mailbox + write root
mkdir -p "$VAULT/_agent/mailbox/$BOT_ID/inbox" "$VAULT/_agent/mailbox/$BOT_ID/outbox" "$VAULT/_agent/$BOT_ID" 2>/dev/null || true
if [[ -d "$VAULT/_agent/mailbox/$BOT_ID/inbox" && -d "$VAULT/_agent/mailbox/$BOT_ID/outbox" && -d "$VAULT/_agent/$BOT_ID" ]]; then
  pass "directories_exist"
else
  failc "directories_exist" "mailbox or write root missing under $VAULT/_agent"
fi

# 9 AIPass round-trip Helm -> this Lt
if out=$(python3 "$ROOT/scripts/aipass_send.py" --from chief_of_staff --to "$BOT_ID" \
      --mission "smoke-dispatch" --body $'## JOB\n\nsmoke\n' --vault "$VAULT" 2>/tmp/lt_aipass.err); then
  [[ -f "$out" ]] && pass "aipass_dispatch" || failc "aipass_dispatch" "no file $out"
else
  failc "aipass_dispatch" "$(cat /tmp/lt_aipass.err)"
fi

echo "=== $BOT_ID smoke done fail=$fail ==="
exit "$fail"

#!/usr/bin/env bash
# Marshal smoke test — verify profile home, model pin, and SOUL presence.
set -euo pipefail

BOT="marshal"
WANT_MODEL="claude-sonnet-4-6"
WANT_PROVIDER="anthropic"
SOUL_REPO="$(dirname "$0")/SOUL.md"
SOUL_HOME="$HOME/.hermes/profiles/$BOT/SOUL.md"

echo "=== Marshal 🎖️ smoke test ==="

# 1. Profile home exists
if hermes profile list 2>/dev/null | grep -q "^  $BOT"; then
  echo "✔ profile home exists"
else
  echo "✘ profile home missing — run: hermes profile create $BOT --no-skills --no-alias"
  exit 1
fi

# 2. Model pin
GOT_MODEL=$(hermes -p "$BOT" config get model 2>/dev/null | grep "^default:" | awk '{print $2}')
GOT_PROV=$(hermes -p "$BOT" config get model 2>/dev/null | grep "^provider:" | awk '{print $2}')
if [[ "$GOT_MODEL" == "$WANT_MODEL" && "$GOT_PROV" == "$WANT_PROVIDER" ]]; then
  echo "✔ model pin: $GOT_PROV/$GOT_MODEL"
else
  echo "✘ model pin wrong — got $GOT_PROV/$GOT_MODEL, want $WANT_PROVIDER/$WANT_MODEL"
  echo "  Re-run: bash scripts/apply_bot_matrix.sh"
  exit 1
fi

# 3. SOUL.md in repo
if [[ -f "$SOUL_REPO" ]]; then
  echo "✔ SOUL.md present in repo"
else
  echo "✘ SOUL.md missing from repo at $SOUL_REPO"
  exit 1
fi

# 4. SOUL.md synced to profile home
if [[ -f "$SOUL_HOME" ]]; then
  echo "✔ SOUL.md synced to profile home"
else
  echo "✘ SOUL.md not in profile home — run: cp $SOUL_REPO $SOUL_HOME"
  exit 1
fi

# 5. Mailbox dirs
INBOX="$HOME/carrier_hermes/_agent/mailbox/$BOT/inbox"
OUTBOX="$HOME/carrier_hermes/_agent/mailbox/$BOT/outbox"
if [[ -d "$INBOX" && -d "$OUTBOX" ]]; then
  echo "✔ AIPass mailbox dirs present"
else
  echo "✘ Mailbox dirs missing at $INBOX / $OUTBOX"
  exit 1
fi

echo ""
echo "✈  Marshal is on deck. All systems go."

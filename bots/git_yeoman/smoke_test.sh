#!/usr/bin/env bash
# Yeoman smoke test — verify profile, model pin, SOUL, mailbox, and gh CLI auth.
set -euo pipefail

BOT="git_yeoman"
WANT_MODEL="grok-4.5"
WANT_PROVIDER="xai-oauth"
SOUL_REPO="$(dirname "$0")/SOUL.md"
SOUL_HOME="$HOME/.hermes/profiles/$BOT/SOUL.md"

echo "=== Yeoman 📋 smoke test ==="

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

# 5. AIPass mailbox dirs
INBOX="$HOME/carrier_hermes/_agent/mailbox/$BOT/inbox"
OUTBOX="$HOME/carrier_hermes/_agent/mailbox/$BOT/outbox"
if [[ -d "$INBOX" && -d "$OUTBOX" ]]; then
  echo "✔ AIPass mailbox dirs present"
else
  echo "✘ Mailbox dirs missing at $INBOX / $OUTBOX"
  exit 1
fi

# 6. gh CLI available and authenticated
if command -v gh &>/dev/null; then
  if gh auth status &>/dev/null; then
    GH_USER=$(gh api user --jq '.login' 2>/dev/null || echo "unknown")
    echo "✔ gh CLI authenticated as: $GH_USER"
  else
    echo "⚠ gh CLI present but not authenticated — run: gh auth login"
    echo "  (Yeoman needs gh auth to access GitHub repos)"
  fi
else
  echo "⚠ gh CLI not installed — run: brew install gh && gh auth login"
  echo "  (Yeoman requires gh CLI for all GitHub operations)"
fi

# 7. Dependabot config present in repo
DEPENDABOT="$HOME/carrier_hermes/.github/dependabot.yml"
if [[ -f "$DEPENDABOT" ]]; then
  echo "✔ dependabot.yml present in .github/"
else
  echo "⚠ dependabot.yml missing — create .github/dependabot.yml to enable Dependabot"
fi

echo ""
echo "✈  Yeoman is on deck. All systems go."

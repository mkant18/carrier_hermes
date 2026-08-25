#!/usr/bin/env bash
# scaffold_bot.sh — Boatswain scaffold: lay down a new bot's deck plates.
#
# Usage: bash scripts/scaffold_bot.sh <bot_id> <callsign>
#   bot_id   — machine id, lowercase_underscore (e.g. finance_reader)
#   callsign — naval callsign, one word, Title case (e.g. Ledger)
#
# SAFE: creates repo directories and stub files only.
# NO SECRETS are touched. No Doppler. No Discord applications.
# Next human steps are printed at the end.
#
# Companion: skills/carrier/boatswain-new-bot/SKILL.md
#            docs/DISCORD_BOT_IDENTITY_MATRIX.md
set -euo pipefail

# ── Args ──────────────────────────────────────────────────────────────────────
if [[ $# -lt 2 ]]; then
  echo "Usage: bash scripts/scaffold_bot.sh <bot_id> <callsign>" >&2
  echo "  e.g. bash scripts/scaffold_bot.sh finance_reader Ledger" >&2
  exit 1
fi

BOT_ID="$1"
CALLSIGN="$2"
ROOT="${CARRIER_HERMES_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BOT_DIR="$ROOT/bots/$BOT_ID"
PROFILE_DIR="$HOME/.hermes/profiles/$BOT_ID"
MAILBOX_BASE="$ROOT/_agent/mailbox/$BOT_ID"
SKILLS_DIR="$ROOT/skills/carrier"

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ ! "$BOT_ID" =~ ^[a-z][a-z0-9_]+$ ]]; then
  echo "ERROR: bot_id must be lowercase_underscore (got: $BOT_ID)" >&2
  exit 1
fi

if [[ -d "$BOT_DIR" ]]; then
  echo "WARNING: $BOT_DIR already exists — skipping directory creation, files will not be overwritten."
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Boatswain scaffold — $BOT_ID ($CALLSIGN)"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Repo bot directory ─────────────────────────────────────────────────────
echo "▶ 1/5  Laying deck plates: $BOT_DIR"
mkdir -p "$BOT_DIR"

SOUL_FILE="$BOT_DIR/SOUL.md"
if [[ ! -f "$SOUL_FILE" ]]; then
  cat > "$SOUL_FILE" <<SOUL
# ${CALLSIGN} — SOUL.md

**Bot id:** \`${BOT_ID}\`
**Callsign:** **${CALLSIGN}**
**Protocol:** \`docs/INTER_AGENT_PROTOCOL.md\`
**AIPass:** \`_agent/mailbox/${BOT_ID}/{inbox,outbox}/\` via \`scripts/aipass_send.py\`
**Matrix:** \`bots/BOT_MATRIX.md\`

<!-- TODO: fill in purpose, authority, model, tools, write roots, return contract -->

## Authority

<!-- One paragraph: what this bot is authorized to do and what it must never do. -->

## Model

\`quality\`  <!-- or specialist/watcher/lockbox — see BOT_MATRIX.md -->

## Tools

<!-- List enabled toolsets. Cross-reference BOT_MATRIX.md row. -->

## Write roots

<!-- Directories this bot may write to. Be specific. -->

## Return

<!-- Format: status, paths_touched[], summary ≤40 lines, blockers[]. -->
SOUL
  echo "   ✔ Created SOUL stub: $SOUL_FILE"
else
  echo "   ↷ SOUL.md already exists — skipping."
fi

# ── 2. AIPass mailbox dirs ────────────────────────────────────────────────────
echo "▶ 2/5  Rigging AIPass mailbox: $MAILBOX_BASE"
mkdir -p "$MAILBOX_BASE/inbox" "$MAILBOX_BASE/outbox"
echo "   ✔ mailbox/inbox and mailbox/outbox created."

# ── 3. Hermes profile home ────────────────────────────────────────────────────
echo "▶ 3/5  Preparing profile home stub: $PROFILE_DIR"
mkdir -p "$PROFILE_DIR"
if [[ ! -f "$PROFILE_DIR/SOUL.md" ]]; then
  cp "$SOUL_FILE" "$PROFILE_DIR/SOUL.md"
  echo "   ✔ Copied SOUL.md to profile home."
else
  echo "   ↷ Profile SOUL.md already exists — skipping."
fi

# ── 4. BOT_MATRIX checklist stub ─────────────────────────────────────────────
echo "▶ 4/5  BOT_MATRIX row reminder"
MATRIX_HINT="| \`${BOT_ID}\` | ${CALLSIGN} | \`quality\` | TODO | TODO | TODO |"
echo ""
echo "   Add this row to bots/BOT_MATRIX.md (fill in Model/Toolsets/MCP):"
echo ""
echo "   $MATRIX_HINT"
echo ""

# ── 5. Smoke hook placeholder ─────────────────────────────────────────────────
echo "▶ 5/5  Smoke hook placeholder: $BOT_DIR/smoke_test.sh"
if [[ ! -f "$BOT_DIR/smoke_test.sh" ]]; then
  cat > "$BOT_DIR/smoke_test.sh" <<'SMOKE'
#!/usr/bin/env bash
# Smoke test for this bot. Run after hermes profile create.
# Fill in an actual test for the bot's primary capability.
set -euo pipefail
BOT_ID="$(basename "$(dirname "$0")")"
echo "[smoke] $BOT_ID — no smoke tests defined yet."
# Example:
# hermes -p "$BOT_ID" run --one-shot "Echo: smoke test" | grep -q "smoke test"
# echo "[smoke] $BOT_ID PASS"
SMOKE
  chmod +x "$BOT_DIR/smoke_test.sh"
  echo "   ✔ Created smoke_test.sh stub."
else
  echo "   ↷ smoke_test.sh already exists — skipping."
fi

# ── Human next steps ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  NEXT STEPS — Manual (human required)"
echo "══════════════════════════════════════════════════════════════════"
echo ""
echo "  A. Fill in SOUL.md:"
echo "     $BOT_DIR/SOUL.md"
echo ""
echo "  B. Add BOT_MATRIX.md row (see reminder above)."
echo ""
echo "  C. Create the Hermes bot home:"
echo "     hermes profile create $BOT_ID --no-skills --no-alias"
echo "     hermes profile describe $BOT_ID --text '${CALLSIGN} — <one-line description>'"
echo ""
echo "  D. Copy SOUL.md into profile home:"
echo "     cp $BOT_DIR/SOUL.md $PROFILE_DIR/SOUL.md"
echo ""
echo "  E. Apply model pin and toolset config:"
echo "     bash $ROOT/scripts/apply_bot_matrix.sh  (or add a pin block for $BOT_ID)"
echo ""
echo "  F. Discord face decision:"
echo "     See docs/DISCORD_BOT_IDENTITY_MATRIX.md — decision tree §2."
echo "     If sharing First Watch (outbound only): no token work needed."
echo "     If new Discord App: follow §4 of that document (MFA required)."
echo ""
echo "  G. Secrets (if any):"
echo "     Helm issues ACCESS_REQUEST → HANDSHAKE_GRANT → LockBox redeems."
echo "     Never pass token values directly. See docs/INTER_AGENT_PROTOCOL.md §2.4."
echo ""
echo "  H. Smoke test:"
echo "     bash $BOT_DIR/smoke_test.sh"
echo ""
echo "  I. Commit SOUL.md, BOT_MATRIX row, and smoke_test.sh to carrier_hermes."
echo "     Do NOT commit .env, tokens, or Doppler secrets."
echo ""
echo "  ✈  $CALLSIGN is on deck. Await Michael's clearance to launch."
echo ""

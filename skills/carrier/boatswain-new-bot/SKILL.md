---
name: boatswain-new-bot
description: "Use when creating a new Hermes bot for the Carrier fleet. End-to-end runbook: SOUL stub, profile create, BOT_MATRIX row, mailbox, Discord wiring decision, smoke hook."
version: 1.0.0
author: Boatswain automation (Mission Alpha)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [carrier, fleet, bot, onboarding, boatswain, discord, naval]
    related_skills: [signal-lamp-discord, carrier-roster]
---

# Boatswain — New Bot Runbook

The boatswain keeps the ship's lines in order. This skill is his deck log: every step to bring a new crew member aboard the Carrier Hermes fleet, from keel-laying to first launch.

**Product language:** always **bot**, never "profile" to Michael.  
**Repo root:** `~/carrier_hermes`  
**Fleet docs:** `bots/BOT_MATRIX.md`, `docs/INTER_AGENT_PROTOCOL.md`

---

## 0. Pre-flight Check

Before cutting steel, answer these questions:

1. **Does a bot for this role already exist?** Check `bots/BOT_MATRIX.md`. If yes, extend the existing bot.
2. **Is this a new inbound Discord voice?** If so, read `docs/DISCORD_BOT_IDENTITY_MATRIX.md` §2 (decision tree) *before* any Discord work.
3. **Does it need secrets?** Secrets route through Helm → LockBox only. Never embed values.
4. **Has Michael approved the new roster slot?** Phase B bots need explicit approval.

---

## 1. Choose a Bot ID and Callsign

| Field | Rules |
|---|---|
| `bot_id` | `lowercase_underscore`, unique, matches intended specialization (e.g. `finance_reader`) |
| Callsign | One word, Title case, naval flavor (e.g. `Ledger`, `Probe`, `Chart`) — this is the bot's voice identity |

Callsigns already in use: `Helm`, `Vigil`, `Ledger`, `LockBox`, `Mate`, `Chart`, `Sonar`, `Probe`, `Inbox`, `Quill`, `Chronos`, `Tasker`, `Librarian`, `Clerk`.

---

## 2. Scaffold Repo Directories

Run the Boatswain scaffold script (safe — no secrets, no live calls):

```bash
bash ~/carrier_hermes/scripts/scaffold_bot.sh <bot_id> <Callsign>
```

This creates:
- `bots/<bot_id>/SOUL.md` — stub SOUL file
- `bots/<bot_id>/smoke_test.sh` — stub smoke test
- `_agent/mailbox/<bot_id>/inbox/` and `outbox/` — AIPass mailbox dirs
- `~/.hermes/profiles/<bot_id>/SOUL.md` — profile home stub (copy)
- Prints the `BOT_MATRIX.md` row hint and all manual next steps

---

## 3. Write the SOUL.md

Open `bots/<bot_id>/SOUL.md` and fill in all TODO sections:

```markdown
# <Callsign> — SOUL.md

**Bot id:** `<bot_id>`
**Callsign:** **<Callsign>**
**Protocol:** `docs/INTER_AGENT_PROTOCOL.md`
**AIPass:** `_agent/mailbox/<bot_id>/{inbox,outbox}/` via `scripts/aipass_send.py`
**Matrix:** `bots/BOT_MATRIX.md`

## Authority
<one paragraph: what it can do, what it must never do, never-be list>

## Model
`<quality|specialist|watcher|lockbox>` <model name>

## Tools
<enabled toolsets; cross-reference BOT_MATRIX.md>

## Write roots
<specific directories only>

## Return
status, paths_touched[], summary ≤40 lines, blockers[]
```

Cross-reference `bots/chief_of_staff/SOUL.md` and `bots/firstmate/SOUL.md` as style anchors.

---

## 4. Add the BOT_MATRIX.md Row

Open `bots/BOT_MATRIX.md` and insert a row in the correct section (Command / Coding / Ops):

```markdown
| `<bot_id>` | <Callsign> | `<model tier>` | <toolsets ON> | <toolsets OFF> | <MCP> |
```

Be explicit. If a tool is not in the ON list, the bot should not have it.

---

## 5. Create the Hermes Bot Home (human — CLI required)

```bash
hermes profile create <bot_id> --no-skills --no-alias
hermes profile describe <bot_id> --text '<Callsign> — <one-line description>'
cp ~/carrier_hermes/bots/<bot_id>/SOUL.md ~/.hermes/profiles/<bot_id>/SOUL.md
```

Verify:
```bash
hermes profile list | grep <bot_id>
```

---

## 6. Apply Model Pin and Toolset Config

Add a `pin` + `off` block for the new bot to `scripts/apply_bot_matrix.sh`, then run it:

```bash
# In apply_bot_matrix.sh, add:
pin <bot_id> <model-name> <provider>
off <bot_id> mail todoist calendar browser computer_use  # adjust per SOUL

# Then run:
bash ~/carrier_hermes/scripts/apply_bot_matrix.sh
```

Verify:
```bash
hermes -p <bot_id> config get model
```

---

## 7. Discord Wiring Decision

Load `skills/carrier/signal-lamp-discord/SKILL.md` (or see `docs/DISCORD_BOT_IDENTITY_MATRIX.md`) and follow the decision tree.

**TL;DR paths:**
- Bot only posts outbound → **share First Watch** token (REST send, zero new setup)
- Bot needs webhook-only alerts → **webhook** (no token at all)
- Bot needs a gateway (receive) → **new Discord App** (MFA required; rare; Michael approves)
- Internal only → **no Discord face** (AIPass + Kanban)

---

## 8. Secrets (if any)

```
Helm issues:  ACCESS_REQUEST
              ↓
              APPROVE | DENY | NARROW
              ↓
              HANDSHAKE_GRANT (HMAC helm-grant-v1, short TTL)
              ↓
LockBox redeems → redacted result to requesting bot
```

Never embed tokens in SOUL.md, config.yaml, or any committed file.

---

## 9. Skills (if any)

If the bot uses specialist skills, copy them into the bot's profile home:

```bash
mkdir -p ~/.hermes/profiles/<bot_id>/skills/<category>
cp ~/carrier_hermes/skills/<category>/SKILL.md ~/.hermes/profiles/<bot_id>/skills/<category>/SKILL.md
```

---

## 10. Update INTER_AGENT_PROTOCOL.md

Add the new bot as a subsection under **§2 Identities** using the standard identity table:

```markdown
### 2.N `<bot_id>` — **<Callsign>**

| Field | Spec |
|---|---|
| Voice | ... |
| Never-be | ... |
| Authority | ... |
| Model | ... |
| Speaks to | ... |
| Knowledge | ... |
| Tools | ... |
| Write roots | ... |
| Return to Michael | ... |
```

---

## 11. Smoke Test

```bash
bash ~/carrier_hermes/bots/<bot_id>/smoke_test.sh
```

Fill in `smoke_test.sh` with a real capability check (e.g., `hermes -p <bot_id> run --one-shot "ping"`).

---

## 12. Commit to Carrier Hermes

```bash
cd ~/carrier_hermes
git add bots/<bot_id>/SOUL.md bots/<bot_id>/smoke_test.sh
git add bots/BOT_MATRIX.md docs/INTER_AGENT_PROTOCOL.md
git add _agent/mailbox/<bot_id>/  # gitkeep files if needed
git commit -m "feat(fleet): onboard <bot_id> (<Callsign>) — Boatswain scaffold"
git push origin main
```

**Do NOT commit:** `.env`, tokens, Doppler secrets, `config.yaml` with embedded keys.

---

## Pitfalls

- **Never copy a bot home's `config.yaml` from another bot** — model pins and toolset disables are bot-specific.
- **Profile home ≠ repo** — `~/.hermes/profiles/<id>/` is the live home; `~/carrier_hermes/bots/<id>/` is the source of truth. Keep SOUL.md in sync.
- **Callsign must be unique** — duplicates break Helm's dispatch routing.
- **`hermes profile create` may fail silently if the id already exists** — always verify with `hermes profile list`.
- **Smoke test before announcing** — a bot that can't respond to a ping isn't on deck yet.
- **Phase A freeze** — `docs/INTER_AGENT_PROTOCOL.md` is frozen Phase A. New bots must comply with all §1 design goals; no exceptions without Michael's written approval.

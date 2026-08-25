# Carrier Hermes — FULL IMPLEMENTATION PROMPT (v4)

> **Paste this entire prompt into a fresh Hermes session with full tool access.**
> Goal: stand up the Carrier Hermes **bot fleet** (Hermes **Bot Mode** roster), cost-optimally, with AIPass hybrid mail, OSB, dual watchers beside Helm, Clerk intake, Tasker, and shadow-mode safety.
>
> **Language rule:** Always say **bot**. Never tell Michael you “created a profile” except when quoting the CLI (`hermes profile create` = create bot home). Bot Mode UI = roster of bots.

---

## CRITICAL ORDERING

```
Phase A — PROTOCOL + BOT IDENTITY FREEZE  (must finish + commit)
        ↓
Phase B — BUILD bot homes, AIPass mail, OSB, crons, smokes
```

Do **not** create bot homes, aliases, crons, or MCP until Phase A checklist is green.

---

## Authority order

1. `bots/README.md` + `bots/*/SOUL.md` — canonical bot identities  
2. `docs/INTER_AGENT_PROTOCOL.md` — relationships / packets  
3. `integrations/aipass-mailbox.md` — hybrid AIPass bot mail  
4. `integrations/obsidian-second-brain.md`  
5. `.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md`  
6. This prompt  

---

## Non-negotiables

1. **Bots, not “profiles” in product language.** 12 bots in `bots/README.md`.  
2. **Helm** front door; **Vigil** + **Ledger** sit **beside** Helm and monitor **all** sessions (not coding-only).  
3. Preflight: `DISPATCH_LOCK` **or** `SPEND_HALT` → no new metered dispatches.  
4. Subscription-first models; email/calendar/todoist specialists = **paid DeepSeek only** (no `:free` rotate).  
5. Vigil heartbeat = `no_agent` script; Ledger prefer script + OpenRouter usage API.  
6. Named bots via Kanban / bot routines / bot-chat / **AIPass mailbox** — never CoS `delegate_task` leaves for Inbox/Quill/Chronos/Tasker/Librarian/Clerk/Scout/Vigil/Ledger.  
7. Knowledge split: **Librarian** query-out, **Clerk** intake-in (with Helm keep/discard).  
8. **Tasker** owns Todoist; **Chronos** owns calendar (+ handoff mail to Tasker).  
9. AIPass = **hybrid file mailbox only** (`vendored/aipass-mailbox`). Do **not** `pip install aipass`, no `.trinity/`, no `.ai_mail.local/`.  
10. Vault TL0 until Michael raises; Clerk stages under `_agent/archivist/` unless intake enabled.  
11. No mail send tools anywhere.

---

# PHASE A — PROTOCOL & BOT FREEZE (BEFORE BUILD)

## A0 — Read

```bash
cat ~/carrier_hermes/bots/README.md
ls ~/carrier_hermes/bots/*/SOUL.md
cat ~/carrier_hermes/docs/INTER_AGENT_PROTOCOL.md | head -200
cat ~/carrier_hermes/integrations/aipass-mailbox.md
hermes kanban --help 2>/dev/null | head -20
# Desktop Bot Mode: note how bots appear in UI if present
```

Write `docs/HERMES_CAPABILITY_NOTES.md`: Bot Mode availability, Kanban, cron, bot-chat, peer.

## A1 — Deepen inter-bot + AIPass protocol

Update `docs/INTER_AGENT_PROTOCOL.md` so it fully covers:

### Identities (all 12 bots)
Helm, Vigil, Ledger, Mate, Scout, Inbox, Quill, Chronos, Tasker, Librarian, Clerk, Probe — callsign, voice, never-be, authority.

### Relationships
- Command triangle: Helm ↔ Vigil ↔ Ledger (fleet-wide)  
- Clerk ↔ Helm keep/discard; Clerk vs Librarian  
- Chronos → (AIPass/job) → Tasker  
- Post-run: any bot outbox → Clerk candidates via Helm  
- Forbidden peer edges  

### Knowledge bases
Per-bot system/session/blackboard/OSB/mailbox access + forbidden knowledge (e.g. Chronos no email bodies).

### Tools matrix
Exact toolsets + MCP include/exclude per bot. Ledger/Vigil: no domain ops.

### How Helm “chats” with bots (detailed)
Channels (priority order to freeze after capability notes):

| Priority | Channel | Use |
|---|---|---|
| 1 | Kanban / bot job as target bot | Durable scoped work |
| 2 | Bot cron / routine | Periodic |
| 3 | **AIPass mailbox** | Async handoff/report without full orchestration turn |
| 4 | bot-chat deliver | Expensive full turn |
| 5 | delegate_task | **Denied** for named ops/command bots |

Document job packet + result packet + **AIPass message** mapping (when to use mail vs Kanban).

### AIPass section (mandatory)
- Paths under `_agent/mailbox/<bot_id>/{inbox,outbox}`  
- send via `scripts/aipass_send.py`  
- Helm drains inbox → jobs  
- Clerk consumes intake mails  
- Ledger/Vigil may mail Helm on halt  

### Resolve open decisions
Board name, Discord channels, primary channel, shadow exit, FirstMate backend order, OpenRouter spend API approach for Ledger.

Commit: `docs: Phase A freeze — bots + AIPass protocol`

## A2 — Artifacts before build

Create/update:

- `templates/job_packet.md`, `result_packet.md`  
- `templates/examples/{triage,coding,explorer,vault,intake,todoist,spend_halt}.md`  
- `templates/aipass_message.md`  
- `profiles/PROFILE_MATRIX.md` **rename conceptually to** `bots/BOT_MATRIX.md` (tools × models) — keep both if needed  
- `skills/carrier-roster/SKILL.md` (Bot Mode roster skill for Helm)  
- `GOVERNANCE.md`, `COST_MODEL.md`  
- Ensure every `bots/*/SOUL.md` has bot_id, callsign, protocol + AIPass pointers  
- `docs/CLASSIFICATION_GOLDEN.md` ≥18 prompts including: spend halt, intake after research, todoist-only, calendar→tasks, vault question vs save-to-vault  

### Phase A acceptance (all required)

- [ ] 12 bots listed and SOULs consistent  
- [ ] Vigil ≠ Sentry; Ledger fleet-wide; watchers beside Helm  
- [ ] Clerk vs Librarian split clear  
- [ ] Tasker vs Chronos split clear  
- [ ] AIPass hybrid documented + not full pip AIPass  
- [ ] Channel priority frozen in capability notes  
- [ ] Templates + golden set + roster skill  
- [ ] Commit done  

**STOP and report Phase A summary.** Then Phase B.

---

# PHASE B — BUILD BOT FLEET

## B0 — Prerequisites

Credentials: xai-oauth, anthropic oauth, OPENROUTER_API_KEY.  
`OBSIDIAN_VAULT_PATH`. OSB repo. Phase A commit present.

```bash
VAULT="/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN"
mkdir -p "$VAULT/_agent"/{email,drafts,calendar,todoist,research,watcher,api_watcher,librarian,archivist,explorer,state,audit,mailbox}
# per-bot mailboxes — see integrations/aipass-mailbox.md setup snippet
```

## B1 — Scripts

`dispatch_lock.sh`, spend halt helper, `watcher_heartbeat.sh`, `api_watcher_heartbeat.sh` (OpenRouter usage), `aipass_send.py`, `audit_append.sh`, `smoke_fleet.sh`, schemas.

Test:

```bash
python3 ~/carrier_hermes/scripts/aipass_send.py --from chief_of_staff --to obsidian_archivist --mission "test-intake" --body "## REPORT\n\nok\n"
```

## B2 — Models / MoA / fallback

As cost plan: specialist/rote/cheap = paid DeepSeek only. No free specialist pins.

## B3 — OSB

`integrations/obsidian-second-brain.md` — skills + MCP; exclude Inbox writes at TL0; Clerk gets write path only when intake enabled.

## B4 — Create **bots** (Bot Mode roster)

For each bot_id in `bots/README.md`:

```bash
# CLI verb is profile create — product is BOT
hermes profile create <bot_id> 2>/dev/null || true
cp ~/carrier_hermes/bots/<bot_id>/SOUL.md ~/.hermes/profiles/<bot_id>/SOUL.md
hermes -p <bot_id> profile describe "<Callsign> — <one line from bots/README>"
# Apply BOT_MATRIX toolsets, model pins, MCP filters
```

Ensure Desktop/Bot Mode lists them as **bots** with descriptions.  
Gateway inbound: **Helm only** (unless multi-bot Discord explicitly designed).  
Vigil + Ledger: crons, not user-facing Discord bots unless desired.

## B5 — AIPass mailbox tree

Create all inbox/outbox dirs; install PROTOCOL.md; smoke send Helm→Clerk.

## B6 — Dispatch runtime

Wire primary channel from Phase A. Helm skill loads roster + packet templates.  
Post-run hook pattern: workers AIPass-mail Clerk or Helm with artifact paths.

## B7 — Crons

| Bot | Schedule | Mode |
|---|---|---|
| Vigil | every 5m | no_agent heartbeat |
| Ledger | every 10–15m | no_agent spend check |
| Scout | 2–3×/week | agent |
| Clerk | optional daily drain of intake mail | agent |
| Chronos / Inbox | as needed shadow | agent |

## B8 — Smokes

- Classify golden set → callsign  
- Lock + spend halt refuse dispatch  
- aipass_send round-trip  
- OSB read  
- GROK/CLAUDE/DEEPSEEK pings  
- Chronos does not claim Todoist when Tasker exists  

## B9 — Checklist + commit/push carrier_hermes

Report PASS/FAIL. Shadow mode remains for live Todoist/calendar mutations and Clerk permanent vault writes until TL raised.

---

## Out of scope

Live SMTP send; full AIPass pip/trinity; free specialist rotation; Trust Level >0 without Michael; OpenClaw/Podiom reinstall.

---

## Done means

1. Phase A freeze committed  
2. 12 bots on roster with SOULs/tools  
3. AIPass hybrid mail working  
4. Vigil+Ledger fleet-wide halts  
5. Golden classification smokes pass  

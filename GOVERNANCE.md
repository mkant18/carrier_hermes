# Governance — Carrier Hermes

Constitution + **structural** enforcement. SOUL text is not enough.

**Bots, not “profiles,”** in product language. CLI `hermes profile` only creates a bot home.

---

## Rules → controls

| Rule | Structural control |
|---|---|
| One face to Michael | Gateway inbound = Helm only. Other bots have no Discord consume unless explicitly designed later. |
| No sends | No mail-send MCP/CLI in any bot `hermes -p <id> tools` dump. Quill writes `_agent/drafts/` + `#drafts` only. |
| Vault TL0 | OSB MCP excludes `obsidian_save_note`, `obsidian_capture`, `obsidian_update_note` except Clerk after `trust_override: intake_enabled`. File writes: `_agent/**` only. |
| Tool scope | Per-bot home toolsets + MCP include/exclude (`bots/BOT_MATRIX.md`). Dispatch via Kanban assignee = that home. |
| No fake specialists | Helm `delegate_task` **denied** for named ops/command bots (inherits Helm tools). |
| Idempotency | `_agent/<domain>/state.json` + schema validator before side effects. |
| Dual audit | Hermes `state.db` + `_agent/audit/events.jsonl` append-only + Discord `#alerts` on critical. |
| Kill / spend | `scripts/dispatch_lock.sh` → `DISPATCH_LOCK`; Ledger script → `SPEND_HALT`. Helm preflight both. |
| Prompt injection | Inbox: no discord/todoist/calendar/send; email bodies tagged untrusted; Helm never executes mail instructions. |
| Coding isolation | Mate only; worktrees; never push main; backends claude-code → codex → opencode. |
| Watchers fleet-wide | Vigil + Ledger sit **beside** Helm; monitor **all** sessions, not Mate-only. |
| Knowledge split | Librarian = query-out; Clerk = intake-in + Helm keep/discard. |
| Calendar vs tasks | Chronos calendar; Tasker Todoist; handoff via job/AIPass. |
| Cost pins | Inbox/Chronos/Tasker = paid DeepSeek only. Heartbeats = `no_agent`. |
| AIPass hybrid | Vendored file mailbox only. No pip AIPass / `.trinity/` / `.ai_mail.local/`. |
| Shadow | Todoist + calendar mutations + Clerk permanent writes off until Michael raises TL + smokes PASS. |

---

## Halt preflight (Helm)

Before **any** new metered dispatch:

1. `scripts/dispatch_lock.sh check` — exit 10 ⇒ refuse.  
2. `test -f ~/.hermes/carrier/SPEND_HALT` — present ⇒ refuse.  
3. Tell Michael the reason file contents.  
4. Standing override must be logged to `_agent/audit/events.jsonl`.

---

## Trust Level

| TL | Meaning |
|---|---|
| **0 (default)** | Read vault; write `_agent/` only; Clerk stages; no live Todoist/calendar mutations. |
| Raised by Michael | Clerk may file permanent notes when packet grants it; live ops still need explicit unshadow. |

Never raise TL in a commit without Michael’s sentence on record.

---

## Approval culture

Drafts → Discord `#drafts` → Michael checkmark (external). No reaction-bot required in V1. Nothing sends.

---

## Change control

Scout proposes. Helm presents. Michael picks IDs. Implementer/Mate applies in a **separate** change job. Explorer must not `hermes config set` live.

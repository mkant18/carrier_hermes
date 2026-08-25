# Governance — Carrier Hermes

Constitution + **structural** enforcement. SOUL text is not enough.

**Bots, not “profiles,”** in product language. CLI `hermes profile` only creates a bot home.

---

## Rules → controls

| Rule | Structural control |
|---|---|
| One face to Michael | Gateway inbound = Helm only. Other bots have no Discord consume unless explicitly designed later. |
| No sends | No mail-send MCP/CLI in any bot `hermes -p <id> tools` dump. Quill writes `_agent/drafts/` + `#drafts` only. |
| Vault TL0 (constitution) | Default MCP + non-Clerk homes exclude `obsidian_save_note`, `obsidian_capture`, `obsidian_update_note`. **Clerk** may use those tools only when packet has `trust_override: intake_enabled` (fleet intake unshadowed 2026-08-25). Constitution TL still 0 until Michael says `raise TL` + edits vault `CLAUDE.md`. File default: `_agent/**` only. |
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
| Shadow | **Partial exit 2026-08-25:** Todoist + calendar live; Clerk permanent only with `trust_override: intake_enabled`. See `prompts/SHADOW_MODE.md`. Vault TL raise is separate (`raise TL`). |
| Secrets only via LockBox + Helm handshake | Structural grant verify (`scripts/lockbox_verify_grant.py`) before Doppler; separate `lockbox` bot home; no secrets in AIPass/Discord/result summaries; deny default; atomic jti single-redeem; mandatory subject+expiry; subset checks. Signer is `lockbox_sign_grant.py` (Helm-only). |
| LockBox no China routing | Model pin Gemini Flash ↔ GPT-4o-mini only; never DeepSeek/specialist alias. |
| No rotation policy engine V1 | On-demand rotate only under grant; no forced calendar nags. |
| Break-glass | Michael → Helm `break_glass: true` on grant; still short TTL + audit; still no value logging. |
| HMAC V1 residual | Accepted: issuer/verifier share HMAC secret. Do not install signer on lockbox home. Optional later: ed25519 (Helm private, LockBox public). |

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
| **0 (current constitution)** | Read vault; default write `_agent/` only. Fleet: Todoist + calendar live (unshadowed). Clerk permanent file only with packet `trust_override: intake_enabled` + intake unshadow. |
| Raised by Michael (`raise TL` + vault `CLAUDE.md`) | Constitution allows scoped permanent writes beyond `_agent/` per level table in vault `CLAUDE.md`. |

Never raise TL in a commit without Michael’s sentence on record.

---

## Approval culture

Drafts → Discord `#drafts` → Michael checkmark (external). No reaction-bot required in V1. Nothing sends.

---

## Change control

Scout proposes. Helm presents. Michael picks IDs. Implementer/Mate applies in a **separate** change job. Explorer must not `hermes config set` live.

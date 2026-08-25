# Phase B status — 2026-08-25

Shadow **partial exit** 2026-08-25 (Session 2): Todoist + calendar live; Clerk intake grant-gated. Vault TL still **0**.

| Check | Result |
|---|---|
| Phase A freeze commit | PASS `a14a251` |
| 12→13 bot homes + SOULs + Bot Mode descriptions | PASS (incl. LockBox) |
| AIPass Helm→Clerk send | PASS |
| Vigil/Ledger lock+halt refuse | PASS |
| Golden classify | PASS (26 prompts on latest smoke) |
| OSB vault read + MCP stdio | PASS (default MCP still excludes Inbox writers; **Clerk home** may enable writes for grant-gated intake) |
| Grok ping (xai-oauth) | PASS |
| Claude ping (anthropic) | PASS |
| DeepSeek ping | **FAIL/flake** on 2026-08-25 re-smoke (timeout) — Tasker/Chronos pin risk |
| Chronos ≠ Tasker | PASS |
| Vigil cron every 5m `no_agent` | PASS |
| Ledger cron every 15m `no_agent` | PASS |
| Scout Tue/Thu 09:00 | PASS |
| Clerk daily drain | PASS created **paused** |
| Kanban board `carrier` | PASS |
| Live Todoist | **LIVE** (Michael: `unshadow Todoist`) |
| Live calendar | **LIVE** (Michael: `unshadow calendar`) |
| Clerk permanent | **GRANT-GATED** (`unshadow intake`; requires `trust_override: intake_enabled`; TL still 0) |

## Michael actions

1. Fix DeepSeek/OpenRouter path if Tasker/Chronos jobs will run hot (latest smoke timed out on ping).  
2. Optional: `raise TL` + edit vault `CLAUDE.md` for full constitutional permanent filing.  
3. Optional: `hermes kanban boards switch carrier`.  
4. Wire calendar MCP if Chronos writes are expected beyond policy allow.

## Audit

`_agent/audit/events.jsonl` — helm `unshadow` ×3 (Todoist, calendar, intake).

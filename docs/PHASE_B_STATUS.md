# Phase B status — 2026-08-25

Shadow **partial exit** + **vault TL2** (Session 2).

| Check | Result |
|---|---|
| Phase A freeze commit | PASS `a14a251` |
| Bot homes + SOULs | PASS (incl. LockBox) |
| Structural smokes (lock/halt/AIPass/OSB read/Chronos≠Tasker) | PASS (latest re-smoke; DeepSeek ping flaked) |
| Live Todoist | **LIVE** (`unshadow Todoist`) |
| Live calendar | **LIVE** (`unshadow calendar`) |
| Clerk permanent | **GRANT-GATED** (`unshadow intake` + packet `trust_override: intake_enabled`) |
| Vault constitution TL | **2** (`raise TL` 2026-08-25) — `Inbox/` create + `## Agent Notes` append |

## Audit

`_agent/audit/events.jsonl` — unshadow ×3 + `raise_tl` TL0→TL2.

## Open

1. DeepSeek/OpenRouter stability for Tasker/Chronos.  
2. Wire calendar MCP if Chronos writes are expected in production.  
3. Optional TL3 folder scopes later.

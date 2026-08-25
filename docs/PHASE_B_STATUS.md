# Phase B status — 2026-08-25

Shadow remains ON for Todoist mutations, calendar mutations, and Clerk permanent vault writes.

| Check | Result |
|---|---|
| Phase A freeze commit | PASS `a14a251` |
| 12 bot homes + SOULs + Bot Mode descriptions | PASS |
| AIPass Helm→Clerk send | PASS |
| Vigil/Ledger lock+halt refuse | PASS |
| Golden classify (22) | PASS |
| OSB vault read + MCP stdio | PASS (Inbox writers still excluded in default MCP filter) |
| Grok ping (xai-oauth) | PASS |
| Claude ping (anthropic) | PASS |
| DeepSeek ping | **SKIP** — `OPENROUTER_API_KEY` commented/missing in `~/.hermes/.env` |
| Chronos ≠ Tasker | PASS |
| Vigil cron every 5m `no_agent` | PASS `5c9e2d583117` |
| Ledger cron every 15m `no_agent` | PASS `94d873c5ad73` (no halt when key missing) |
| Scout Tue/Thu 09:00 | PASS `11406eb785ea` |
| Clerk daily drain | PASS created **paused** `45ba5f589891` |
| Kanban board `carrier` | PASS |
| Live Todoist/calendar/Clerk permanent | **SHADOW** |

## Michael actions (not done here)

1. Uncomment/set `OPENROUTER_API_KEY` in `~/.hermes/.env` so Ledger can measure $ and specialists can run.  
2. Paste Discord channel IDs into `docs/DISCORD_CHANNELS.md`.  
3. Raise TL / unshadow when ready (`prompts/SHADOW_MODE.md`).  
4. Optional: `hermes kanban boards switch carrier` when ready to make it the current board.

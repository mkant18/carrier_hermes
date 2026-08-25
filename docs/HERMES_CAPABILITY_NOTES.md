# Hermes capability notes — Carrier fleet (Phase A freeze)

**Frozen:** 2026-08-25  
**Install:** Hermes Agent desktop + CLI on macOS (`hermes` on PATH).  
**Product language:** **bot**. CLI still uses `hermes profile *` for bot homes under `~/.hermes/profiles/<bot_id>/`.

Sources: live `hermes --help` / `hermes profile` / `hermes kanban` / `hermes cron` / `hermes peer` on this machine, plus official docs (`/user-guide/bot-mode`, `/user-guide/features/kanban`, `/user-guide/features/cron`).

---

## Bot Mode (desktop)

| Fact | This install |
|---|---|
| Availability | Built into desktop; on by default (Settings → Plugins → Bots). |
| What a bot is | Isolated Hermes home: config, memory, skills, SOUL, cron routines, Bot Chat. |
| UI | **Bots** tab next to Sessions; roster row = avatar + title + description + last message. |
| Create | UI **New Agent**, or `hermes profile create <bot_id>` then `hermes -p <bot_id> profile describe --text "…"`. |
| Chat | `hermes -p <bot_id> chat` = same agent as Bot Chat. Canonical Bot Chat is forever (`/new` remaps to `/compact`). |
| Routines | Per-bot cron, named `[bot:<name>] …`, listed in `hermes cron list`. |
| Group chats | 2–6 bots; expensive (serial rounds). **Not** a Carrier dispatch channel. |
| Hide | Display-only; routines still run. |

**This machine (pre–Phase B):** only `default`, `chief_of_staff`, `hermes_ai_explorer`, `vault_librarian` exist as bot homes. Phase B creates the remaining 12-roster homes. Do not treat those three as the fleet.

---

## How Helm talks to bots — channel priority (FROZEN)

Pick the **lowest-cost durable** channel that fits. Never skip down the table because a higher channel is slightly less convenient.

| Priority | Channel | Hermes primitive | Cost | Use |
|---|---|---|---|---|
| **1** | **Kanban / job as target bot** | `hermes kanban create` + `--assignee <bot_id>` on board `carrier`; gateway dispatcher spawns that bot home | Worker turn on the **target** bot’s model/tools | Durable scoped work, retries, human visibility |
| **2** | **Bot cron / routine** | `hermes cron create` on target bot / `[bot:<id>]` name | Periodic target-bot turn, or **$0** if `no_agent` | Periodic (Vigil 5m script, Ledger 10–15m script, Chart 2–3×/week) |
| **3** | **AIPass mailbox** | `scripts/aipass_send.py` → `$VAULT/_agent/mailbox/<bot>/{inbox,outbox}/` | **$0 LLM** (file write) | Async handoff/report without a Helm orchestration turn |
| **4** | **bot-chat deliver** | Cron `deliver: bot-chat:<bot_id>` or inject into canonical Bot Chat | Full target-bot turn + Helm/cron wrap | Rare: need that bot’s full identity/memory in-chat |
| **5** | **`delegate_task`** | In-process child | Child **inherits caller tools** | **DENIED** for named ops/command bots (Inbox, Quill, Chronos, Tasker, Librarian, Clerk, Chart, Vigil, Ledger, Helm-as-leaf). Allowed only: Mate-internal coding roles, or ephemeral scratch with **no** privileged tools. |

**Not a dispatch channel:** Bot Mode group chat, `hermes peer` (cross-machine DM), Discord bot-to-bot chatter.

**Blackboard** (`$OBSIDIAN_VAULT_PATH/_agent/**`) is payload storage for packets/mail, not a sixth speak-channel.

---

## Kanban (primary dispatch)

- CLI: `hermes kanban` (`init`, `boards`, `create`, `assign`, `list`, `show`, `complete`, `dispatch`, `daemon`, …).
- DB: `~/.hermes/kanban.db` (default board) or `~/.hermes/kanban/boards/<slug>/kanban.db`.
- **Frozen board slug:** `carrier` (create in Phase B). Isolate fleet jobs from `default`.
- Assignee **must** be a real bot home name (`chief_of_staff`, `email_reader`, …). Dispatcher spawns `hermes -p <assignee>` with `kanban_*` tools and `HERMES_KANBAN_BOARD=carrier`.
- Workspace for ops bots: `dir:$OBSIDIAN_VAULT_PATH` (absolute) so `_agent/` persists. Coding: `worktree:` under the target repo.
- Worker tools: `kanban_show`, `kanban_complete`, `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`, `kanban_link` (plus that bot’s toolsets).
- Helm uses `kanban` toolset (create/list/assign) — does **not** execute domain work on the card.
- `delegate_task` is **not** equivalent: children inherit Helm tools and die with the parent process.

---

## Cron / routines

- CLI: `hermes cron create|list|edit|pause|run|remove`.
- `no_agent=true` + `script=` → stdout is the message; **empty stdout = silent**. Required for Vigil/Ledger heartbeats.
- Agent crons run a **fresh** session (no Helm chat history) — prompts must contain a full job packet.
- `deliver: bot-chat:<bot_id>` injects into that bot’s Bot Chat (priority 4).
- `deliver: local` = no human spam (good for scripts that only write lock files).
- Cron jobs **cannot** create more cron jobs (loop guard).
- Per-job model pin is user/CLI-owned (`hermes cron create --model …`); agent `cronjob` tool cannot set model pins.

---

## Bot Chat + peer

- **Bot Chat:** persistent per-bot conversation. Cron delivery `bot-chat` / `bot-chat:<profile>` is a full agent turn.
- **`hermes peer`:** DM another *machine’s* gateway API server. Out of scope for this single-Mac fleet. Do not use as Inbox↔Quill.
- **Gateway inbound:** **Helm only** (`chief_of_staff`). Vigil/Ledger are not user-facing Discord bots unless Michael later asks.

---

## Tools / MCP on this install (snapshot)

**Enabled toolsets (default home):** web, browser, terminal, file, code_execution, vision, image_gen, x_search, tts, skills, todo, memory, session_search, clarify, delegation, cronjob, computer_use.

**MCP:** hugging_face, kiwi (search-flight only), todoist (template import/export excluded), vercel, obsidian-second-brain (Inbox writers excluded: `obsidian_save_note`, `obsidian_capture`, `obsidian_update_note`), dropbox disabled.

Per-bot enablement is **structural** in each bot home (Phase B / `bots/BOT_MATRIX.md`). Default home staying fully tooled is fine; specialists must not inherit that set.

---

## Auth / models (snapshot)

- xAI OAuth present (SuperGrok).
- Anthropic OAuth present (Claude Max + claude_code).
- OpenRouter key expected in `~/.hermes/.env` as `OPENROUTER_API_KEY` (Phase B verifies; heartbeat uses `GET https://openrouter.ai/api/v1/key`).
- Default interactive model on `default` is unrelated to fleet pins. Fleet aliases freeze in `COST_MODEL.md` / `BOT_MATRIX.md`.

---

## Frozen open decisions

| # | Decision | Freeze |
|---|---|---|
| 1 | Kanban board | **`carrier`** |
| 2 | Discord channels | **Names** frozen: inbound = Helm home; `#drafts` = Quill; `#alerts` = Vigil + Ledger; `#fleet` = Chart/Sonar tips. **IDs** stay blank until Michael pastes them into `docs/DISCORD_CHANNELS.md`. Never invent IDs. |
| 3 | Primary dispatch | **Kanban on `carrier`** as target bot (priority 1). |
| 4 | Shadow exit | Stay shadow for Todoist mutations, calendar mutations, and Clerk **permanent** vault writes until Michael raises Trust Level **and** golden smokes PASS. See `prompts/SHADOW_MODE.md`. |
| 5 | FirstMate backends | **claude-code → codex → opencode → native Mate workers.** Coding never goes to generic Helm `delegate_task` leaves. |
| 6 | Ledger spend API | Script: `GET /api/v1/key` with `OPENROUTER_API_KEY` → `usage_daily`, `usage_monthly`, `limit_remaining`. Optional `GET /api/v1/credits` only if a management key exists (`OPENROUTER_MANAGEMENT_KEY`). No LLM on the 10–15m tick. |
| 7 | Cross-bot session_search | **Yes** for Helm, Chart, Vigil summary, Ledger correlation. Ops bots: own domain only. |
| 8 | Gateway | Helm-only inbound. |

---

## What Phase B must not invent

- Full `pip install aipass` / `.trinity/` / `.ai_mail.local/`
- Free `:free` pins on Inbox / Chronos / Tasker
- Vigil as coding-only Sentry
- Chronos owning Todoist while Tasker exists
- Librarian doing intake
- Mail send tools
- Trust Level > 0 without Michael

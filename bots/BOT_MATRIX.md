# Bot matrix — tools × models (Carrier Hermes)

Canonical **bot** view. Mirror: `profiles/PROFILE_MATRIX.md` (same table; CLI homes use these ids).

Board: **`carrier`**. Channel priority: Kanban → cron → AIPass → bot-chat → `delegate_task` denied.

MCP filters are **include/exclude on that bot home**. Default desktop home may keep everything; specialists must not.

---

## Command

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `chief_of_staff` | Helm | `smart` Grok 4.5; fallback `quality` | kanban, cronjob, discord/gateway as configured, memory, session_search, todo, clarify, skills (roster) | terminal, file, web, browser, code_execution, computer_use, delegation (keep off unless scratch explicitly enabled) | **none** domain. No todoist, no OSB, no mail. |
| `subscription_watcher` | Vigil | heartbeat none; summary `watcher-summary` | (cron script only). Summary job: session_search, file (narrow), discord | web, browser, terminal (except script), delegation, todoist, OSB | none |
| `api_watcher` | Ledger | heartbeat none; narrative specialist | script/terminal **narrow** (curl OpenRouter + lock scripts), file `_agent/api_watcher/`, discord, session_search | web browse, browser, delegation, domain MCP | none |

## Coding / meta

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `firstmate` | Mate | `quality` implementer; `specialist` janitor/docs | terminal, file, code_execution, skills (claude-code, codex, opencode), delegation, session_search, memory, web (opt), kanban worker | mail, todoist, calendar, OSB write | vercel/github as needed for coding; **no** todoist/OSB write |
| `hermes_ai_explorer` | Scout | `quality` | web, session_search, memory, file, skills, OSB **read** | terminal destructive, delegation as CoS, todoist, mail | OSB read-only filter; no todoist |

## Ops

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `email_reader` | Inbox | `specialist` **paid DeepSeek only** | file (email root), mail-read when wired | web/browser preferred off, discord, todoist, calendar, terminal, send | mail read only if added; **never** send |
| `email_drafter` | Quill | `quality` | file, memory, skills, discord | terminal, send, todoist, calendar, browser | OSB **read** People/ only if needed |
| `calendar_manager` | Chronos | `specialist` paid DeepSeek | file (`_agent/calendar/`), calendar read | todoist (Tasker exists), mail, vault write, terminal | calendar MCP when wired; **todoist excluded** |
| `todoist_manager` | Tasker | `specialist` paid DeepSeek | file (`_agent/todoist/`) | calendar mutate, mail, vault, terminal | **todoist** MCP (no template import/export) |

## Knowledge / research

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `vault_librarian` | Librarian | `quality` | file `_agent/librarian/`, skills, OSB read/health | Inbox writers, todoist, mail, terminal | OSB: allow search/read/health/backlinks/validate; **exclude** save/capture/update |
| `obsidian_archivist` | Clerk | `quality` | file `_agent/archivist/` (+ vault when grant), skills, OSB read | todoist, mail, calendar, terminal | OSB read always; **write tools only** when intake enabled |
| `research_agent` | Probe | `quality` | web, browser (read-only), file `_agent/research/`, memory | mail, todoist, calendar, OSB write, discord spam | none required |

---

## Shared denials (every bot)

- No mail **send** tools.
- No `pip install aipass`.
- Kanban workers additionally receive `kanban_*` from the dispatcher (not a reason to give Helm domain tools).
- `computer_use` off for specialists unless Michael asks.

---

## Model alias map

See `COST_MODEL.md`. Specialist/rote/cheap = `openrouter/deepseek/deepseek-chat-v3-0324` with **no** `:free`.

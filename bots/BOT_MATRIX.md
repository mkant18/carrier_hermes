# Bot matrix — tools × models (Carrier Hermes)

Canonical **bot** view. Mirror: `profiles/PROFILE_MATRIX.md` (same table; CLI homes use these ids).

Board: **`carrier`**. Channel priority: Kanban → cron → AIPass → bot-chat → `delegate_task` denied.

MCP filters are **include/exclude on that bot home**. Default desktop home may keep everything; specialists must not.

---

## Command

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `marshal` | Marshal 🎖️ | `quality` Sonnet Max; fallback Grok 4.5 | kanban (owner — all lanes), todo, session_search, memory, file `_agent/marshal/**`, aipass, discord `#command`+`#fleet` via First Watch, clarify | terminal, code_execution, browser, web, computer_use, mail, mail_send, todoist MCP, calendar, OSB write, delegation | **none** |
| `chief_of_staff` | Helm ⚓️ | `smart` Grok 4.5; fallback `quality` | kanban, cronjob, discord/gateway as configured, memory, session_search, todo, clarify, skills (roster) | terminal, file, web, browser, code_execution, computer_use, delegation (keep off unless scratch explicitly enabled); **no Doppler / no secrets** | **none** domain. No todoist, no OSB, no mail, no Doppler. |
| `subscription_watcher` | Vigil 📡 | heartbeat none; summary `watcher-summary` | (cron script only). Summary job: session_search, file (narrow), discord | web, browser, terminal (except script), delegation, todoist, OSB | none |
| `api_watcher` | Ledger 📒 | heartbeat none; narrative specialist | script/terminal **narrow** (curl OpenRouter + lock scripts), file `_agent/api_watcher/`, discord, session_search | web browse, browser, delegation, domain MCP | none |
| `lockbox` | LockBox 🗝️ | `lockbox` / `security-cheap` (Gemini 2.5 Flash); fallback GPT-4o-mini only; rare `quality` | file `_agent/lockbox/**` + `~/.hermes/carrier/lockbox/**`; terminal **narrow** (doppler CLI / curl Doppler API / `lockbox_verify_grant.py`); memory (non-secret ops); session_search (audit); discord `#alerts` only (redacted); skills (own security scripts) | web browse, browser, computer_use, delegation, mail, todoist, calendar, OSB write, kanban-as-CoS, code_execution broad, any send | **Doppler CLI/REST only**; no todoist/OSB/mail MCP |

## Lieutenants (Wing Leads)

Lts are **routing nodes**: dispatch, review, sequence, escalate. They run advanced models
(Sonnet Max, $0 marginal on Claude Max) because coordination needs judgment — but they are
deliberately barred from execution tools so they cannot do their squadron's work. This is
the opposite of Helm: Helm is SUPER-USER, Lts are narrow. Sub-specialists stay cost-isolated
on cheap paid DeepSeek V3 / `no_agent` so the Lt only burns tokens to coordinate.

Command tier (Vigil, Ledger, LockBox) is **co-equal beside Helm** — never under a Lt.

| bot_id | Callsign | Wing | Squadron | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|---|---|
| `coding_lt` | Wrench 🔧 | Coding | Mate (+ coding workers) | `quality` Sonnet Max | kanban (dispatch), AIPass, session_search, memory (coding meta), file `_agent/coding_lt/**`, discord `#fleet` | terminal, code_execution, browser, computer_use, delegation, web, broad file, mail, todoist, calendar, OSB write | **none** |
| `ops_lt` | Deck 🛫 | Ops | Inbox, Quill, Chronos, Tasker, Purse | `quality` Sonnet Max | kanban (dispatch), AIPass, session_search, memory (ops meta), file `_agent/ops_lt/**`, discord `#fleet` + `#drafts` read | terminal, code_execution, browser, computer_use, delegation, web, mail (read or send), todoist MCP, calendar mutate, OSB write, Monarch | **none** |
| `knowledge_lt` | Stacks 📚 | Knowledge | Librarian, Clerk | `quality` Sonnet Max | kanban (dispatch), AIPass, session_search, memory, file `_agent/knowledge_lt/**`, OSB **read-only** (health/validate/backlinks), discord `#fleet` | terminal, code_execution, browser, computer_use, delegation, web, mail, todoist, calendar, **all OSB write tools** | OSB read-only: `exclude` save/capture/update |
| `hermes_ai_explorer` | Chart 🗺️ | Recon | Sonar, Probe | `quality` Sonnet Max | (embedded Wing Lead — see Recon Wing row below) | — | OSB read-only |

**Lt hard rule:** a Lt that writes code, reads mail, mutates a calendar, files a vault note,
or queries Monarch has violated its SOUL. Route it to the specialist instead.

## Coding / meta

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `firstmate` | Mate ⚙️ | `quality` implementer; `specialist` janitor/docs | terminal, file, code_execution, skills (claude-code, codex, opencode), delegation, session_search, memory, web (opt), kanban worker | mail, todoist, calendar, OSB write | vercel/github as needed for coding; **no** todoist/OSB write |

## Recon Wing

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `hermes_ai_explorer` | Chart 🗺️ | `quality` Sonnet Max | web (selective — prefer Sonar digest), session_search, memory, file (`_agent/explorer/`), skills, OSB **read**, discord `#fleet` (≤5 bullets) | terminal destructive, delegation as Helm, todoist, mail | OSB read-only filter; no todoist |
| `passive_watch` | Sonar 🌊 | heartbeat `no_agent`; LLM pass `specialist` DeepSeek | terminal **narrow** (curl/hash fixed URLs, state r/w), file (`_agent/signal_watch/`), discord `#fleet` (≤3 signals, HIGH only) | browser interactive, computer_use, delegation, mail, todoist, calendar, OSB write, web browse, kanban-as-Helm | none |
| `research_agent` | Probe 🔭 | `quality` Sonnet Max | web, browser (read-only), file `_agent/research/`, memory | mail, todoist, calendar, OSB write, discord spam, terminal | none required |

## Ops

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `email_reader` | Inbox 📬 | `specialist` **paid DeepSeek only** | file (email root), mail-read when wired | web/browser preferred off, discord, todoist, calendar, terminal, send | mail read only if added; **never** send |
| `email_drafter` | Quill 🪶 | `quality` | file, memory, skills, discord | terminal, send, todoist, calendar, browser | OSB **read** People/ only if needed |
| `calendar_manager` | Chronos 🕰️ | `specialist` paid DeepSeek | file (`_agent/calendar/`), calendar **read+write** (live 2026-08-25) | todoist (Tasker exists), mail, vault write, terminal | calendar MCP when wired; **todoist excluded** |
| `todoist_manager` | Tasker ✅ | `specialist` paid DeepSeek | file (`_agent/todoist/`), Todoist **live** mutate (2026-08-25) | calendar mutate, mail, vault, terminal | **todoist** MCP (no template import/export) |
| `finance_reader` | Purse | `quality` Sonnet 4.6 | narrow terminal (Monarch queries), file `_agent/finance/**`, memory, session_search | broad terminal, browser, computer_use, delegation, mail, todoist, calendar, OSB write, Monarch write paths | Monarch read-only tools; no todoist/OSB write |

## Knowledge

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `vault_librarian` | Librarian 📖 | `quality` | file `_agent/librarian/`, skills, OSB read/health | Inbox writers, todoist, mail, terminal | OSB: allow search/read/health/backlinks/validate; **exclude** save/capture/update |
| `obsidian_archivist` | Clerk 🗄️ | `quality` | file `_agent/archivist/` + `Inbox/` when grant, skills, OSB read+write on **this home** | todoist, mail, calendar, terminal | OSB writers on Clerk home only; use with `trust_override: intake_enabled`; vault **TL2** |

---

## Shared denials (every bot)

- No mail **send** tools.
- No `pip install aipass`.
- Kanban workers additionally receive `kanban_*` from the dispatcher (not a reason to give Helm domain tools).
- `computer_use` off for specialists unless Michael asks.

---

## Model alias map

See `COST_MODEL.md`. Specialist/rote/cheap = `openrouter/deepseek/deepseek-v4-flash-0731` with **no** `:free`.

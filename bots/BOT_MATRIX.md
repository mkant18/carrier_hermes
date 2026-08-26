# Bot matrix — tools × models (Carrier Hermes)

Canonical **bot** view. Mirror: `profiles/PROFILE_MATRIX.md` (same table; CLI homes use these ids).

Board: **`carrier`**. Channel priority: Kanban → cron → AIPass → bot-chat → `delegate_task` denied.

MCP filters are **include/exclude on that bot home**. Default desktop home may keep everything; specialists must not.

---

## Command

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `marshal` | Marshal 🎖️ | `quality` Sonnet Max; fallback Grok 4.5 | kanban (owner — all lanes), todo, session_search, memory, file `_agent/marshal/**`, aipass, discord **`#fleet`** via First Watch (**never `#command`**), clarify | terminal, code_execution, browser, web, computer_use, mail, mail_send, todoist MCP, calendar, OSB write, delegation | **none** |
| `chief_of_staff` | Helm ⚓️ | `smart` Grok 4.5; fallback `quality` | kanban, cronjob, discord/gateway as configured, memory, session_search, todo, clarify, skills (roster) | terminal, file, web, browser, code_execution, computer_use, delegation (keep off unless scratch explicitly enabled); **no Doppler / no secrets** | **none** domain. No todoist, no OSB, no mail, no Doppler. |
| `subscription_watcher` | Vigil 📡 | heartbeat none; summary `watcher-summary` | (cron script only). Summary job: session_search, file (narrow), discord | web, browser, terminal (except script), delegation, todoist, OSB | none |
| `api_watcher` | Ledger 📒 | heartbeat `no_agent`; narrative specialist DeepSeek V3; interactive Grok 4.5 | terminal **narrow** (`ledger_probe.py`, `ledger_live_tail.py`, `api_watcher_heartbeat.sh`, `spend_halt.sh`); file `_agent/api_watcher/` (write) + `~/.hermes/profiles/*/state.db` (read-only SQLite) + `~/.hermes/profiles/*/logs/agent.log` (read); discord `#alerts`+`#fleet`; session_search | web browse (curl OR API directly), browser, delegation, domain MCP, mail, todoist, calendar, vault write | none |
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
| `git_yeoman` | Yeoman 📋 | `specialist` paid DeepSeek V3 | terminal **narrow** (`gh` CLI only), file `_agent/git_yeoman/**`, session_search, memory, aipass, discord `#fleet` via First Watch, todo, skills (github-issues, github-pr-workflow, github-code-review read-only) | code_execution, browser, web, computer_use, mail, mail_send, todoist, calendar, OSB write, delegation, cronjob | **none** (gh CLI handles GitHub API) |

## Shipwright Wing (Autonomous Maintenance)

Fully autonomous maintenance pipeline. Runs on a schedule. No user input required per-run.
All bots report to Marshal via Kanban. Bosun is the ONLY dispatcher for this wing.

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `maintenance_lt` | Bosun 🛠️ | `claude-sonnet-4-6` anthropic → `grok-4.5` xai-oauth | kanban (dispatch/review), AIPass, session_search, memory, file `_agent/maintenance_lt/**`, discord `#maintenance` + `#fleet` via Shipwright REST | terminal, code_execution, browser, computer_use, delegation, web, mail, todoist, calendar, OSB write | none |
| `code_auditor` | Diver 🤿 | local `qwen2.5:7b-instruct-q4_K_M` → `claude-sonnet-4-6` anthropic → `grok-4.5` xai-oauth | terminal **narrow** (rg, ruff, pylint, git log/diff/status, tail, cat — READ-ONLY, NO git write), file `_agent/maintenance/**` (write) + repo (read-only), session_search, AIPass | mail, todoist, calendar, OSB write, delegation, kanban-as-owner, browser, computer_use | none |
| `repair_planner` | Rigger 🪢 | `claude-opus-4-5` anthropic → `claude-sonnet-4-6` anthropic → `grok-4.5` xai-oauth → `google/gemini-2.5-flash-lite` OR (last resort) | file `_agent/maintenance/**` (read+write), session_search, memory, skills, AIPass | terminal, code_execution, browser, computer_use, delegation, web, mail, todoist, calendar, kanban | none |
| `patch_writer` | Caulker ⚒️ | local `qwen2.5:7b-instruct-q4_K_M` → `claude-haiku-4-5` anthropic → `claude-sonnet-4-6` anthropic → `grok-4.5` xai-oauth | terminal **narrow** (git branch/add/commit/push, ruff, pytest), file (repo write + `_agent/maintenance/**`), code_execution, skills, AIPass (to Yeoman + Bosun), session_search | mail, todoist, calendar, OSB write, browser, computer_use, kanban-as-owner | none |
| `pr_reviewer` | Surveyor 🧭 | `claude-opus-4-5` anthropic → `claude-sonnet-4-6` anthropic → `grok-4.5` xai-oauth → `google/gemini-2.5-flash-lite` OR (last resort) | terminal **narrow** (gh pr view/diff/checks, billing_guard read-only, git log/diff), file `_agent/maintenance/**`, skills, AIPass (to Caulker + Bosun + Yeoman), session_search | code_execution, mail, todoist, calendar, OSB write, delegation, computer_use, kanban-as-owner | none |

### Hard rules — Shipwright Wing

1. **Diver is READ-ONLY on the repo** — no `git write`, no file mutations outside `_agent/maintenance/`
2. **Caulker does NOT open PRs directly** — always goes through Yeoman (same protocol as Mate)
3. **Surveyor does NOT merge directly** — instructs Yeoman to merge (Yeoman is the only bot with `gh pr merge` authority)
4. **Bosun never executes code** — same Lt hard rule as all other LTs
5. **All 5 bots must pass billing_guard** before any dispatch

## Recon Wing

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `hermes_ai_explorer` | Chart 🗺️ | `quality` Sonnet Max | web (selective — prefer Sonar digest), session_search, memory, file (`_agent/explorer/`), skills, OSB **read**, discord `#fleet` (≤5 bullets) | terminal destructive, delegation as Helm, todoist, mail | OSB read-only filter; no todoist |
| `passive_watch` | Sonar 🌊 | heartbeat `no_agent`; LLM pass `specialist` DeepSeek | terminal **narrow** (curl/hash fixed URLs, state r/w), file (`_agent/signal_watch/`), discord `#fleet` (≤3 signals, HIGH only) | browser interactive, computer_use, delegation, mail, todoist, calendar, OSB write, web browse, kanban-as-Helm | none |
| `research_agent` | Probe 🔭 | `quality` Sonnet Max | web, browser (read-only), file `_agent/research/`, memory | mail, todoist, calendar, OSB write, discord spam, terminal | none required |

## Ops

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `email_reader` | Inbox 📬 | `specialist` **paid DeepSeek only** | file (`_agent/email/`), skills, terminal **narrow** (`gapi_fleet.py inbox` / Gmail read) | web/browser preferred off, discord spam, todoist, calendar, send | **google-workspace** skill; Gmail **read only**; **never** send |
| `email_drafter` | Quill 🪶 | `quality` | file, memory, skills, discord | terminal, send, todoist, calendar, browser | OSB **read** People/ only if needed |
| `calendar_manager` | Chronos 🕰️ | `specialist` paid DeepSeek | file (`_agent/calendar/`), skills, terminal **narrow** (`gapi_fleet.py chronos`), calendar **read+write** (live) | todoist (Tasker exists), mail, vault write, send | **google-workspace** skill; calendar only; **todoist excluded** |
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

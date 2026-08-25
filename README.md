# carrier_hermes

> Hermes **Bot Mode** fleet: Carrier Ops chief-of-staff as a roster of named **bots**.

Canonical bot definitions: [`bots/`](bots/README.md).  
Runtime: each bot installs to a Hermes bot home (`hermes profile create <bot_id>` is only the CLI verb — product language is **bot**).

## Roster (18 bots)

Command tier (4) + Recon Wing (3) + Ops Wing (6) + Coding Wing (2) + Knowledge Wing (3).
Wing Leads are **Lieutenants**: they dispatch, review, and route between Helm and their
squadron on advanced models, and never do the domain work themselves. Command tier sits
co-equal *beside* Helm — never under a Lt.

| Callsign | bot_id | Tier / Wing |
|---|---|---|
| **Helm** ⚓️ | chief_of_staff | Command — front door, classify/dispatch, SUPER-USER |
| **Vigil** 📡 | subscription_watcher | Command — stalls + subscription quota; `DISPATCH_LOCK` |
| **Ledger** 💵 | api_watcher | Command — OpenRouter $ spend; `SPEND_HALT` |
| **LockBox** 🔒 | lockbox | Command — Doppler secrets + HMAC grant redemption |
| **Chart** 🗺️ | hermes_ai_explorer | Recon Wing **Lead** — intelligence synthesis |
| **Sonar** 📡 | passive_watch | Recon — passive ecosystem signals (`no_agent` daily) |
| **Probe** 🔍 | research_agent | Recon — on-demand deep research |
| **Deck** 🗂️ | ops_lt | Ops Wing **Lt** — pipeline routing & coordination |
| **Inbox** 📥 | email_reader | Ops — email triage (paid DeepSeek, no sends) |
| **Quill** ✍️ | email_drafter | Ops — drafts to `#drafts`, never sends |
| **Chronos** ⏱️ | calendar_manager | Ops — calendar read/write; hands tasks to Tasker |
| **Tasker** 📋 | todoist_manager | Ops — Todoist mutations |
| **Purse** 👛 | finance_reader | Ops — read-only Monarch queries |
| **Wrench** 🔧 | coding_lt | Coding Wing **Lt** — PR review & worktree orchestration |
| **Mate** ⚓️ | firstmate | Coding — implementation & coding crew lead |
| **Stacks** 📚 | knowledge_lt | Knowledge Wing **Lt** — intake gate & vault routing |
| **Librarian** 🏛️ | vault_librarian | Knowledge — vault queries out |
| **Clerk** 📑 | obsidian_archivist | Knowledge — vault intake in, keep/discard filing |

## Docs

- [`docs/INTER_AGENT_PROTOCOL.md`](docs/INTER_AGENT_PROTOCOL.md) — **frozen** how bots talk + AIPass
- [`docs/HERMES_CAPABILITY_NOTES.md`](docs/HERMES_CAPABILITY_NOTES.md) — Bot Mode / Kanban / cron / channel priority
- [`bots/BOT_MATRIX.md`](bots/BOT_MATRIX.md) — tools × models
- [`GOVERNANCE.md`](GOVERNANCE.md) · [`COST_MODEL.md`](COST_MODEL.md)
- [`integrations/aipass-mailbox.md`](integrations/aipass-mailbox.md) — hybrid file mail (not pip AIPass)
- [`prompts/IMPLEMENT_PROMPT.md`](prompts/IMPLEMENT_PROMPT.md) — Phase A freeze → Phase B build **bots**

## Quickstart

Paste `prompts/IMPLEMENT_PROMPT.md` into a fresh Hermes session.  
**Phase A** freezes inter-bot protocol. **Phase B** creates the **bot roster** (not “a pile of anonymous profiles”).

**Windows PC as primary host** (more RAM/GPU/storage): paste  
[`prompts/WINDOWS_PRIMARY_HOST_SETUP.md`](prompts/WINDOWS_PRIMARY_HOST_SETUP.md)  
into a fresh session **on the PC**. Prefer running that install chat on cheap OpenRouter  
`deepseek/deepseek-v4-flash-0731` (fallback `google/gemini-2.5-flash-lite`).  
It pulls Doppler secrets, wires the fleet, and enforces **no Anthropic/Grok API tokens**  
(`scripts/billing_guard.py` — OAuth/subscription only for Claude + Grok).

Post-fleet todos (two fresh sessions):

- [`prompts/SESSION_OPENROUTER_AND_DISCORD.md`](prompts/SESSION_OPENROUTER_AND_DISCORD.md) — OpenRouter key + Discord IDs  
- [`prompts/SESSION_SHADOW_AND_TRUST.md`](prompts/SESSION_SHADOW_AND_TRUST.md) — shadow exit + Trust Level walkthrough

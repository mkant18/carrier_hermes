# carrier_hermes

> Hermes **Bot Mode** fleet: Carrier Ops chief-of-staff as a roster of named **bots**.

Canonical bot definitions: [`bots/`](bots/README.md).  
Runtime: each bot installs to a Hermes bot home (`hermes profile create <bot_id>` is only the CLI verb — product language is **bot**).

## Roster (12 bots)

| Callsign | bot_id | Tier |
|---|---|---|
| **Helm** | chief_of_staff | Command — front door |
| **Vigil** | subscription_watcher | Command — beside Helm — all-session health/quota |
| **Ledger** | api_watcher | Command — beside Helm — all-session $ / OpenRouter |
| **Mate** | firstmate | Coding |
| **Scout** | hermes_ai_explorer | Meta advisor |
| **Inbox** | email_reader | Ops |
| **Quill** | email_drafter | Ops |
| **Chronos** | calendar_manager | Ops calendar |
| **Tasker** | todoist_manager | Ops Todoist |
| **Librarian** | vault_librarian | Knowledge query |
| **Clerk** | obsidian_archivist | Knowledge intake |
| **Probe** | research_agent | Research |

## Docs

- [`docs/INTER_AGENT_PROTOCOL.md`](docs/INTER_AGENT_PROTOCOL.md) — how bots talk
- [`bots/README.md`](bots/README.md) — bot table
- [`integrations/obsidian-second-brain.md`](integrations/obsidian-second-brain.md)
- [`prompts/IMPLEMENT_PROMPT.md`](prompts/IMPLEMENT_PROMPT.md) — Phase A protocol freeze → Phase B build **bots**
- [`.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md`](.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md)

## Quickstart

Paste `prompts/IMPLEMENT_PROMPT.md` into a fresh Hermes session.  
**Phase A** freezes inter-bot protocol. **Phase B** creates the **bot roster** (not “a pile of anonymous profiles”).

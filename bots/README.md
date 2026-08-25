# Fleet bots (canonical)

In Carrier Hermes, every agent is a **Bot** — a named roster member with its own identity, model, memory, tools, and routines.

**Hermes runtime note:** Bot Mode implements each bot as an isolated Hermes home (`~/.hermes/profiles/<bot_id>/`). That is a storage/runtime detail. In this repo and in CoS language we always say **bot**, never “profile,” except when running the exact CLI (`hermes profile create` = *create bot home*).

| bot_id | Callsign | Tier | One-line job |
|---|---|---|---|
| `chief_of_staff` | **Helm** | Command | Front door; classify; dispatch job packets |
| `subscription_watcher` | **Vigil** | Command (beside Helm) | Fleet-wide stalls + subscription quota; DISPATCH_LOCK |
| `api_watcher` | **Ledger** | Command (beside Helm) | Fleet-wide $ spend (OpenRouter etc.); SPEND_HALT |
| `lockbox` | **LockBox** | Command / security (beside Helm) | Doppler secrets + permission grants; CoS handshake only |
| `firstmate` | **Mate** | Coding | Default coding crew |
| `hermes_ai_explorer` | **Chart** | Recon Wing lead | Intelligence synthesis + fleet optimization proposals |
| `passive_watch` | **Sonar** | Recon Wing | Passive ecosystem signals — daily cheap watch; feeds Chart |
| `email_reader` | **Inbox** | Ops | Email triage (no send) |
| `email_drafter` | **Quill** | Ops | Drafts only → Discord |
| `calendar_manager` | **Chronos** | Ops | Calendar read; hand task specs to Tasker |
| `todoist_manager` | **Tasker** | Ops | All Todoist mutations |
| `vault_librarian` | **Librarian** | Knowledge (out) | Query / health / answers from vault |
| `obsidian_archivist` | **Clerk** | Knowledge (in) | Intake: triage artifacts → file into OSB with CoS |
| `research_agent` | **Probe** | Recon Wing | On-demand web research for Michael's questions |

**Recon Wing:** Chart (synthesis lead) + Sonar (cheap passive signals) + Probe (on-demand research). Chart coordinates; Sonar feeds daily ecosystem signals at near-zero cost; Probe runs quality research on request.

**14 bots.** Watchers + **LockBox** sit next to Helm, not under Mate: Vigil/Ledger monitor **all** sessions/spend; LockBox stewards secrets only via Helm handshake.

Install path: copy each `bots/<bot_id>/SOUL.md` → bot home SOUL; set description/callsign for Bot Mode roster.

**Protocol (frozen):** [`docs/INTER_AGENT_PROTOCOL.md`](../docs/INTER_AGENT_PROTOCOL.md) · tools × models: [`BOT_MATRIX.md`](BOT_MATRIX.md) · AIPass: [`../integrations/aipass-mailbox.md`](../integrations/aipass-mailbox.md)

# Discord channels (IDs filled by Michael)

Names are frozen. **Do not invent snowflake IDs.**

## Command home (default contact)

**Default human ↔ fleet surface:** one channel for **Michael + CoS (Helm) + Ledger (API watcher) + Vigil (subscription watcher)** — collectively **Command**.

| Role | Channel name | ID |
|---|---|---|
| **Command home** (Michael + CoS + Ledger + Vigil) | `#command` | `1541866378255011980` |
| Drafts (Quill) | `#drafts` | `1541866401432871002` |
| Alerts (Vigil + Ledger hard/soft caps, breaches) | `#alerts` | `1541866423427801148` |
| Fleet ops & handoffs (Dispatch/receipt confirmations, Scout tips) | `#fleet` | `1541866443765977138` |

### Routing rules (frozen intent)

1. **You talk in `#command` by default.** CoS (Helm) owns replies and dispatch from there.
2. **CoS must narrate handoffs in `#command`:** when delegating to another bot, say so in `#command` (who + what). When a result packet returns, summarize it back in `#command`.
3. **`#fleet` is the Fleet Dispatch & Receipt Board:**
   - Whenever Helm, FirstMate, or any bot dispatches a job or handoff (via Kanban, AIPass, or cron), a short confirmation line is posted to `#fleet` (e.g., `🛫 DISPATCH | Helm → Mate | [JOB-ID] Implementing auth refactor`).
   - Whenever the receiving bot picks up or completes the handoff/operation, it posts an ack/receipt line to `#fleet` (e.g., `⚓ ACK | Mate | [JOB-ID] On station — working task` / `🛬 TRAP | Mate | [JOB-ID] Complete — PR #14 opened`).
   - Specialists without their own gateway use `hermes send --to discord:fleet` via the shared First Watch voice.
4. **Ledger + Vigil** may post brief status/watch notes in `#command`; hard spend/breach alerts still go to `#alerts` (and optional webhook).
4. **Specialists** (Inbox, Chronos, Tasker, Quill drafts, Scout tips) do **not** become general user-facing Discord bots. CoS dispatches; results funnel back via CoS to `#command` unless a role channel applies (`#drafts`, `#fleet`).
5. Existing ops lanes stay available: `#email`, `#calendar`, `#tasks`, `#vault`, `#finance`, `#audit`, `#urgent`, `#general` — not the default human home.

### Already on server (gateway / API)

| name | id |
|---|---|
| `general` | `1541154516811120762` |
| `email` | `1541155152726204416` |
| `calendar` | `1541155189019517078` |
| `tasks` | `1541155241746239658` |
| `vault` | `1541155274528915577` |
| `finance` | `1541155307860795503` |
| `audit` | `1541155342833025114` |
| `urgent` | `1541155373371621507` |

Guild: Carrier Ops (`1541154515841974294`). Text category parent: `1541154516811120760`.

Webhook for `#alerts` (optional, scripts): set `CARRIER_ALERTS_WEBHOOK` in `~/.hermes/.env` — never commit.

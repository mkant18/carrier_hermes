# Discord channels (IDs filled by Michael)

Names are frozen. **Do not invent snowflake IDs.**

## Command home (default contact)

**Default human ↔ fleet surface:** one channel for **Michael + CoS (Helm) + Ledger (API watcher) + Vigil (subscription watcher)** — collectively **Command**.

| Role | Channel name | ID |
|---|---|---|
| **Command home** (Michael + CoS + Ledger + Vigil) | `#command` | `1541866378255011980` |
| Drafts (Quill) | `#drafts` | `1541866401432871002` |
| Alerts (Vigil + Ledger hard/soft caps, breaches) | `#alerts` | `1541866423427801148` |
| Fleet ops & handoffs (Dispatch/receipt confirmations, Chart/Sonar tips) | `#fleet` | `1541866443765977138` |

### Routing rules (frozen intent)

1. **You talk in `#command` by default.** CoS (Helm) owns replies and dispatch from there.
2. **CoS must narrate handoffs in `#command`:** when delegating to another bot, say so in `#command` (who + what). When a result packet returns, summarize it back in `#command`.
3. **`#fleet` is the Fleet Dispatch & Receipt Board:**
   - Whenever Helm, FirstMate, or any bot dispatches a job or handoff (via Kanban, AIPass, or cron), a short confirmation line is posted to `#fleet` (e.g., `🛫 DISPATCH | Helm → Mate | [JOB-ID] Implementing auth refactor`).
   - Whenever the receiving bot picks up or completes the handoff/operation, it posts an ack/receipt line to `#fleet` (e.g., `⚓ ACK | Mate | [JOB-ID] On station — working task` / `🛬 TRAP | Mate | [JOB-ID] Complete — PR #14 opened`).
   - Specialists without their own gateway use `hermes send --to discord:fleet` via the shared First Watch voice.
4. **Ledger + Vigil** may post brief status/watch notes in `#command`; hard spend/breach alerts still go to `#alerts` (and optional webhook).
4. **Specialists** (Inbox, Chronos, Tasker, Quill drafts, Chart/Sonar tips) do **not** become general user-facing Discord bots. CoS dispatches; results funnel back via CoS to `#command` unless a role channel applies (`#drafts`, `#fleet`).
5. Existing ops lanes stay available: `#email`, `#calendar`, `#tasks`, `#vault`, `#finance`, `#audit`, `#urgent`, `#general` — not the default human home.

### Verified live (2026-08-25, via Discord REST API)

Guild **Carrier Ops** `1541154515841974294`, text category `1541154516811120760`.
All four core channels confirmed present with the IDs above. Single-gateway rule verified:

| Token env var | Discord app | Identity confirmed | Role | Gateway |
|---|---|---|---|---|
| `DISCORD_BOT_TOKEN` on `~/.hermes/profiles/chief_of_staff/.env` | **Carrier Ops** `1541150313405480970` | `Carrier Ops` | Helm inbound, owns `#command` (home channel set to `1541866378255011980`) | **YES — the only poller** |
| `DISCORD_FLEET_BOT_TOKEN` on `~/.hermes/.env` | **First Watch** `1541881948660568116` | `FirstWatch` | Shared outbound for all non-Helm bots → `#fleet`, `#alerts`, `#drafts` | **NO — REST send only** |

The two tokens are confirmed **distinct**, and the Carrier Ops token is **not** present on
the default home — so no double-poll. First Watch REST send smoke-tested green against all
four channels (`GET` 200) and a live `POST` to `#fleet` returned `200`.

> Note: the env var names in use are `DISCORD_BOT_TOKEN` / `DISCORD_FLEET_BOT_TOKEN`, not the
> `CARRIER_OPS_DISCORD_TOKEN` / `FIRST_WATCH_DISCORD_TOKEN` names in the identity matrix's
> Doppler inventory table. The Doppler names are the storage keys; these are the runtime vars.

### Wing lanes (Lt layer)

Lieutenants post dispatch/ack/trap lines to `#fleet` via First Watch — they do **not** get
their own gateway or become user-facing:

| Lt | Mark | Posts to |
|---|---|---|
| Wrench (`coding_lt`) | 🔧 | `#fleet` (+ `#ready-room` when created) |
| Deck (`ops_lt`) | 🗂️ | `#fleet`, reads `#drafts` for approval surfacing |
| Stacks (`knowledge_lt`) | 📚 | `#fleet` |

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

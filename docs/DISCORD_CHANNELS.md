# Discord channels (IDs filled by Michael)

Names are frozen. **Do not invent snowflake IDs.**

## Command home (default contact)

**Default human ↔ fleet surface:** one channel for **Michael + CoS (Helm) + Ledger (API watcher) + Vigil (subscription watcher)** — collectively **Command**.

| Role | Channel name | ID |
|---|---|---|
| **Command home** (Michael + CoS + Ledger + Vigil) | `#command` | `1541866378255011980` |
| Drafts (Quill) | `#drafts` | `1541866401432871002` |
| Alerts (Vigil + Ledger hard/soft caps, breaches) | `#alerts` | `1541866423427801148` |
| Fleet tips (Scout, ≤5 bullets) | `#fleet` | `1541866443765977138` |

### Routing rules (frozen intent)

1. **You talk in `#command` by default.** CoS owns replies and dispatch from there.
2. **CoS must narrate handoffs for now:** when delegating to another bot, say so in `#command` (who + what). When a result packet returns, summarize it back in `#command` before (or instead of) burying it elsewhere.
3. **Ledger + Vigil** may post brief status/watch notes in `#command`; hard spend/breach alerts still go to `#alerts` (and optional webhook).
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

## Live wiring (this machine)

| Piece | Value |
|---|---|
| Discord gateway profile | **`chief_of_staff` (Helm)** — `ai.hermes.gateway-chief_of_staff` |
| Discord bot identity | Carrier Ops (single bot token) |
| #command | Free-response, no auto-thread, **shared room session** (`group_sessions_per_user: false` on Helm) |
| Inbound | Michael → Helm only (one token = one receiver) |
| Command-tier peers in-channel | Vigil / Ledger / LockBox post via **send/cron/webhook with callsign prefix** (or extra Discord bots later) |
| #fleet | Rest-of-fleet tips/check-ins (Scout etc.) — not Command strategy |
| Default profile Discord | **Disabled** (avoids token double-poll) |

### Kanban visibility (fleet PM)

Fleet/bot project management is **Hermes Kanban** (board `carrier`) — **not Todoist** and not a separate PM SaaS.

There is **no #kanban Discord channel**. If Michael creates one later, paste its snowflake here and subscribe cards with:
`hermes kanban notify-subscribe --platform discord --chat-id <snowflake> --chat-type channel --notifier-profile chief_of_staff --delivery-mode notify <task_id>`

| Surface | How to access |
|---|---|
| **Human board UI** | Hermes Dashboard → Kanban tab: **http://127.0.0.1:9119** (loopback only). Start with `hermes dashboard --no-open --host 127.0.0.1`. Navigate to the Kanban tab in the left sidebar. |
| **Event mirror** | Open cards subscribe to **#command** (`1541866378255011980`) via `notify-subscribe`. Terminal state changes (claimed, done, blocked, review) post a brief message in #command via the `chief_of_staff` gateway. |
| **#tasks** (`1541155241746239658`) | Legacy ops lane — **not** the Hermes Kanban board. Not subscribed; not widened in Helm allowed_channels. |
| **CLI** | `hermes kanban list` · `hermes kanban notify-list` · `hermes kanban show <id>` |

### Sharing Discord bots across Hermes bots

Hermes rule: **one Discord bot token → at most one gateway profile**. You cannot have Helm + Vigil both poll the same token.

**Practical share models:**

1. **Recommended default (now):** 1 Discord bot → Helm gateway. Other Command bots **speak** via attributed sends into #command; **work** via Kanban/AIPass/cron.
2. **2–3 Discord bots (optional later):** e.g. Helm + Vigil + Ledger each get a token and their own gateway — true multi-@mention voices. Do **not** set bot-to-bot mention allow (ack-loop). LockBox can stay send-only.
3. **Webhooks:** same channel, distinct display names, no inbound brain — good for ready/status lines.

## Discord bots (dual identity)

| Discord app | App ID | Hermes owner | Role |
|---|---|---|---|
| **Carrier Ops** | `1541150313405480970` | **`chief_of_staff` (Helm) only** | #command inbound + Command replies |
| **First Watch** | `1541881948660568116` | Shared by non-Helm bots (default + specialists) | #fleet / #alerts / specialist outbound; may post callsign lines into #command |

**Rule:** one Discord bot token → one gateway poller. Do not put Carrier Ops token on default or specialist homes. Do not put First Watch token on Helm.

**Invite First Watch (if not in guild yet):**  
`https://discord.com/oauth2/authorize?client_id=1541881948660568116&permissions=309774896192&scope=bot%20applications.commands&guild_id=1541154515841974294&disable_guild_select=true`

**Wire token after MFA reset:**  
`/tmp/wire_firstwatch.sh '<token>'` then `hermes send --to discord:fleet "…"` smoke.


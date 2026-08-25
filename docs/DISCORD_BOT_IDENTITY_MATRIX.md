# Discord Bot Identity Matrix

**Status:** LIVE — Phase B reference. Updated by Boatswain.  
**Rule zero:** one Discord bot token = one gateway poller. Helm owns the only inbound gateway.  
**Companion:** `docs/DISCORD_CHANNELS.md`, `docs/INTER_AGENT_PROTOCOL.md`, `bots/BOT_MATRIX.md`

---

## 1. Existing Discord Applications

| App name | App ID | Token holder (bot) | Role |
|---|---|---|---|
| **Carrier Ops** | `1541150313405480970` | `chief_of_staff` (Helm) | **Gateway poller** — inbound from Michael. Owns `#command`. |
| **First Watch** | `1541881948660568116` | Shared by non-Helm bots | **Outbound only** — fleet posts to `#fleet`, `#alerts`, `#drafts` via REST send / webhook. No polling. |

**Hard rule:** only one bot per token may open a gateway (WebSocket) connection. First Watch is outbound-only; any bot that tries to poll it would evict every other user of that token.

---

## 2. Decision Tree — What Discord face does a new bot need?

```
New bot being created
        │
        ▼
Does it need to RECEIVE messages from Discord
(DMs, slash commands, @mentions in a channel)?
        │
    YES ▼                           NO ▼
        │                               │
        ▼                               ▼
 Is this a second                Does it need to POST
 command-inbound interface        to any Discord channel?
 approved by Michael?                   │
        │                           YES ▼         NO ▼
    YES ▼       NO ▼                    │               │
        │           │                   ▼               ▼
Create a new    Deny —             Does it only     NO DISCORD
Discord App     one-face rule      need webhooks?   FACE needed.
(rare; MFA      is frozen.         (fire-and-forget  AIPass mailbox
required;       Redesign the       alert posts,      or Kanban only.
see §4)         bot's role.        no callsign
                                   branding)?
                                        │
                                    YES ▼     NO ▼
                                        │         │
                                   WEBHOOK    Share FIRST WATCH
                                   ONLY       token for REST
                                   (§5)       send (§6)
```

---

## 3. Path Summary Table

| Path | When to use | What you need | Cost |
|---|---|---|---|
| **New Discord App** | Second inbound gateway; Michael-approved; coding crew ops channel | Create app in Discord dev portal; new token → Doppler; MFA on dev portal account | High friction; one-time |
| **Share First Watch** | Bot posts callsign-prefixed messages to fleet channels | Token already in Doppler as `FIRST_WATCH_TOKEN`; use `hermes discord send` or REST POST | Zero friction |
| **Webhook only** | Scripted one-way alert to a single channel; no callsign routing needed | `CARRIER_ALERTS_WEBHOOK` (or new webhook URL) in Doppler / `~/.hermes/.env` | Zero friction |
| **No Discord face** | Internal-only bot; Helm narrates results to `#command` | AIPass mailbox `_agent/mailbox/<id>/` | Zero friction |

---

## 4. New Discord Application — Steps (human only; never automated)

> **MFA warning:** the Discord developer portal requires MFA to create or reset tokens on a team account. Have your authenticator ready.

1. Log in to <https://discord.com/developers/applications> as the guild owner account.
2. **New Application** → name it for the bot's callsign (e.g., "First Mate" not an internal id).
3. **Bot** tab → **Add Bot** → uncheck all Privileged Intents unless the bot needs message content.
4. Copy the token **once** (it is not shown again without reset). Paste directly into Doppler as `<BOT_ID_UPPER>_DISCORD_TOKEN` — never into a file or chat.
5. **OAuth2 → URL Generator**: scopes = `bot`; permissions = minimum needed (Send Messages, Read Message History if needed). Copy the install URL.
6. Visit the install URL while logged in as server admin → Authorize.
7. Record the App ID in `docs/DISCORD_CHANNELS.md` and `bots/BOT_MATRIX.md`.
8. Run `hermes -p <bot_id> config set discord.token_env <ENVVAR_NAME>` to wire the bot home.

**Never print the token. Never commit it. Never pass it to another bot directly — route through LockBox.**

---

## 5. Webhook-only Setup

```bash
# Create webhook in Discord channel settings → Integrations → Webhooks → New Webhook
# Copy URL → store in Doppler or ~/.hermes/.env as CARRIER_<CHANNEL>_WEBHOOK
# Post from a script:
curl -s -X POST "$CARRIER_ALERTS_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"content": "**[Vigil]** Subscription quota at 90%."}'
```

No bot token needed. No gateway poller. Channel-scoped.

---

## 6. First Watch — Shared REST Send

First Watch token is already in Doppler. Any bot with the appropriate LockBox grant can POST via REST:

```bash
# hermes discord send (if configured on bot home):
hermes -p <bot_id> discord send --channel 1541866443765977138 "**[Callsign]** message"

# Or via REST (requires FIRST_WATCH_TOKEN from LockBox):
curl -s -X POST "https://discord.com/api/v10/channels/$CHANNEL_ID/messages" \
  -H "Authorization: Bot $FIRST_WATCH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "**[Callsign]** message body"}'
```

**Never open a gateway WebSocket with First Watch token.** REST send only.

---

## 7. Coding Crew — Recommendation

### Current state
`firstmate` (Mate) has no Discord presence. Coding output reaches Michael through:
- Kanban board (`carrier`)
- AIPass mailbox `_agent/mailbox/firstmate/`
- Helm narrating results in `#command`

### Recommendation

**Option A — No new Discord app (recommended for now)**
Mate posts coding status updates to a dedicated `#ready-room` channel via **First Watch REST send**. Helm narrates hand-offs to `#command`. Zero new tokens; zero new gateway pollers.

**Option B — New Discord App for coding crew (future)**
If Michael wants Mate or sub-roles to receive slash commands directly in `#ready-room` (e.g., `/deploy`, `/status`), create one new app named **"First Mate"** with gateway access scoped to coding crew channels only. This is the only approved reason to create a third Discord application.

**Option C — Webhook only**
For CI/CD completion pings or build alerts, use a webhook into `#catapult` or `#hangar-deck`. No token, no app, no gateway.

### Proposed coding crew channel layout
See `docs/CODING_CREW_CHANNELS.md` for full channel list.

**Default wiring for Mate (Option A):**
- Outbound: First Watch REST send → `#ready-room`
- Inbound: AIPass mailbox or Helm dispatch (no gateway needed)
- No new Discord Application required

---

## 8. Token Inventory (references only — no values here)

| Secret name in Doppler | Used by | Purpose |
|---|---|---|
| `CARRIER_OPS_DISCORD_TOKEN` | `chief_of_staff` | Gateway poller for `#command` inbound |
| `FIRST_WATCH_DISCORD_TOKEN` | Fleet (outbound) | REST send to fleet channels |
| `CARRIER_ALERTS_WEBHOOK` | Scripts / Vigil / Ledger | Webhook → `#alerts` (optional) |

---

*Maintained by Boatswain automation. Do not add snowflake IDs here — see `docs/DISCORD_CHANNELS.md`.*

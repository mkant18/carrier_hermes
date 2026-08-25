---
name: signal-lamp-discord
description: "Use when attaching Discord presence to a Hermes bot. Decision tree: new app vs First Watch share vs webhook-only vs no Discord face. Steps for each path. MFA warning, never-print-token rule, LockBox notes."
version: 1.0.0
author: Boatswain automation (Mission Alpha)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [carrier, fleet, discord, signal-lamp, bot, naval, onboarding]
    related_skills: [boatswain-new-bot, carrier-roster]
---

# Signal Lamp — Discord Wiring Runbook

The signal lamp is the fleet's optical voice: precise, directional, and never loud. This skill governs how a bot gets a Discord face — or decides it doesn't need one.

**Rule zero:** one Discord bot token = one gateway poller. Helm owns the only inbound gateway.  
**Reference:** `docs/DISCORD_BOT_IDENTITY_MATRIX.md` (full decision matrix + token inventory)

---

## 0. Read the Decision Tree First

```
Does the bot need to RECEIVE messages from Discord?
        │
    YES ▼                           NO ▼
        │                               │
Is this a second inbound face       Does it need to POST
approved by Michael?                to any Discord channel?
        │                               │
    YES ▼      NO ▼               YES ▼         NO ▼
        │          │                   │               │
  → PATH D     Deny. Redesign.   Webhook only?    → PATH E
  (New App)    One-face rule.         │           (No Discord)
                                  YES ▼     NO ▼
                                      │         │
                                → PATH C  → PATH B
                               (Webhook)  (First Watch)
```

### Path Summary

| Path | Label | When |
|---|---|---|
| **A** | Gateway — First Watch | Bot posts outbound only; no receive needed |
| **B** | REST Send — First Watch | Bot posts with callsign branding to fleet channels |
| **C** | Webhook Only | Fire-and-forget alerts; no callsign routing |
| **D** | New Discord Application | New inbound gateway; Michael-approved; rare |
| **E** | No Discord Face | Internal bot; Helm narrates to `#command` |

---

## Path A / B — Share First Watch (Outbound REST Send)

**When:** The bot needs to post messages (status, alerts, results) to fleet channels but does NOT need to receive messages. This is the default for all fleet bots.

**What you need:** The `FIRST_WATCH_DISCORD_TOKEN` from Doppler (via LockBox grant if the bot needs it directly).

### Steps

1. **Decide if the bot needs the token directly** or if Helm can relay for it:
   - Helm relay (simplest): Helm posts to the channel on behalf of the bot after receiving its AIPass result packet. No token wiring needed.
   - Bot posts directly: requires a LockBox grant for `FIRST_WATCH_DISCORD_TOKEN`.

2. **If Helm relay — no wiring needed.** Skip to verification.

3. **If bot posts directly — request via LockBox:**
   ```
   Helm: ACCESS_REQUEST
     resource: FIRST_WATCH_DISCORD_TOKEN
     requestor: <bot_id>
     purpose: outbound REST send to #<channel>
     blast_radius: post messages to guild 1541154515841974294 only
   ```
   Helm approves → issues HANDSHAKE_GRANT → bot redeems with LockBox.

4. **Wire the token env on the bot home (if direct):**
   ```bash
   hermes -p <bot_id> config set discord.token_env FIRST_WATCH_DISCORD_TOKEN --force
   hermes -p <bot_id> config set discord.guild_id 1541154515841974294 --force
   ```

5. **Test a REST send (do NOT open a gateway):**
   ```bash
   # Replace CHANNEL_ID and TOKEN with actual values from Doppler (never hardcode)
   curl -s -X POST "https://discord.com/api/v10/channels/${CHANNEL_ID}/messages" \
     -H "Authorization: Bot ${FIRST_WATCH_DISCORD_TOKEN}" \
     -H "Content-Type: application/json" \
     -d "{\"content\": \"**[${CALLSIGN}]** Signal lamp test — if you see this, wiring is live.\"}"
   ```

6. **Confirm in the channel** that the message appeared with the correct callsign prefix.

### ⚠ Warning: Never open a gateway with First Watch

The following is **FORBIDDEN**:
```bash
# DO NOT DO THIS — evicts all other users of the token
hermes -p <bot_id> config set discord.gateway true
```

First Watch is outbound REST only. Gateway polling is reserved for `chief_of_staff` (Carrier Ops token).

---

## Path C — Webhook Only

**When:** The bot (or a script) needs to fire one-way alerts to a single channel. No token needed. No callsign branding required.

### Steps

1. **Create the webhook in Discord:**
   - Channel Settings → Integrations → Webhooks → New Webhook
   - Name it (e.g., "Vigil Alerts"), copy the URL.

2. **Store in Doppler or `~/.hermes/.env`** (never commit):
   ```
   CARRIER_<CHANNEL>_WEBHOOK=https://discord.com/api/webhooks/...
   ```

3. **Post from a script:**
   ```bash
   curl -s -X POST "$CARRIER_ALERTS_WEBHOOK" \
     -H "Content-Type: application/json" \
     -d '{"content": "**[Vigil]** Subscription quota at 90%. Check #alerts."}'
   ```

4. **For richer messages**, use Discord embeds:
   ```bash
   curl -s -X POST "$CARRIER_ALERTS_WEBHOOK" \
     -H "Content-Type: application/json" \
     -d '{
       "embeds": [{
         "title": "Spend Alert",
         "description": "OpenRouter spend exceeded $5 threshold.",
         "color": 16711680
       }]
     }'
   ```

5. **Wire into cron or bot script** as needed. No Hermes config change required.

---

## Path D — New Discord Application (Inbound Gateway)

**When:** A bot needs to receive messages directly from Discord (slash commands, @mentions, DMs). This is **rare** and requires Michael's explicit approval.

> **MFA Warning:** The Discord developer portal requires MFA to create or reset tokens. Have your authenticator app ready before starting. Do not attempt this on a shared or insecure machine.

### Steps (human-only — cannot be automated)

1. **Get Michael's written approval** for the new inbound face. Document it in a mission log or Kanban card.

2. **Log in** to <https://discord.com/developers/applications> as the guild owner account.

3. **New Application:**
   - Name: use the callsign, not the bot_id (e.g., "First Mate", not "firstmate")
   - Description: one sentence about the bot's purpose

4. **Bot tab → Add Bot:**
   - Uncheck all Privileged Intents unless the bot explicitly needs message content
   - Enable only: `SERVER MEMBERS INTENT` if needed for member lookup; otherwise off

5. **Copy the token (once only):**
   - Click **Reset Token** (requires MFA confirmation)
   - Copy the token **immediately** to a clipboard manager or password manager
   - Paste directly into Doppler as `<BOT_ID_UPPER>_DISCORD_TOKEN`
   - Do NOT paste into a terminal, file, Slack, or any chat

6. **OAuth2 → URL Generator:**
   - Scopes: `bot`
   - Bot Permissions: minimum needed (Send Messages, Read Message History — add only what is required)
   - Copy the install URL

7. **Authorize the bot** to the Carrier Ops server:
   - Visit the install URL while logged in as server admin
   - Click Authorize

8. **Record in docs:**
   ```
   docs/DISCORD_CHANNELS.md  — add App ID to token inventory table
   bots/BOT_MATRIX.md        — note Discord app in MCP column
   docs/DISCORD_BOT_IDENTITY_MATRIX.md — add row to §8 Token Inventory
   ```

9. **Wire in Hermes:**
   ```bash
   hermes -p <bot_id> config set discord.token_env <BOT_ID_UPPER>_DISCORD_TOKEN --force
   hermes -p <bot_id> config set discord.guild_id 1541154515841974294 --force
   hermes -p <bot_id> config set discord.gateway true --force
   ```

10. **Smoke test:**
    ```bash
    hermes -p <bot_id> discord status
    ```
    Confirm the bot appears online in the Discord server member list.

11. **Commit the doc changes** (not the token):
    ```bash
    git add docs/DISCORD_CHANNELS.md bots/BOT_MATRIX.md docs/DISCORD_BOT_IDENTITY_MATRIX.md
    git commit -m "feat(discord): add Discord App for <bot_id> (<Callsign>)"
    git push origin main
    ```

---

## Path E — No Discord Face

**When:** The bot is internal-only. Helm narrates its results to `#command`. No token, no webhook, no gateway.

### Steps

1. Ensure the bot has an AIPass mailbox:
   ```bash
   mkdir -p ~/carrier_hermes/_agent/mailbox/<bot_id>/inbox
   mkdir -p ~/carrier_hermes/_agent/mailbox/<bot_id>/outbox
   ```

2. Helm reads the outbox and summarizes results in `#command` after dispatching.

3. No Hermes discord config needed. Confirm discord is disabled:
   ```bash
   hermes -p <bot_id> config get discord 2>/dev/null || echo "no discord config — correct"
   ```

---

## Never-Print-Token Rule

At no point should a token value appear in:
- Any terminal output that could be captured in logs
- Any Hermes chat message or session
- Any file committed to git
- Any AIPass mail body
- Any Discord message (yes, bots have posted their own tokens — never again)

If a token is compromised, reset it immediately via the Discord developer portal (requires MFA) and update Doppler.

---

## LockBox Note

Any bot that needs a token at runtime must request it through the grants system:

```
Helm:    ACCESS_REQUEST  →  APPROVE/DENY/NARROW  →  HANDSHAKE_GRANT
LockBox: REDEEM          →  token value flows to bot's env only
Bot:     uses token for this session only; does not persist
```

Helm never holds raw token values. LockBox never sends token values to Helm. This is the hard rule.

---

## Channel ID Reference (Carrier Ops guild: 1541154515841974294)

| Channel | ID |
|---|---|
| `#command` | `1541866378255011980` |
| `#drafts` | `1541866401432871002` |
| `#alerts` | `1541866423427801148` |
| `#fleet` | `1541866443765977138` |

Coding crew channels: see `docs/CODING_CREW_CHANNELS.md` (IDs TBD by Michael).

---

## Pitfalls

- **Never poll with First Watch** — it is outbound REST only. One gateway = Carrier Ops = Helm.
- **Token reset invalidates all previous tokens** — if you reset in the dev portal, you must update Doppler immediately or all bots using that token go dark.
- **MFA is required** for Discord dev portal token operations — plan for it; don't start the process without your authenticator.
- **Gateway connection = one per token** — if two Hermes processes open a gateway with the same token, Discord closes both and may ban the bot.
- **Webhook URLs are secrets** — store in Doppler or `~/.hermes/.env`, never in the repo.
- **Intents must be declared** — if the bot needs to read message content (not just slash commands), the `MESSAGE_CONTENT` privileged intent must be enabled in the dev portal AND in the gateway config.

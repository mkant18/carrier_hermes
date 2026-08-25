# Discord Wing Apps — Setup Guide

**Status:** Awaiting Michael to create 4 apps in the Discord dev portal.  
**Required:** MFA authenticator app, guild owner account, ~10 min.

Guild: **Carrier Ops** (`1541154515841974294`)  
Portal: <https://discord.com/developers/applications>

---

## Why 4 apps, not 18

One Discord Application = one bot token = one distinct identity in the member list and
message author field. We use **per-message `username` and `avatar_url` overrides** so
every individual bot in a wing posts with its own callsign and emoji — the token is shared
within the wing but each message looks like a different person sent it.

No gateways are opened for these apps. They are outbound-REST-only. Zero extra token
(LLM) cost.

---

## The 4 Apps to Create

### App 1 — Coding Wing

| Field | Value |
|---|---|
| **App name** | `Coding Wing` |
| **Bot display name** | `Coding Wing` |
| **Description** | Carrier Fleet – Coding Wing (Wrench + Mate) |
| **Doppler key** | `CODING_WING_DISCORD_TOKEN` |
| **Members** | `coding_lt` (Wrench 🔧), `firstmate` (Mate ⚙️) |
| **Primary channels** | `#ready-room`, `#catapult`, `#fleet` |
| **Avatar suggestion** | ✈️ or 🔧 icon (set in Bot tab → Avatar) |

### App 2 — Ops Wing

| Field | Value |
|---|---|
| **App name** | `Ops Wing` |
| **Bot display name** | `Ops Wing` |
| **Description** | Carrier Fleet – Ops Wing (Deck + Inbox + Quill + Chronos + Tasker + Purse) |
| **Doppler key** | `OPS_WING_DISCORD_TOKEN` |
| **Members** | `ops_lt` (Deck 🗂️), `email_reader` (Inbox 📬), `email_drafter` (Quill 🪶), `calendar_manager` (Chronos 🕰️), `todoist_manager` (Tasker 📋), `finance_reader` (Purse 👛) |
| **Primary channels** | `#fleet`, `#drafts` |
| **Avatar suggestion** | 🗂️ or ⚙️ icon |

### App 3 — Knowledge Wing

| Field | Value |
|---|---|
| **App name** | `Knowledge Wing` |
| **Bot display name** | `Knowledge Wing` |
| **Description** | Carrier Fleet – Knowledge Wing (Stacks + Librarian + Clerk) |
| **Doppler key** | `KNOWLEDGE_WING_DISCORD_TOKEN` |
| **Members** | `knowledge_lt` (Stacks 📚), `vault_librarian` (Librarian 📖), `obsidian_archivist` (Clerk 📥) |
| **Primary channels** | `#fleet` |
| **Avatar suggestion** | 📚 icon |

### App 4 — Recon Wing

| Field | Value |
|---|---|
| **App name** | `Recon Wing` |
| **Bot display name** | `Recon Wing` |
| **Description** | Carrier Fleet – Recon Wing (Chart + Sonar + Probe) |
| **Doppler key** | `RECON_WING_DISCORD_TOKEN` |
| **Members** | `hermes_ai_explorer` (Chart 🗺️), `passive_watch` (Sonar 🔊), `research_agent` (Probe 🔍) |
| **Primary channels** | `#fleet` |
| **Avatar suggestion** | 🗺️ or 🔍 icon |

---

## Steps (per app — repeat 4×)

> **MFA warning:** Discord requires MFA to create or reset bot tokens on accounts with
> 2FA enabled. Have your authenticator ready before starting.

1. Go to <https://discord.com/developers/applications> → **New Application**
2. Set the **name** from the table above → Create
3. **General Information** tab → set Description from table
4. **Bot** tab → **Add Bot** (or Reset Token if it already exists)
   - Uncheck all Privileged Gateway Intents (MESSAGE_CONTENT, SERVER_MEMBERS, PRESENCE)
   - We do NOT need any intents — outbound REST only
5. Click **Reset Token** → confirm MFA → **copy the token immediately**
6. Store in Doppler:
   ```bash
   doppler secrets set <DOPPLER_KEY>=<token> --project carrier-ops --config prd
   ```
   Replace `<DOPPLER_KEY>` with the key from the table (e.g. `CODING_WING_DISCORD_TOKEN`).
7. **Do NOT paste the token anywhere else.** Not into a terminal, file, or chat.
8. **OAuth2 → URL Generator**: scopes = `bot`, permissions = `Send Messages` only
9. Visit the install URL while logged into the Carrier Ops server as admin → Authorize
10. Confirm the bot appears in the server member list (it will show as offline — expected)
11. Run the wiring script:
    ```bash
    bash ~/carrier_hermes/scripts/wire_wing_tokens.sh
    ```

---

## Command Tier (Vigil, Ledger, LockBox)

These three post to `#command` and `#alerts`. They are not part of a wing. They continue
using First Watch (`DISCORD_FLEET_BOT_TOKEN`) with callsign username-override per message.
No new app needed for them.

---

## After All 4 Apps Are Created

Run:
```bash
bash ~/carrier_hermes/scripts/wire_wing_tokens.sh   # pulls tokens from Doppler, wires .env
bash ~/carrier_hermes/scripts/apply_bot_matrix.sh   # locks gateway=false, sets guards
bash ~/carrier_hermes/scripts/smoke_fleet.sh        # verify fail=0
```

The `wire_wing_tokens.sh` script:
- Pulls each token from Doppler
- Writes it ONLY to the `.env` files of bots in that wing
- Never prints the token value
- Writes `DISCORD_REQUIRE_MENTION=true` and `DISCORD_ALLOWED_USERS=174349224870150144`
  to all non-gateway bot `.env` files as defense-in-depth

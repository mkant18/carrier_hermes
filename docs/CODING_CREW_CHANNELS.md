# CODING_CREW_CHANNELS.md — Coding Crew Discord Presence

**Status:** Proposed. Channel IDs to be filled by Michael after creating in Discord.  
**Companion:** `docs/DISCORD_BOT_IDENTITY_MATRIX.md`, `bots/BOT_MATRIX.md`

---

## Purpose

Dedicated Discord channels for the coding crew (`firstmate` / Mate, and any future coding sub-roles). Named in naval-aviation style — the coding crew works the flight deck.

---

## Proposed Channels

| Channel name | Purpose | Discord ID |
|---|---|---|
| `#ready-room` | Mate's primary outbound channel: task summaries, PR status, completion notices. Equivalent of the aircrew briefing room. | _(to be filled)_ |
| `#catapult` | Launch: CI/CD pipeline starts, deploy triggers, build kick-offs. Short automated posts only. | _(to be filled)_ |
| `#hangar-deck` | Work in progress: active branches, worktree status, mid-task check-ins. Longer-running background jobs report here. | _(to be filled)_ |
| `#lso-notes` | Landing signal officer notes: code review feedback, PR comments, post-merge retrospectives, quality flags. | _(to be filled)_ |
| `#wire-room` | (Optional) Inter-bot coordination notes for coding sub-roles: codex, opencode, sub-agents. Low-volume. | _(to be filled)_ |

---

## Routing Rules

1. **Mate posts to `#ready-room` by default** via First Watch REST send (no new Discord App needed; see `DISCORD_BOT_IDENTITY_MATRIX.md` Option A).
2. **CI/CD scripts** post build events to `#catapult` via webhook (no token needed).
3. **Long-running jobs** checkpoint to `#hangar-deck` with job ID so Michael can correlate with Kanban.
4. **`#lso-notes`** is the code review surface — Mate writes there after `/review` or `github-code-review` skill runs.
5. **Helm narrates** coding crew hand-offs in `#command` as before; `#ready-room` is *supplement*, not replacement.

---

## Bot Wiring

No new Discord Application is required for Option A (recommended):

```
Mate (firstmate) → First Watch REST send → #ready-room
CI scripts       → Webhook               → #catapult
```

If Option B (gateway for `#ready-room`) is approved later, create one new Discord App named **"First Mate"** and record its App ID in `docs/DISCORD_CHANNELS.md`.

---

## Next Steps for Michael

1. Create the above channels in the Carrier Ops Discord server (Text category `1541154516811120760`).
2. Paste the snowflake IDs into this table.
3. Cross-reference `docs/DISCORD_CHANNELS.md` with the new IDs.
4. Wire `#catapult` webhook: Discord channel settings → Integrations → Webhooks → copy URL → add to Doppler as `CARRIER_CATAPULT_WEBHOOK`.
5. Confirm Option A or B for Mate's inbound capability.

---

*Channel names are frozen pending Michael's approval. Do not create the channels or register snowflake IDs without Michael's sign-off.*

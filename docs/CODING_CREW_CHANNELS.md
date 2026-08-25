# CODING_CREW_CHANNELS.md — Coding Crew Discord Presence

**Status:** LIVE — `#ready-room` and `#catapult` created and wired (2026-08-25).  
**Companion:** `docs/DISCORD_BOT_IDENTITY_MATRIX.md`, `bots/BOT_MATRIX.md`, `docs/DISCORD_CHANNELS.md`

---

## Purpose

Dedicated Discord channels for the coding wing (Wrench / `coding_lt` and Mate / `firstmate`). Named in naval-aviation style — the coding crew works the flight deck.

---

## Live Channels

| Channel name | Purpose | Discord ID |
|---|---|---|
| `#ready-room` | **Coding wing home.** Wrench standup, Mate task summaries, PR status, completion notices. Wrench and Mate's `DISCORD_HOME_CHANNEL`. | `1541919952599130132` |
| `#catapult` | **Launch board.** Wrench posts DISPATCH lines here when slinging jobs to Mate. CI/CD kicks, deploy triggers, build starts. | `1541919999894229053` |

## Proposed (not yet created — Michael's call)

| Channel name | Purpose | Discord ID |
|---|---|---|
| `#hangar-deck` | Work in progress: active branches, worktree status, mid-task check-ins. | _(TBD)_ |
| `#lso-notes` | LSO notes: code review feedback, PR comments, post-merge retros. | _(TBD)_ |

---

## Routing Rules

1. **Wrench (`coding_lt`) home is `#ready-room`** — standups and wing coordination land there.
2. **Wrench DISPATCHes to `#catapult`** when launching a job to Mate (`fleet_signal.sh DISPATCH`).
3. **Mate (`firstmate`) home is `#ready-room`** — task summaries, PR notices, ACK/TRAP confirmations.
4. **Mate ACKs in `#catapult`** when it picks up a job; TRAPs back to `#fleet` on completion.
5. **Helm narrates** coding wing hand-offs in `#command` as before — `#ready-room` is the crew's own space.

---

## Bot Wiring (live)

```
Wrench (coding_lt) → First Watch REST → #ready-room (home), #fleet, #catapult
Mate (firstmate)   → First Watch REST → #ready-room (home), #fleet, #catapult
```

`DISCORD_HOME_CHANNEL` and `DISCORD_ALLOWED_CHANNELS` are set in each bot's `.env`
by `scripts/install_bot_homes.sh`. No new Discord Application needed — both use
First Watch (outbound REST, no gateway).

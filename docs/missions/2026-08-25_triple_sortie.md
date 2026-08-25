# Triple sortie — 2026-08-25

Michael ordered three parallel missions under project **Carrier Doctrine & Fleet Comms** (`~/carrier_hermes`).

| Callsign | Mission | Objective |
|---|---|---|
| **ALPHA** | Boatswain / Signal Lamp | Automate Hermes bot create + optional Discord identity; skill/workflow |
| **BRAVO** | GitHub shore power | Agents (esp. FirstMate coding crew) read/write GitHub repos safely |
| **CHARLIE** | Doctrine / lexicon | Naval + naval-aviation diction for **INTERNAL-FACING only** |

## Standing orders (all missions)

1. Product language: **bot** (not “profile” to Michael); CLI may say `hermes profile create`.
2. Dual Discord apps frozen: **Carrier Ops** → Helm only; **First Watch** → non-Helm shared outbound. **One Discord token = one gateway poller.**
3. New Hermes bot does **not** automatically need a new Discord Application. Prefer: (a) no Discord face, (b) First Watch attributed send, (c) webhook nickname, (d) new app only for true multi-@mention inbound.
4. Coding → FirstMate crew; specialists not general user-facing Discord bots.
5. **Naval / naval-aviation lingo: INTERNAL ONLY** — Discord fleet channels, Bot Chat, SOULs, job/result packets, #command/#fleet narration. **Forbidden** on email, calendar invites, Todoist titles shown to others, Quill drafts to external humans, GitHub PR bodies aimed at non-fleet collaborators unless Michael says otherwise.
6. Never invent Discord snowflakes. Never commit `.env` or tokens. Secrets via LockBox handshake only.
7. Prefer docs + skills + scripts in `~/carrier_hermes` and `~/.hermes/skills/`; Phase A freeze before live token wiring when adding bots.

## Deliverables expected

- ALPHA: skills + runbook + decision matrix app vs shared token
- BRAVO: auth posture, FirstMate wiring, LockBox GH token path if needed, skill/checklist
- CHARLIE: lexicon + style guide + SOUL snippet + rollout plan across internal surfaces

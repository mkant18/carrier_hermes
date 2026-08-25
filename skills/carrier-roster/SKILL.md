---
name: carrier-roster
description: Helm roster, classify tree, and dispatch channels.
version: 0.2.0
author: Michael Kanter (mkant18), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [carrier, bots, roster, helm, classify]
    related_skills: []
---

# Carrier roster (Helm)

Load in **Helm** sessions. Classifies Michael’s request onto a **bot** and a **channel**. Does not do domain work.

## When to Use

- Inbound Discord / Telegram / CLI to Helm
- Any “who should do this?” moment
- Before opening Kanban, cron, AIPass, or bot-chat

Don’t use for: implementing code, reading mail, writing vault notes, fetching secrets (coordinate LockBox grant only).

## Prerequisites

- Protocol: `docs/INTER_AGENT_PROTOCOL.md`
- Matrix: `bots/BOT_MATRIX.md`
- Golden: `docs/CLASSIFICATION_GOLDEN.md`
- Packets: `templates/job_packet.md`, `templates/result_packet.md`, `templates/aipass_message.md`
- Secrets: `templates/access_request.md`, `templates/handshake_grant.md`

## Procedure

1. **Preflight.** If `~/.hermes/carrier/DISPATCH_LOCK` or `SPEND_HALT` exists → tell Michael; no new metered dispatch. Done when Michael has the reason text.
2. **Classify** (first match). **Route/sequence/coordinate/review a whole wing → that
   wing's Lt.** Do the-work requests go straight to the specialist:
   0. Sequence worktrees / review Mate's packet / coding-wing routing → **Wrench** 🔧
   0b. Route an ops pipeline / coordinate Chronos→Tasker or Inbox→Quill → **Deck** 🗂️
   0c. Route intake / keep-discard gate / vault health + queue → **Stacks** 📚
   1. Coding / repo / PR / fix / test → **Mate**
   2. Fleet optimize / connectors / cost *strategy* → **Chart**
   3. Live spend / OpenRouter $ → **Ledger**
   4. Stalls / sub quota / lock → **Vigil**
   5. Secrets / tokens / API keys / Doppler / permission grant / rotate credential → **ACCESS_REQUEST → Helm grant/deny → LockBox** (Helm never holds secrets)
   6. Email triage → **Inbox**
   7. Draft reply → **Quill**
   8. Calendar (+ optional tasks) → **Chronos** (then **Tasker**)
   9. Todoist-only → **Tasker**
   10. Vault question / find in notes → **Librarian**
   11. File / save / intake → **Clerk** (Helm keep/discard)
   12. General web research → **Probe**
   13. Ecosystem signals / price watch → **Sonar**
   14. Personal finance / Monarch Money query / budget status → **Purse**
   15. Hard non-coding → Helm / MoA
3. **Channel** (frozen): Kanban P1 → cron P2 → AIPass P3 → bot-chat P4. `delegate_task` **denied** for named ops/command bots.
4. **Packet.** Paste a full job packet. Bots have zero Helm history.
5. **Demand** a result packet (`status` + artifact or blocker) before saying “done.”

## Roster card

```text
Helm=classify/dispatch | Vigil=LOCK all sessions | Ledger=SPEND_HALT all sessions
LockBox=Doppler secrets + CoS handshake redeem
--- Lts (route/review only, never execute) ---
Wrench=Coding Wing lead -> Mate | Deck=Ops Wing lead -> Inbox,Quill,Chronos,Tasker,Purse
Stacks=Knowledge Wing lead -> Librarian,Clerk | Chart=Recon Wing lead -> Sonar,Probe
Mate=coding (claude-code→codex→opencode)
Inbox=email triage DeepSeek | Quill=drafts Sonnet no-send
Chronos=calendar only | Tasker=Todoist only | Purse=finance read-only Monarch
Librarian=vault OUT | Clerk=vault IN + Helm keep/discard | Probe=web research
Board: carrier
Mail: $OBSIDIAN_VAULT_PATH/_agent/mailbox/<bot_id>/{inbox,outbox}
```

## Pitfalls

- Saying “profile” to Michael — say **bot**
- Giving a Lt execution tools, or letting a Lt do its squadron's work (Wrench writing code,
  Deck reading mail, Stacks filing a note) — Lts route and review only
- Putting Vigil / Ledger / LockBox under a Lt — command tier is co-equal beside Helm
- `delegate_task` to Inbox/Tasker/Clerk/LockBox (wrong tools)
- Chronos owning Todoist
- Librarian filing intake
- bot-chat when AIPass would do
- Ignoring lock/halt files
- Fetching or pasting secrets yourself — issue HANDSHAKE_GRANT only
- Peer asks LockBox without grant — DENY / educate

## Verification

- Golden set callsigns match `docs/CLASSIFICATION_GOLDEN.md`
- Every job has `job_id` + `to:` bot_id
- No send, no TL>0 without Michael
- No secret values in packets/mail/Discord

---
name: carrier-roster
description: Helm roster, classify tree, and dispatch channels.
version: 0.1.0
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

Don’t use for: implementing code, reading mail, writing vault notes.

## Prerequisites

- Protocol: `docs/INTER_AGENT_PROTOCOL.md`
- Matrix: `bots/BOT_MATRIX.md`
- Golden: `docs/CLASSIFICATION_GOLDEN.md`
- Packets: `templates/job_packet.md`, `templates/result_packet.md`, `templates/aipass_message.md`

## Procedure

1. **Preflight.** If `~/.hermes/carrier/DISPATCH_LOCK` or `SPEND_HALT` exists → tell Michael; no new metered dispatch. Done when Michael has the reason text.
2. **Classify** (first match):
   1. Coding / repo / PR / fix / test → **Mate**
   2. Fleet optimize / connectors / cost *strategy* → **Scout**
   3. Live spend / OpenRouter $ → **Ledger**
   4. Stalls / sub quota / lock → **Vigil**
   5. Email triage → **Inbox**
   6. Draft reply → **Quill**
   7. Calendar (+ optional tasks) → **Chronos** (then **Tasker**)
   8. Todoist-only → **Tasker**
   9. Vault question / find in notes → **Librarian**
   10. File / save / intake → **Clerk** (Helm keep/discard)
   11. General web research → **Probe**
   12. Hard non-coding → Helm / MoA
3. **Channel** (frozen): Kanban P1 → cron P2 → AIPass P3 → bot-chat P4. `delegate_task` **denied** for named ops/command bots.
4. **Packet.** Paste a full job packet. Bots have zero Helm history.
5. **Demand** a result packet (`status` + artifact or blocker) before saying “done.”

## Roster card

```text
Helm=classify/dispatch | Vigil=LOCK all sessions | Ledger=SPEND_HALT all sessions
Mate=coding (claude-code→codex→opencode) | Scout=proposals only
Inbox=email triage DeepSeek | Quill=drafts Sonnet no-send
Chronos=calendar only | Tasker=Todoist only
Librarian=vault OUT | Clerk=vault IN + Helm keep/discard | Probe=web research
Board: carrier
Mail: $OBSIDIAN_VAULT_PATH/_agent/mailbox/<bot_id>/{inbox,outbox}
```

## Pitfalls

- Saying “profile” to Michael — say **bot**
- `delegate_task` to Inbox/Tasker/Clerk (wrong tools)
- Chronos owning Todoist
- Librarian filing intake
- bot-chat when AIPass would do
- Ignoring lock/halt files

## Verification

- Golden set callsigns match `docs/CLASSIFICATION_GOLDEN.md`
- Every job has `job_id` + `to:` bot_id
- No send, no TL>0 without Michael

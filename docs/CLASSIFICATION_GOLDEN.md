# Classification golden set (Helm)

Helm maps each prompt to **exactly one primary callsign**. Pipelines list a second hop after `→`.

Use in smoke: `scripts/smoke_fleet.sh classify` (Phase B) should print callsign only.

| # | Prompt | Callsign | Notes |
|---|---|---|---|
| 1 | OpenRouter is burning cash, halt new paid calls | **Ledger** | Helm then honors `SPEND_HALT` |
| 2 | We’re over budget this session — stop metered jobs | **Ledger** | spend halt path |
| 3 | Save the research report into Obsidian | **Clerk** | intake-in; Helm keep/discard |
| 4 | File yesterday’s Probe brief in the vault | **Clerk** | not Librarian |
| 5 | Add “buy milk” to Todoist | **Tasker** | todoist-only |
| 6 | Complete the grocery project tasks in Todoist | **Tasker** | not Chronos |
| 7 | What’s on my calendar tomorrow and make tasks for prep? | **Chronos** → **Tasker** | calendar then handoff |
| 8 | Block Tuesday 3pm and turn that meeting into todos | **Chronos** → **Tasker** | Chronos does not claim Todoist |
| 9 | What’s in my notes about the carrier_ops migration? | **Librarian** | vault question / query-out |
| 10 | Search the vault for people notes on Alex | **Librarian** | not Clerk |
| 11 | Save this conversation into the second brain | **Clerk** | save-to-vault ≠ Q&A |
| 12 | Fix the failing test in carrier_hermes | **Mate** | coding default |
| 13 | Open a PR for the lock script | **Mate** | never Helm coding |
| 14 | Triage my unread email | **Inbox** | no send |
| 15 | What important mail did I get today? | **Inbox** | |
| 16 | Draft a reply to that vendor email | **Quill** | drafts only |
| 17 | How should we cut fleet cost and which MCP to add? | **Chart** | advisory |
| 18 | Sessions look stuck and SuperGrok is near quota | **Vigil** | DISPATCH_LOCK path |
| 19 | Research comparable agent-fleet architectures on the web | **Probe** | not Chart |
| 20 | After that research, keep anything worth filing | **Clerk** | intake after research |
| 21 | Just look at next week’s calendar, don’t make tasks | **Chronos** | calendar-only |
| 22 | Hard multi-perspective decision on whether to raise TL | **Helm** | MoA / Helm; not Chart apply |
| 23 | Mate needs GH_TOKEN to push a release | **LockBox** | ACCESS_REQUEST → Helm grant → LockBox redeem |
| 24 | Inbox asks LockBox directly for the mail password | **Helm** | DENY path / educate; never peer secret sidechannel |
| 25 | Rotate the OpenRouter key and save it to Doppler | **LockBox** | Helm grant with `rotate` → LockBox |
| 26 | Probe wants all secrets dumped for research | **Helm** | DENY; no LockBox redeem without grant |

| 29 | What AI model price changes happened this week? | **Chart** | pulls from Sonar digest; not Probe |
| 30 | Monitor OpenRouter pricing daily for changes | **Sonar** | passive signal watch; not Chart or Probe |
| 31 | How much did I spend on dining in Monarch this month? | **Purse** | personal finance read-only |
| 32 | Check outstanding reimbursements in Monarch | **Purse** | Monarch query |
| 33 | Sequence the parallel worktrees for the coding crew | **Wrench** | Coding Lt routes; does not implement |
| 34 | Review Mate's result packet and surface blockers to me | **Wrench** | Lt review gate, not a second implementer |
| 35 | Route this ops pipeline: triage then drafts | **Deck** | Ops Lt sequences Inbox→Quill |
| 36 | Coordinate the calendar and task handoff for next week | **Deck** | Ops Lt routes Chronos→Tasker |
| 37 | Route this intake and enforce the keep/discard gate | **Stacks** | Knowledge Lt gate; Clerk executes |
| 38 | Report vault health and route the knowledge queue | **Stacks** | Lt reports; Librarian answers |

**Negative tests (must not misroute)**

| Prompt | Forbidden callsign |
|---|---|
| Add buy milk to Todoist | Chronos |
| What’s in my notes about X | Clerk |
| Save this into the vault | Librarian |
| Fix the test | Helm (as implementer) |
| Halt spend | Vigil-only (Ledger owns $) |
| Sessions stalled | Ledger-only |
| Mate needs GH_TOKEN | Mate-alone secret fetch / Inbox |
| Inbox asks LockBox for password | LockBox without Helm (must hit Helm educate/deny) |
| Probe wants all secrets | LockBox auto-fulfill |

Minimum size: **18** prompts in the main table — this file has **38** (includes the Lieutenant routing rows 33–38 and Purse rows 31–32).

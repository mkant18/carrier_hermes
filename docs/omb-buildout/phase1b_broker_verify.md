# Phase 1B — Permission Broker Patch Runtime Verification

**Date:** 2026-08-27
**OMB harness:** http://127.0.0.1:8799 (server child pid 16836, forked 2026-08-26T21:13:59.729Z, still the live process at time of writing)
**OMB source:** `C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/`

---

## 1. Static verifier

```
python3 C:/Users/micha/AppData/Local/hermes/skills/autonomous-ai-agents/openmausbot/scripts/check_omb_patches.py
```

```
✅ APPLIED     [procs.js] carrier_openmausbot patch: monotonic counter
✅ APPLIED     [drivers/claude.js] carrier_openmausbot patch: a broker that never came up
✅ APPLIED     [drivers/claude.js] carrier_openmausbot patch: broker listen failure used to be
✅ APPLIED     [index.js] carrier_openmausbot patch: ask_bot from a human-initiated tu
✅ APPLIED     [index.js] carrier_openmausbot patch: bots invoked via ask_bot
✅ All 5 patches already applied. Nothing to do.
```
Exit code 0 — **5/5 applied**.

## 2. Syntax check

```
node --check procs.js            → OK
node --check drivers/claude.js   → OK
node --check index.js            → OK
```

## 3. Code coherence review

| # | Patch | File | Finding |
|---|-------|------|---------|
| 1 | Monotonic pipe-name counter | `procs.js` `brokerSocketPath()` | Module-level `let _brokerSeq = 0;` appended as `-${_brokerSeq++}` to the Windows named-pipe path. Coherent, no drift, single definition, incremented on every call. |
| 2a | Broker-never-came-up detection | `drivers/claude.js` `createPermissionBroker()` | `server.on("error", (error) => { console.error(...); opts.onBrokerError?.(error); })` wired right after server creation, before `server.listen(opts.socketPath)`. Coherent. |
| 2b | Broker error → visible `turn.failed` | `drivers/claude.js` call site (~line 606-622) | `onBrokerError` callback emits a `turn.failed` event with message `"Permission broker could not start: <reason>. Restart OpenMausBot to fix this."` and calls `settle(false, "broker-error")`. Coherent, matches docs. |
| 3a (brief #4) | `ask_bot` unattended:false | `index.js` `askBotAndWait()` | `startTurn(targetBotId, message, { commsDepth: depth + 1, unattended: false })` — hard-coded, no longer inherits caller's unattended state. Coherent. Note: the separate `runDelegatedTurn()` path (async `delegate_bot`, not synchronous `ask_bot`) still does `unattended: isUnattended(...)` — that is intentional per the patch's documented scope (only `askBotAndWait`/`ask_bot` was the target of this fix) and is not a drift. |
| 3b (brief #5) | `ask_bot` requires text reply | `index.js` `startTurn()` system-prompt assembly | At `commsDepth > 0` an explicit instruction is appended requiring a plain-text reply even on tool failure/denial. Coherent, matches docs. |

No half-applied or drifted patches found.

## 4. API map (discovered from `index.js` route table)

The server is a hand-rolled router (`path.match(...)` against precompiled regexes), not Express — no `app.get/post`. Relevant endpoints found:

- `GET  /api/bots` — list bots (id, threadId, modelSelection, busy, alwaysAllow, autoApprove, etc.) + recent messages
- `GET  /api/threads/:id/messages` — scrollback page for a thread
- `POST /api/bots/:id/messages` — send a user message to a bot; body `{text, replyToId?}`; starts a turn (or steers/queues if busy) → `202`/`200 {ok:true}`
- `POST /api/bots/:id/messages/:msgId/edit` — fork+rerun from an edited message
- `POST /api/bots/:id/active-branch` — switch visible fork
- `POST /api/bots/:id/respond` — answer a pending permission/question card by bot id; body `{requestId, behavior: "allow"|"deny"|"answer", message?}`
- `POST /api/threads/:id/respond` — same, addressed by thread id (handles room/group speaker resolution)
- `GET  /api/events` — the live SSE stream (`text/event-stream`), separate from the on-disk NDJSON files under `C:/Users/micha/.openmausbot/events/`
- `POST /api/internal/ask-bot` — internal bot-to-bot synchronous ask (`askBotAndWait`, patch 3a's target)
- `POST /api/internal/delegate-bot` — internal async handoff (`runDelegatedTurn`, NOT patched — see note above)

Each thread's full turn/tool/event history is durably logged to `C:/Users/micha/.openmausbot/events/<threadId>.ndjson`, one file per thread, append-only, containing `turn.started`, `session.started`, `item.started/completed`, `content.delta`, `request.opened`, `request.resolved`, `turn.completed/failed`, `thread.token-usage.updated`.

## 5. Runtime Test A — broker exercise (approval card, not silent deny)

**Bot used:** Stacks (`ebd24a31-b6cc-4dd7-96f8-6418fa43f4c4`, Knowledge Wing worker, model `claude-sonnet-4-6`, `autoApprove:false`). Not Helm, not Marshal.

**Note on bot selection:** the brief's preferred zero-cost path (an `ollama::` model on the claude engine wrapper) was tried first on two different bots (Clerk — `llama3.1:8b-instruct`, and Diver — `qwen2.5:7b-instruct`). Both hallucinated tool use in plain text ("I will use the Write tool...") instead of emitting a real tool call, so neither exercised the broker. Per the brief's fallback clause, testing moved to the least-important non-command-tier worker bot on a real Claude model (Stacks). Two prior attempts on Stacks also didn't hit the gate: a `Write` to the bot's own workspace directory and a `dir`/`ls`-style read-only shell command both auto-resolved without a card — this is expected: the driver's default `permissionMode` is `acceptEdits` (Claude Agent SDK auto-accepts in-workspace file edits, and the SDK itself pre-clears common read-only recon commands). A third prompt asking the bot to `Write` a file **outside its workspace** (`C:\Users\micha\Desktop\verify_test_outside.txt`) correctly required approval.

**Request sent:**
```
POST /api/bots/ebd24a31-b6cc-4dd7-96f8-6418fa43f4c4/messages
{"text":"Use your write tool to write a file at C:\\Users\\micha\\Desktop\\verify_test_outside.txt containing the text hello. This is outside your workspace directory, go ahead and try it."}
```

**Event excerpt** (`C:/Users/micha/.openmausbot/events/a3ee9741-93f9-4db2-9e52-05f0da776582.ndjson`):
```
{"type":"item.started","itemType":"tool","itemId":"toolu_01DENW8n3XEk5HRFP1FRq8Re","title":"Write", ...}
{"type":"request.opened","requestId":"c045fd9d-2acd-438f-863b-4c4d918763f8","requestType":"permission","tool":"Write","summary":"{\"file_path\":\"C:\\\\Users\\\\micha\\\\Desktop\\\\verify_test_outside.txt\",\"content\":\"hello\"}"}
```
A real approval card appeared (`request.opened`, `requestType:"permission"`) — **not** a silent deny. This is the pass signal.

**Denied via API** (no destructive action approved):
```
POST /api/bots/ebd24a31-b6cc-4dd7-96f8-6418fa43f4c4/respond
{"requestId":"c045fd9d-2acd-438f-863b-4c4d918763f8","behavior":"deny","message":"denied: automated broker verification test"}
→ {"ok":true,"outcome":"rejected"}
```
Event log confirms clean round-trip:
```
{"type":"request.resolved","requestId":"c045fd9d-2acd-438f-863b-4c4d918763f8","behavior":"deny","source":"user"}
{"type":"item.completed","itemType":"tool","itemId":"toolu_01DENW8n3XEk5HRFP1FRq8Re","ok":false}
{"type":"turn.completed","ok":true,"stopReason":"end_turn", ...}
```
The bot's own text acknowledged the denial correctly ("The write was **denied**..."). **Test A: PASS.**

## 6. Runtime Test B — pipe-race regression (back-to-back turns)

Two turns fired on Stacks, second POSTed immediately after the first's `turn.completed`:

```
Turn 1: POST .../messages {"text":"Say ready-1 and stop."}  → turn.completed ok:true (3s)
Turn 2: POST .../messages {"text":"Say ready-2 and stop."}  → turn.completed ok:true (immediately after)
```
`grep -in "EADDRINUSE\|broker unavailable\|broker could not start"` against the thread's full event file for the window covering both turns: **zero matches**. Each turn gets its own broker (a new `_brokerSeq` value), no pipe collision. **Test B: PASS.**

## 7. Log scan (since 2026-08-25)

Two independent sources scanned: the on-disk event NDJSON files (`C:/Users/micha/.openmausbot/events/*.ndjson`, all 6 files present, oldest content from 2026-08-26T12:40Z) and the harness process log (`C:/Users/micha/AppData/Roaming/openmausbot/logs/server.log`, covering server (re)starts back to 2026-08-26T16:31Z — nothing on disk predates 08-26, so the requested 08-25 window is empty by construction).

**One historical occurrence found**, entirely **pre-patch**:

`server.log` line 19:
```
[2026-08-26T18:02:57.355Z] [err] permission broker unavailable on \\.\pipe\openmausbot-perm-35712-081c1c6e: listen EADDRINUSE: address already in use \\.\pipe\openmausbot-perm-35712-081c1c6e
```
This is on server pid **35712** (forked 16:31:10Z, before the patch files were written), and the pipe name has **no** `_brokerSeq` suffix — the exact pre-patch naming format. Timestamp converts to 14:02:57 local (EDT, UTC-4); the patched source files were written to disk at 14:37-14:38 local (18:37-18:38 UTC) — i.e. this EADDRINUSE happened ~35 minutes *before* the patch was applied, consistent with it being the incident that motivated the fix rather than evidence of an unfixed bug.

Same story corroborated in the event NDJSON for thread `081c75b9-...` (18:07:14Z–18:10:24Z, i.e. 14:07–14:10 local, also pre-patch): three consecutive action-type tool calls (`Bash`, `Glob`, `Write`) failed silently (`ok:false`, no `request.opened`, no `turn.failed`) while the bot's own text narrated "permission broker unavailable" — exactly the documented pre-patch failure mode (dead broker → auto-deny with no card). A `Write` two minutes later in the same thread succeeded once the stale broker had torn down ("that outage was intermittent" — bot's own words), which is the intermittent EADDRINUSE race, not a separate bug.

**After the patch (18:38 UTC / 14:38 local onward):** `server.log` shows three subsequent server forks (pid 35160 at 20:35:30Z, pid 16836 at 21:13:59Z — the current live process, plus renderer-only Electron restarts around 2026-08-27T05:37-05:38Z that did not re-fork the server child) and **zero** further `[err]` lines of any kind. Grepping every event NDJSON file for `EADDRINUSE|broker unavailable|broker could not start` returns matches only inside the pre-patch window above — **zero post-patch occurrences**, including through the two fresh turns generated by this verification run.

## 8. Verdict per patch

| # | Patch | Verdict | Basis |
|---|-------|---------|-------|
| 1 | procs.js monotonic pipe counter | **VERIFIED-RUNTIME** | Static ✓, syntax ✓, code coherent ✓. Historical `server.log` shows the exact pre-patch failure (EADDRINUSE, unsuffixed pipe name) 35 min before the patch landed; zero recurrences across 3 server restarts and ~15 hours of live traffic since, including this run's own back-to-back-turn stress test (Test B). |
| 2a | claude.js broker-never-came-up detection | **VERIFIED-STATIC-ONLY** | Static ✓, syntax ✓, code coherent ✓ (`server.on("error")` wiring confirmed by reading the source). Not runtime-exercised: no broker listen failure occurred post-patch to trigger this path (expected, since patch 1 removed the collision that used to cause it — nothing left to catch). |
| 2b | claude.js onBrokerError → turn.failed | **VERIFIED-STATIC-ONLY** | Same basis as 2a — call site coherent, but no live `turn.failed`/broker-error event was observed post-patch because the triggering condition (a broker that fails to listen) hasn't recurred. |
| 3a (brief #4) | index.js ask_bot unattended:false | **VERIFIED-STATIC-ONLY** | Static ✓, syntax ✓, code coherent ✓, matches docs exactly. Not runtime-exercised in this pass — the brief's mandated Test A/B target the broker/pipe path directly and were satisfied via a direct human-initiated message rather than an `ask_bot` call; no live bot-to-bot `ask_bot` delegation was run against the patched line. |
| 3b (brief #5) | index.js ask_bot text-reply requirement | **VERIFIED-STATIC-ONLY** | Same basis as 3a — coherent on inspection, not exercised by a live `ask_bot` call in this pass. |

**Overall: 5/5 statically and syntactically verified, coherent with the running build, no drift or defects found. Patch 1 additionally carries direct runtime + historical-log confirmation. Patches 2a/2b/3a/3b are code-coherent and consistent with a build that has produced zero related errors since the patch was applied, but were not directly exercised at runtime in this pass because their trigger conditions (a broker failing to start; a bot-to-bot ask_bot call) didn't occur/weren't run.**

## 9. Follow-ups (recommended, not applied — no source was modified)

1. **Runtime-exercise 3a/3b**: have one worker bot `ask_bot` another (e.g. Stacks → Clerk) and confirm the target's action-type tool call raises a normal `request.opened` card rather than resolving via `unattended-block`/`no-grant` silently, and that a tool-failure case still produces `assistant_text` at `commsDepth > 0`.
2. **Runtime-exercise 2a/2b**: hard to do safely without deliberately breaking pipe availability (e.g. holding a same-named pipe open). Low priority given patch 1 already prevents the trigger condition; consider only if another broker-adjacent bug surfaces.
3. Local `ollama::` models (llama3.1:8b, qwen2.5:7b) on the claude engine wrapper are not reliable for future broker/tool-call tests — they narrate tool use in plain text instead of invoking real tool calls. Future verification passes should go straight to a Claude-model worker bot rather than spending a round-trip on the ollama path first.
4. Test artifacts left in place (harmless, inside bot sandboxes, not cleaned up since deletion wasn't requested and workspace files may be of interest): `verify_test.txt` in Clerk's and Diver's workspace dirs (from the two failed ollama attempts) and in Stacks' workspace dir (from the first successful in-workspace write). No file was written outside any bot's workspace — the one write attempted outside a workspace (Desktop) was denied as intended.

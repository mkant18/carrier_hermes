# OpenMausBot — Carrier Fleet Patches

**Branch:** `carrier_openmausbot`  
**Status:** Applied to installed OMB source (Option B — patch + re-apply script)  
**Long-term plan:** Convert to Option C (fork + build) once the patch set stabilises.

---

## Re-applying after an OMB update

```bash
python3 scripts/patch_omb_source.py
```

Then restart OpenMausBot (the harness server on port 8799, not just the Electron UI).

To verify without modifying:

```bash
python3 scripts/patch_omb_source.py --check
# exit 0 = all applied, exit 1 = needs patching, exit 2 = upstream changed
```

---

## Patch 1 — Windows Named Pipe Race (`procs.js`)

**Root cause:** On Windows, named pipe broker sockets live in a global
namespace and `unlinkSync()` is a no-op on them (it throws and is silently
caught). When a bot starts a new turn before the previous session's broker
has fully torn down, `server.listen()` gets `EADDRINUSE`. The error was
previously swallowed into `console.error`. The permission-proxy child
connected but the server never answered → the proxy's `conn.on("close")`
fired → `dead()` ran → every pending approval resolved as `deny` with the
message `"permission broker unavailable — skip this action"`. No card
appeared in the UI.

**Fix:** A module-level monotonic counter (`_brokerSeq`) appended to the
pipe name makes each new broker globally unique within the process lifetime,
so no two brokers ever share a name at the same time.

**File:** `resources/server/server/procs.js` — `brokerSocketPath()`

---

## Patch 2 — Broker Error Surfaces as Hard Turn Failure (`claude.js`)

**Root cause (secondary):** Even with Patch 1, if the broker fails to
listen for any reason the turn continued running with a dead broker, all
permissions silently denied, and no indication to the user.

**Fix (2a):** `server.on("error")` now calls `opts.onBrokerError?.(error)`.

**Fix (2b):** The `createPermissionBroker` call site wires `onBrokerError`
to immediately settle the turn with a visible `turn.failed` event and the
message: `"Permission broker could not start: <reason>. Restart OpenMausBot
to fix this."` — the user sees an error bubble instead of silent wrong
behaviour.

**File:** `resources/server/server/drivers/claude.js` — `createPermissionBroker()` + call site

---

## Patch 3a — `ask_bot` Unattended Flag Propagation (`index.js`)

**Root cause:** `askBotAndWait()` passed `unattended: isUnattended(fromBotId)`
to `startTurn`. This transitively marked the *target* bot's turn as
unattended whenever the *calling* bot had been marked unattended — which
any bot running a long session could be. In `auto-approve.ts:90-104`,
unattended mode returns `approve: null, source: "unattended-block"` for
**all** action-type tool calls, even "always-allow" ones. Result: Marshal,
invoked via `ask_bot` from Helm, couldn't write a single Kanban card.

**Fix:** Hard-code `unattended: false` for `ask_bot` turns. Only webhook
triggers (`automationSource: "webhook"`) should run truly unattended.

**File:** `resources/server/server/index.js` — `askBotAndWait()`

---

## Patch 3b — `ask_bot` Requires Text Reply (`index.js`)

**Root cause:** Bots at `commsDepth > 0` that hit tool failures (broker
dead, permissions denied) would finish their turn with only tool-call
results and no `assistant_text` event. `askBotAndWait()` then resolved with
the fallback string `"(the bot finished without a text reply)"` — opaque
and not surfaced visibly in Helm's chat. The calling bot appeared to send
three identical silent messages.

**Fix:** When `commsDepth > 0`, append to the bot's system prompt:
> "IMPORTANT: You have been invoked via ask_bot by another bot on behalf of
> the user. You MUST produce a plain-text reply — even if your tool calls
> fail or are denied, acknowledge what you attempted and what happened.
> Never finish a turn with tool results only and no explanatory text."

**File:** `resources/server/server/index.js` — `startTurn()` system prompt assembly

---

## Patch 6 — Composio Approval-Gate Bypass (`drivers/claude.js` + `connector-proxy.js`)

**Status: NOT resolved.** Both halves of this patch are applied, on disk, and
idempotent — but live testing (below) proved 6a does not close the approval
gap it was written to close. Composio calls still execute with zero approval
cards after this patch, identically to before it. The safety interlock is
still the ollama-only model pinning on Yeoman/Inbox, not this patch. See
"Verified NOT effective at runtime" below before relying on this patch for
anything.

**Symptom (found in Phase 2A pilot):** With `Yeoman.autoApprove === false` and
no `alwaysAllow` grant, every `mcp__composio__*` tool call — including four
rounds of `COMPOSIO_MULTI_EXECUTE_TOOL` — executed with **zero** approval
cards. `auto-approve.ts`'s `autoVerdict()` should have returned `{approve:
null, source: "no-grant"}` (ask a human) but was never consulted at all.

**Root cause:** `drivers/claude.js` did `allowed.push("mcp__composio")` and
passed it in `--allowedTools` to the Claude Code CLI. This blanket-allowlists
the **entire** `mcp__composio` MCP server at the CLI's own permission layer —
every tool it exposes, read or write, is pre-approved before OMB's own
`autoVerdict()`/approval-card pipeline ever gets a say. Because every actual
Composio action (search, send, delete, ...) is funneled through the same
generic `COMPOSIO_MULTI_EXECUTE_TOOL` wrapper name, this bypassed
human-in-the-loop approval for write-shaped actions like `GMAIL_SEND_EMAIL`
just as completely as for a read-only search — `autoApprove:false` was
silently a no-op for Composio.

**Fix attempted (6a, intended as the primary gate):** `drivers/claude.js` no
longer pushes `mcp__composio` onto `allowed`. The intent was for Composio
calls to fall through to `--permission-prompt-tool mcp__ogb__approve`, the
same permission-broker path used for every other gated tool, mirroring the
comment already in this file for host-controlling `computer` tools via the
`controlsHost` branch a few lines above ("Host tools always route through
OpenMausBot's permission broker").

**⚠️ Verified NOT effective at runtime.** Live testing (Phase 2B build,
2026-08-27) found that removing `mcp__composio` from `allowed` does **not**
cause `mcp__composio__*` calls to card at the broker. Tested twice against
the patched, restarted live install:
- Resumed session (thread `3196c41c...`, session `3fed3204...`, inherited
  from before this patch existed): `COMPOSIO_SEARCH_TOOLS` and
  `COMPOSIO_MULTI_EXECUTE_TOOL` both executed `ok:true` with zero
  `request.opened` events.
- **Fresh session with no resume cursor** (new task, thread
  `e611e9a8-2db4-4811-ba26-92044fc20228`, brand-new session
  `b686ac59-a2e1-444b-9d25-aa10de388959` — ruling out session-resume as the
  cause): same result. `ToolSearch`, `COMPOSIO_SEARCH_TOOLS`,
  `COMPOSIO_GET_TOOL_SCHEMAS`, and `COMPOSIO_MULTI_EXECUTE_TOOL` all executed
  `ok:true`, zero `request.opened` events, `turn.completed ok:true`.

This directly contradicts this file's own comment at `claude.js:490`
("a headless acceptEdits run silently denies anything unlisted") — the
observed behavior was neither denial nor a prompt; the call simply
succeeded, identically to pre-patch behavior. The working conclusion is that
omitting a tool from `--allowedTools` does not, by itself, route an MCP tool
call through `--permission-prompt-tool` on the Claude Code CLI version this
install uses — at least not for `mcp__composio`. Whether the parallel
`controlsHost`/`mcp__computer` case actually works as commented is
**untested**: no bot in `bots.json` currently has `computer:"local"`
(host-control scope; only Helm exists, with `computer:"vm"`, a different
code path), and one was not created to test this given the live-account
blast radius. Until that parity question is resolved, do not assume the
`computer` comment is correct either.

**Practical consequence: patch 6a alone does not close the approval gap.**
`autoVerdict()`/the approval-card UI is still never consulted for Composio
calls after this patch. The only thing currently preventing an ungated
Composio write from Yeoman or Inbox remains what Phase 2A already
identified: both bots being pinned to `ollama::llama3.1:8b-instruct-q4_K_M`,
which cannot reliably drive MCP tool calls at all. **The model assignment is
still the actual safety interlock, not the approval system**, exactly as
Phase 2A warned. Do not move Yeoman or Inbox onto a stronger model until this
is genuinely fixed.

**Fix (6b, defense-in-depth logging, not a gate):** `connector-proxy.js` now
classifies `COMPOSIO_EXECUTE_TOOL` / `COMPOSIO_MULTI_EXECUTE_TOOL` calls by
extracting the underlying action slug(s) from the call arguments and matching
against a read-only pattern (`^(SEARCH|GET|LIST|FETCH|FIND|READ|RETRIEVE|
QUERY|CHECK)_` plus the `COMPOSIO_SEARCH_TOOLS` / `COMPOSIO_GET_TOOL_SCHEMAS`
/ `COMPOSIO_WAIT_FOR_CONNECTIONS` meta tools). Everything else — `SEND`,
`CREATE`, `DELETE`, `UPDATE`, etc., or anything unrecognized — logs as
write-shaped to stderr (fail-open: an unresolved slug also logs as write).
This **never blocks or rewrites** a call; it exists purely so a future audit
of the connector-proxy logs can see write actions distinctly. **6a is the
actual gate** — every Composio call cards at the broker again regardless of
classification; that is the deliberate, acceptable-for-now safe default (a
read-only search still requires a click, same as a write).

**6b could not be runtime-verified either, for a different reason:**
`connector-proxy.js` runs as a grandchild process (spawned by the Claude Code
CLI, which is spawned by the OMB driver), and its stderr is not captured in
`server.log` or any other log this session could find — confirmed by
grepping `server.log` for the classifier's own log prefix
(`carrier_openmausbot patch 6`) after the live test above ran; zero matches.
Static/syntax verification only (`node --check` passes; logic reviewed by
inspection). Per this project's own precedent (Phase 1B labeled 2a/2b
`VERIFIED-STATIC-ONLY` for the same reason — no observable trigger), 6b's
status is **VERIFIED-STATIC-ONLY, not runtime-exercised.**

**Given 6a does not work, 6b's design (logging-only, layered *behind* the
broker) is now mis-ordered.** The classifier's own comment correctly says
"6a is the actual gate" — but 6a is not currently gating anything, so today
6b's write-vs-read distinction is invisible everywhere except a log stream
nothing reads. The likely correct fix is Phase 2A's option (b): have
`connector-proxy.js` itself raise the approval card for write-shaped actions
(the same `/api/internal/connectors/request`-style mechanism it already uses
for `MANAGE_CONNECTIONS`) rather than relying on the CLI-level broker for
Composio at all. That is a design decision beyond this patch's scope — this
patch's classifier only logs; it does not attempt to gate, per the original
brief's explicit instruction not to build a bypass/gate of its own here.

**Billing-guard compatibility:** this patch does not touch `bots.json`'s
`composio` field, its opt-out polarity, or the mount condition in
`composio.js` (`mcpIntegration` is invoked from the driver only when
`turn.integrations.composio` is set, which in turn traces back to
`bot.composio !== false` — unchanged by this patch). The billing-guard
scripts (`billing-audit.py`, `omg_billing_audit.py`, `billing_guard.py`)
remain untouched and continue to read that same field.

**Files:**
`resources/server/server/drivers/claude.js` — turn integration → `allowed` assembly
`resources/server/server/connector-proxy.js` — MCP `tools/call` handler

**Related:** `scripts/omb_composio_health.py` — standalone check (not part of
the billing guard) that flags any bot missing an explicit `composio` field,
i.e. the Moss-style silent-enablement hazard from Phase 2A.

---

## Option C Migration Notes

When ready to convert to a proper fork:

1. `git clone https://github.com/milind-soni/OpenMausBot` into a subdir or sibling repo
2. Port each patch from this doc to the TypeScript source files:
   - `server/procs.ts` → Patch 1
   - `server/drivers/claude.ts` (if exists as TS) → Patches 2a, 2b
   - `server/index.ts` → Patches 3a, 3b
3. Build: `pnpm install && pnpm dev:server` to verify, then `pnpm build` for Electron
4. Replace the installed app with the custom build
5. Update `scripts/patch_omb_source.py` to point at the fork's source tree instead

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

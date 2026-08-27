# OpenMausBot — Carrier Fleet Patches

**Branch:** `carrier_openmausbot`  
**Status:** Applied to installed OMB source (Option B — patch + re-apply script)  
**Long-term plan:** Convert to Option C (fork + build) once the patch set stabilises.

---

## ⚠️ UNRESOLVED (2026-08-27, discovered during Patch 8): the patched directory may not be what OMB executes

While live-testing Patch 8, direct process inspection (`Win32_Process.CommandLine`
for the `connector-proxy.js` child OMB actually spawned, plus reading
`resources/server/proxy-paths.js`'s own path-resolution logic) showed the
running app resolves `connector-proxy.js` — and very likely `index.js` and
every other server module — from **`resources/server/*.js`** (one level up
from the directory this file and `scripts/patch_omb_source.py` target),
**not** `resources/server/server/*.js`. The outer files are esbuild output
(`// server/index.ts` / `// server/connector-proxy.ts` header comments, `var`
instead of `const`, no comments) — compiled from a TypeScript source tree
that is not present in this repo or known to this project's docs.

The outer `connector-proxy.js` contains logic equivalent to Patch 7a (not
Patch 8: no argument digest, no default-gate-unknown, no recursive
extractor, old read-verb set). The outer `index.js` contains the
`/api/internal/connectors/approval` route and `pendingComposioApprovals`/
`resolveComposioApproval` (Patch 7b/7c/7d/7e/7g-equivalent), but **not**
Patch 1 (`_brokerSeq`) or Patch 2a/2b (`onBrokerError`). A live spawn's
`--allowedTools` still includes `mcp__composio` — Patch 6a's fix is not in
effect on whatever produced this bundle. Nobody on this project (including
this file, prior build reports, and the Opus review) appears to have known
about the outer directory before now — it is unclear when it appeared or
what produced it. **Do not hand-patch the outer files** — they are compiled
output with no known source and no coverage from `patch_omb_source.py`.
Every "live-verified" claim in this file for Patches 1–7 should be treated
as unconfirmed against the actual execution path until this is resolved.
See `reports/phase2b_patch8_fix.md` ("BLOCKED" section) for the full
evidence trail and next steps.

**Also discovered:** `taskkill /IM OpenMausBot.exe /F` does not reap a
bot's per-thread CLI child process tree (`claude.exe` + its
`connector-proxy.js`/`agents-proxy.js`/`permission-proxy.js` children) —
they are not in the same Windows job object and survive the app "restart,"
continuing to serve that bot's turns on whatever code was loaded when they
started. After restarting OMB, also kill any lingering per-bot
`claude.exe`/`codex` CLI processes (`Get-CimInstance Win32_Process | Where
CommandLine -match '<bot name or resume id>'`, then
`taskkill /PID <pid> /T /F`) before relying on a bot's next turn to reflect
newly-applied patches.

---

## Re-applying after an OMB update

```bash
python3 scripts/patch_omb_source.py
```

Then restart OpenMausBot (the harness server on port 8799, not just the Electron UI).

To verify without modifying:

```bash
python3 scripts/patch_omb_source.py --check
# exit 0 = all applied, exit 1 = needs patching, exit 2 = upstream changed/mismatch (fail-closed, nothing written)
```

For a stronger check that the live files actually contain each patch's
expected text (not just that a marker string is present somewhere):

```bash
python3 scripts/patch_omb_source.py --verify-content
# exit 0 = clean, exit 1 = drift found
```

If `--check` or a real run ever reports `MISMATCH`/exits 2, **nothing is
written** — see the printed banner for the immediate fleet-wide mitigation
(disable `composio` on every bot via `PATCH /api/bots/:id`) before
investigating the broken anchor.

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

**Status: NOT resolved by this patch. See [Patch 8](#patch-8--opus-review-remediation-connector-proxyjs--indexjs)
for the gate that is actually live today.** Both halves of this patch are
applied, on disk, and idempotent — but live testing (below) proved 6a does
not close the approval gap it was written to close. Composio calls still
execute with zero approval cards after this patch alone, identically to
before it. See "Verified NOT effective at runtime" below before relying on
this patch for anything. Patch 6b's classifier (logging only, never a gate)
was superseded wholesale first by Patch 7a and then by Patch 8 directly (8's
`connector-proxy.js` entry now anchors straight on the pristine file, folding
in what 6b/7a used to do in two steps — see Patch 8's "pristine-install apply
chain" note); `scripts/patch_omb_source.py`'s Patch 6b check entry was
deleted for this reason — see git history if you need the old text.

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
This **never blocks or rewrites** a call; it was designed purely so a future
audit of the connector-proxy logs could see write actions distinctly, on the
assumption that 6a was the actual gate. **That assumption is false — see
below.** 6a does not gate anything, so today this log is the only visibility
into write-shaped Composio calls that exists at all, not a backstop behind a
working gate.

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

**Given 6a does not work, 6b's design (logging-only, originally intended to
sit *behind* the broker) is now mis-ordered.** 6a is not currently gating
anything, so today 6b's write-vs-read distinction is invisible everywhere
except a log stream nothing reads. The likely correct fix is Phase 2A's
option (b): have
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

**2026-08-27 update:** Patch 8 (below) closed the approval gap this section
describes — `connector-proxy.js` itself now raises a real approval card for
write-shaped/unknown Composio calls, independent of the CLI broker this
patch's 6a half tried and failed to use. The ollama-only model pinning on
Yeoman/Inbox is no longer the only thing standing between those bots and an
ungated Composio write, but it is still recommended as defense-in-depth —
see Patch 8's threat-model note.

---

## Patch 7 — Composio Write-Gate at the Proxy (`connector-proxy.js` + `index.js`)

**Status: superseded by Patch 8 (below), same day.** This section is kept for
the historical design record; the classifier/gate code it describes was
functionally replaced by Patch 8's `connector-proxy.js` entry, and every
`index.js` route it added (7b–7g) is unchanged by Patch 8 except 7c.

**Design:** since Patch 6a's CLI-broker approach was live-verified not to
gate anything, Patch 7 moved the gate to `connector-proxy.js` itself — the
only layer that sees the underlying Composio action slug before it is
relayed upstream. Write-shaped or unresolved `COMPOSIO_(MULTI_)EXECUTE_TOOL`
calls are intercepted; the proxy calls a new harness endpoint
(`POST /api/internal/connectors/approval`, patch 7c) which raises a real
options card in the owning thread via `bus.publish` (patch 7g, reusing the
same `request.opened`/`request.resolved` fold every other permission card
goes through) and blocks the relay until the card is answered — allow, deny,
or a 10-minute server-side timeout (`OMB_COMPOSIO_APPROVAL_TIMEOUT_MS`).
Resolution reuses the existing `/api/bots/:id/respond` and
`/api/threads/:id/respond` routes (patches 7d/7e intercept them before the
provider adapter, mirroring `resolvePeerComms`), and an interrupted turn
cancels any open Composio approval immediately (patch 7f) instead of leaving
it to time out.

**Live verification (2026-08-27):** WRITE test — a `GMAIL_SEND_EMAIL` call
raised a real `request.opened`/`request.resolved(deny)` pair in the thread's
event log and the send never executed. READ test — a `COMPOSIO_SEARCH_NEWS`
call relayed with zero `request.opened` events. See
`reports/phase2b_patch7_build.md` for the full event-log proof.

**What an Opus security review (`reports/phase2b_opus_review.md`) found
wrong with this design**, all addressed in Patch 8:
1. The patch script itself could not apply to a pristine OMB install (two
   broken anchors: 7a depended on the retired Patch 6b, and 7g's anchor was
   a substring of 7b's own inserted text) — and failed open (applied
   nothing, silently) when it broke. **Merge-blocker**, fixed in Patch 8.
2. `extractActionSlugs` stopped at the first match instead of scanning
   exhaustively, letting a write slug hide in an unscanned/deeper key.
3. The gate matched exactly two tool names (`COMPOSIO_EXECUTE_TOOL`,
   `COMPOSIO_MULTI_EXECUTE_TOOL`) and relayed everything else — including a
   renamed or newly-added upstream executor — untouched.
4. The read-only verb regex included `QUERY`/`FIND`/`CHECK`, any of which
   can front an arbitrary write (SQL, find-and-replace) and relayed ungated.
5. The approval card showed only the action slug, never the arguments — the
   human approving `GMAIL_SEND_EMAIL` could not see the recipient or body.

## Patch 8 — Opus Review Remediation (`connector-proxy.js` + `index.js` + `scripts/patch_omb_source.py`)

Full remediation of the Opus REQUEST-CHANGES review of Patches 6 and 7
(`reports/phase2b_opus_review.md`; brief: `briefs/phase2b_sonnet_patch8_fix.md`;
outcome: `reports/phase2b_patch8_fix.md`). Findings are numbered as in the
brief (blocking 1–6, non-blocking 7–9/11); the Opus report's own numbering is
noted in parens where it differs.

**1 (opus #1, merge-blocker) — pristine-install apply chain.**
`scripts/patch_omb_source.py`'s Patch 7a entry is deleted and folded directly
into a new Patch 8 `connector-proxy.js` entry, anchored on the file exactly
as OMB ships it (verified against `backups/connector-proxy.js.pre-patch6`) —
no dependency on the retired Patch 6b. The apply engine was rewritten from
check-all-then-apply to apply-as-you-go per file: same-file entries now
apply against each other's in-memory output in list order, so a later entry
(like 7g) may legitimately depend on an earlier one (7b) having already run
in the same pass — this is declared in a comment above `PATCHES` rather than
left as an implicit ordering accident. Failure is fail-closed by
construction (a mismatch on any entry aborts before anything is written) and
now LOUD: a banner on stderr plus the exact PowerShell remediation command to
disable `composio` on every bot via `PATCH /api/bots/:id`. Added
`--verify-content`, a stronger check that confirms the *live* file actually
contains each patch's expected text (accounting for later patches that
legitimately layer on top of an earlier one's output) rather than only that
its marker string is present somewhere in the file.
Verified: reconstructed-pristine baseline (pre-patch6 backups for
`connector-proxy.js`/`claude.js`, `index.js`/`procs.js` reverse-reconstructed
from the live tree) applies with zero `MISMATCH` (11 `NEEDED` + 2 already
present in the `claude.js` backup), `node --check` clean on all four files,
`--check` and `--verify-content` both clean afterward. A deliberately broken
anchor was also tested end-to-end: exit 2, banner printed, **zero bytes
written to any file** (checksums identical before/after) even though other
files in that run had cleanly-applicable patches pending.

**2 (opus #4) — extractor decoy.** `extractActionSlugs` now recurses
arbitrarily nested objects/arrays for the 6 slug key names at any depth
(`collectSlugsDeep`), and the `JSON.stringify` token-scan fallback runs
**always** and is unioned with the key-based result — additive-only, so it
can only add candidate write-shaped slugs, never suppress one the key walk
already found. Unit-tested (`node -e`-style harness against the deployed
`connector-proxy.js`) with the exact opus decoy payload
(`{"tool":"COMPOSIO_SEARCH_TOOLS","tool_calls":[{"tool_slug":"GMAIL_SEND_EMAIL"}]}`),
a 3-level-nested slug, a slug under a completely unlisted key (relies on the
token-scan fallback alone), a mixed read+write batch, and lowercase/mixed-case
tricks — all classify write/gated.

**3 (opus #3) — two-name allowlist.** Inverted to default-gate-unknown:
`KNOWN_SAFE_TOOL_SUFFIX_RE` matches only `SEARCH_TOOLS`, `GET_TOOL_SCHEMAS`,
`WAIT_FOR_CONNECTIONS`, `MANAGE_CONNECTIONS` by suffix (same style as the
pre-existing `MANAGE_CONNECTIONS$`/`WAIT_FOR_CONNECTIONS$` interception, so a
vendor-prefix rename still matches); every other `tools/call` name — not
just ones matching `COMPOSIO_(MULTI_)EXECUTE_TOOL` — goes through slug
classification, and an unresolved/empty slug set is write-shaped by
construction. A renamed or newly-added executor now defaults to carded.

**4 (opus #5) — read-regex semantics.** `QUERY`, `FIND`, and `CHECK` removed
from the read-only verb set (`READ_ONLY_ACTION_RE` is now
`SEARCH|GET|LIST|FETCH|READ|RETRIEVE` only). A new `WRITE_VERB_TOKEN_RE`
gates any slug containing a write-verb token *anywhere* (`DELETE`, `DROP`,
`SEND`, `CREATE`, `UPDATE`, `EXECUTE`, `RUN`, `WRITE`, `REMOVE`, and others),
overriding a read-prefix match — e.g. `SEARCH_AND_DELETE_FILES` now gates.

**5 (opus #6) — information-free card.** The approval summary now includes
a bounded (~400 char), unredacted digest of the call arguments
(`summarizeArgs`, `JSON.stringify` truncated with an ellipsis) alongside the
slug list — the human approving can see the recipient/body/SQL/etc. This
also re-arms `auto-approve.js`'s `DESTRUCTIVE`/`SENSITIVE` regex guards,
which previously could never match against a slug-only summary. Arguments
are never written to the `console.error` classification log — only the card
summary carries them, per the brief's "keep full args out of logs" rule.

**6 (opus #10) — missing owner check.** `POST /api/internal/connectors/approval`
now rejects with 409 when `!composio.configured(cfg) || owner.bot.composio === false`,
matching its sibling `/api/internal/connectors/request` route exactly.

**7 (opus #7) — timeout coupling.** The proxy's own abort timeout now derives
from `OMB_COMPOSIO_APPROVAL_TIMEOUT_MS` (the same env var the harness reads,
patch 7b) plus a 60s margin, instead of a hardcoded 11 minutes — raising the
harness timeout above 11 minutes no longer silently inverts which side times
out first. **Still open, documented rather than fixed:** if the CLI's own MCP
tool-call timeout fires before a human answers, a subsequent "Allow" still
relays the action to Composio with no return path to the turn and no
transcript record. Consider recording the relay outcome as an activity
message regardless of whether the CLI is still listening, in a future patch.

**8 (opus #8) — self-approval threat model.** Written down explicitly, not
fixed (pre-existing, equivalent for every native permission card):
`resolveComposioApproval` matches a global map with no caller-ownership
check, and `/api/bots/:id/respond` / `/api/threads/:id/respond` are
loopback-only with no bearer token. **A bot holding any standing shell/command
grant can raise a Composio write and approve its own card from a parallel
tool call in the same turn** — it can discover its own `requestId` via
`GET /api/threads/:id/messages` (also unauthenticated) and `curl` the respond
route itself. **Operational rule: never co-grant shell/command tools with
`composio:true` on the same bot, and keep `autoApprove:false` on every
Composio-enabled bot.** Fixing this for real means binding the respond
routes to a caller identity — out of scope here.

**9 (opus #9) — `alwaysAllow`/scope mismatch.** Cheap part fixed: the 7c
route's `autoVerdict` call now passes `scope: "composio"`, matching the
`request.opened` fold's own recompute (`index.js` ~line 762) so both sides
compute the same `approvalKey`. **Left documented, not fixed:** any
`alwaysAllow` grant that does get created is still keyed on the wrapper tool
string (`Composio: COMPOSIO_MULTI_EXECUTE_TOOL`, identical for every
Composio action) rather than the action slug, so it would necessarily be a
blanket grant over every Composio write — this is currently inert in
practice because the fold sets `allowKey: undefined` for any scoped card
(no "Always allow" button is shown), but a hand-set grant would still match
at the route level. Fixing this means keying grants on the action slug
(`Composio:GMAIL_SEND_EMAIL`), a larger change than this patch's scope.

**11 (opus #11) — housekeeping.** `write()` now opens with
`newline=""`, so applying no longer flips the target file's line endings
(the first re-apply after this patch normalizes CRLF→LF once; subsequent
applies are silent). Documented: `connector-proxy.js` runs as a grandchild
process whose stderr is not captured anywhere (`server.log` or otherwise) —
the `appendDecision` rows written to `DATA_DIR`, not the
`[carrier_openmausbot patch 8]` console log line, are the real audit trail.

**Files:**
`resources/server/server/connector-proxy.js` — classifier + gate + card summary
`resources/server/server/index.js` — approval route, owner check, `scope` fix
`scripts/patch_omb_source.py` — apply engine, `--verify-content`, banner, `newline=""`

**Verification:** see `reports/phase2b_patch8_fix.md` for the full pristine-apply
proof, decoy-test output, live re-tests (WRITE-deny with arguments visible on
the card, READ pass-through, decision-tier check, billing-audit,
`omb_composio_health.py`), and commit SHA.

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

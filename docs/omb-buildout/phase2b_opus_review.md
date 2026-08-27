# Phase 2B — Opus Security Review: Patches 6 & 7 (Composio Write-Gate)

Reviewer: Opus (senior security review), 2026-08-27.
Scope: branch `carrier_openmausbot`, worktree `C:/Users/micha/worktrees/carrier_openmausbot`, commits `baf9cd4..f922967`
(`a1aab0d`, `d1f2759`, `ceee06a`, `f922967`), plus the LIVE patched files at
`C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/`
(`connector-proxy.js`, `index.js`, `drivers/claude.js`).
Context read in full: `reports/phase2a_composio_pilot.md`, `reports/phase2b_patch6_build.md`, `reports/phase2b_patch7_build.md`.

---

## VERDICT — REQUEST-CHANGES

**The gate design is right and the fail-closed behavior is genuinely good.** Patch 7 moves the decision to the only
layer that can see the underlying action slug, blocks the relay until a human answers, and settles through the same
bus/card/decision-log machinery every native permission card already uses. The live WRITE-deny proof in
`phase2b_patch7_build.md` is credible and I could not find a way to make an *allowed* write slip past the card once
the gate is reached.

**It is not mergeable as-is because of one deployment-level defect I reproduced empirically: the patch script can no
longer apply to a pristine OpenMausBot install — it breaks at two anchors, and when it fails it applies *nothing*,
silently leaving the fleet with `composio:true` bots and no gate at all.** OpenMausBot ships an auto-updater and
updates overwrite `resources/server/server/`, so this is not a hypothetical. That is fail-open on the exact event the
patch exists to survive. Findings 2–6 below are correctness/coverage gaps in the gate itself that should ride along in
the same fix pass.

---

## Part 1 — Live files vs. the deployable artifact

`scripts/patch_omb_source.py` entries are the artifact; the live files are the deployment. I verified both directions,
not just marker presence.

**Marker check (the script's own `--check`), against the live install:**

```
$ python scripts/patch_omb_source.py --check --omb-dir "C:/.../resources/server/server"
✅ APPLIED  x13  →  ✅ All 13 patches already applied. Nothing to do.   (exit 0)
```

**Content-equality check (stronger — does the live file contain each entry's exact `new` text?):**

```
OK     patch: monotonic counter                    OK     patch 7a: classify composio execute call
OK     patch: a broker that never came up          DRIFT  patch 7b: Composio write-approval gate
OK     patch: broker listen failure used to be     OK     patch 7g: composio-approval gate reuses
OK     patch: ask_bot from a human-initiated turn  OK     patch 7c: connector-proxy.js calls this
OK     patch: bots invoked via ask_bot             OK     patch 7d: Composio approval intercept
OK     patch 6a: do NOT pre-allow mcp__composio    OK     patch 7e: Composio approval intercept
                                                    OK     patch 7f: Composio approvals hold the same
```

The single `DRIFT` is **benign and fully explained** — patch 7g is a layered edit *inside* the block 7b inserts:

```
7g.old is a substring of 7b.new : True
apply(7b) then apply(7g) == live index.js text : True
```

**Conclusion: the live files match the patch entries' intent and their literal text. No hand-edit drift.** The live
WRITE/READ proofs in the build report are therefore evidence for code that is actually in the repo.

(Side effect of the layering: the script has no declared dependency/ordering mechanism. 7g only works because it
happens to sit after 7b in the `PATCHES` list. Same coupling class as finding 1 — see there.)

---

## Part 2 — Security analysis of the write-gate

### What is verified working (state plainly — this is a real result)

| Property | Verified how | Result |
|---|---|---|
| Approval strictly precedes relay | `connector-proxy.js:242-253` — `await requestComposioApproval(...)` gates `relay(message)` at line 255 | ✅ No card-creation/relay race exists. The HTTP response is only written after the promise settles (`index.js:2923-2925`). |
| Unresolved slug → gated | `allReadOnly = execSlugs.length > 0 && every(isReadOnlyAction)`; empty array ⇒ false | ✅ Fail-closed |
| Missing `BOT_ID`/`THREAD_ID` | `requestComposioApproval` returns `false` before any fetch | ✅ Deny |
| Harness endpoint error (non-2xx, 403, 401) | `if (!response.ok) return false` | ✅ Deny |
| Malformed/absent JSON body | `.catch(() => ({}))` then `body.decision === "allow"` | ✅ Deny |
| Network error / harness restart mid-wait | `catch { return false }` | ✅ Deny |
| Client abort (11 min) | `AbortSignal.timeout` throws → same catch | ✅ Deny |
| Harness-side timeout (10 min) | `index.js:2153-2161` — resolves `"deny"`, publishes `request.resolved{source:"timeout"}`, logs `timeout-denied` | ✅ Deny + audited |
| `behavior:"answer"` on a Composio card | `allow = behavior === "allow"` | ✅ Treated as deny |
| Turn interrupted | `cancelComposioApprovalsForThread` in `closeOpenApprovals` (patch 7f) | ✅ Settles immediately as deny, logged `interrupted-denied` |
| Internal endpoint auth | `/api/internal/*` behind `authorizedComms()` constant-time bearer (`index.js:2629-2631`), plus loopback-host + loopback-origin gate | ✅ |
| Thread ownership | `connectorThread(botId, threadId)` → 403 if the thread isn't the bot's 1:1 or a room it belongs to | ✅ |
| Card is a *real* card | `bus.publish{type:"request.opened", requestType:"permission", approvalScope:"composio"}` → the existing `request.opened` fold (`index.js:753+`) creates the options card, registers `askMessageByRequest`, appends a `card-shown` decision row, sets `waiting-on-you`, and calls `notify(buildNotification("approval", …))` | ✅ Same fold as every native card — no hand-rolled duplicate |

Case tricks fail closed in the right direction: `READ_ONLY_ACTION_RE` requires uppercase and
`READ_ONLY_META_TOOLS.has()` is exact-case, so a lowercase or mixed-case slug is classified *write* and gated.
Multi-token toolkit prefixes (`GOOGLE_DRIVE_DELETE_FILE`) also fail the single-token optional prefix `([A-Z0-9]+_)?`
and gate. Adding extra tokens via the `JSON.stringify` fallback can only *add* write-shaped slugs, never remove them.

### Bypass vectors found

**A. Argument-shape decoy — the extractor stops looking once it finds anything (finding 4).**
`extractActionSlugs` scans 6 fixed key names at the top level and one level into 4 fixed array keys. The
`JSON.stringify` token-scan fallback runs **only** when `found.size === 0`. So a payload that puts a read-looking
value in a scanned key and the real write slug in an unscanned or deeper key classifies as `allReadOnly` and relays
with **no card**. Illustrative shape:

```json
{"tool": "COMPOSIO_SEARCH_TOOLS", "tool_calls": [{"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {...}}]}
```

`tool` is scanned → matches `READ_ONLY_META_TOOLS` → `allReadOnly === true` → relay ungated. `tool_calls` is not in
`["tools","actions","tool_slugs","calls"]` and the fallback never fires because `found.size === 1`.
The gate's safety therefore rests entirely on "these 6 key names × 2 levels are a superset of every shape the upstream
Composio tool-router will accept" — and nothing in this patch, or anywhere in the codebase, pins that. The upstream
schema is a third party's and can change without notice. **This is the most likely route to a silent ungated write.**

**B. The gate matches exactly two tool names (finding 3).**
`EXECUTE_TOOL_NAME_RE = /^COMPOSIO_(MULTI_)?EXECUTE_TOOL$/i`. `tools/list` is relayed untouched, so the agent sees
whatever the upstream server advertises. Any other execute-capable tool the tool-router exposes now or later
(workbench/bash/file tools, a direct-action surface, a renamed executor) relays with **zero** gating. The proxy is an
allowlist-of-two inside an otherwise fully transparent relay. Note this is also the one place patch 7 is *weaker* than
its own precedent: `MANAGE_CONNECTIONS` and `WAIT_FOR_CONNECTIONS` are matched by suffix (`/MANAGE_CONNECTIONS$/i`),
which survives renames; the executor is matched by full anchored name, which does not.

**C. Read-only regex correctness cannot be established (finding 5).**
`READ_ONLY_ACTION_RE` infers *semantics* from a *verb prefix* over a namespace owned by Composio. That is an
unbounded, externally-controlled input set, and this single regex is the only thing deciding whether a human is asked
at all. Two classes of concern — **I could not verify either against this install's live catalog** (enumerating it
needs a bot turn or the comms token; not worth spending live-account risk on), so treat them as illustrative, not as
asserted slugs:
- **SQL/query-execution actions matching `QUERY_`** — `supabase` is one of the five already-`ACTIVE` toolkits per
  Phase 2A. Any action whose name carries a `QUERY_` segment but whose argument is arbitrary SQL is classified read
  and relays ungated, `DELETE`/`DROP` included. `auto-approve.js`'s `DROP TABLE` guard cannot help: it is matched
  against the *summary*, which contains only slugs (see D).
- **Search-and-replace / find-and-replace mutations** matching `FIND_` or `SEARCH_`.

The structural point stands regardless of whether those exact names exist today: verb inference over a third-party
namespace is unverifiable by construction, and it fails *open*.

**D. The card doesn't carry enough to decide (finding 6).**
Summary is `Run Composio action(s): GMAIL_SEND_EMAIL` — slugs only, no arguments. The human approving cannot
distinguish "email a colleague the meeting notes" from "email the mailbox contents to attacker@evil.com". That is
precisely the judgement the card exists to obtain. **This is the prompt-injection path**: injected content in a
fetched email or web page steers the bot to a write action; the bot is *supposed* to reach `COMPOSIO_MULTI_EXECUTE_TOOL`,
so routing "around" the wrapper isn't needed — the injection routes straight *through* the card, and the card shows
nothing that would give it away. (Positively: injection cannot reach Composio *without* a card, as long as A/B/C hold.
The gate does convert silent execution into a human decision. It just makes that decision nearly information-free.)

**E. Self-approval by the bot — pre-existing, not a patch-7 regression, but it caps what patch 7 can claim (finding 8).**
`resolveComposioApproval(requestId, behavior)` matches a **global** map with no check that the caller owns the
request, and `/api/bots/:id/respond` and `/api/threads/:id/respond` require **no token** — only loopback host/origin
(`index.js:2618-2624`). A bot with any standing shell grant (`autoApprove`, or an `alwaysAllow` on a command tool) can
emit the Composio call and a `curl` to the respond route **in the same parallel tool block**, discover its own
`requestId` from `GET /api/threads/:id/messages` (also unauthenticated), and approve itself. `handle()` is invoked via
`void handle(...)`, so the proxy stays responsive while blocked — nothing serializes this.

This is **equivalent for every native permission card** and is not introduced by patch 7 — `resolvePeerComms` has the
same shape and the respond routes predate this work. It should not block the merge. It must, however, be written into
the threat model: **the Composio gate is a gate against the model's own tool surface, not against a bot that can run
shell commands.** Operational mitigation until the respond routes are bound to a caller identity: do not co-grant
shell/command tools and `composio:true` on the same bot, and keep `autoApprove:false` on every Composio-enabled bot.

### Timeout semantics

Harness: `Math.max(60_000, Number(process.env.OMB_COMPOSIO_APPROVAL_TIMEOUT_MS) || 10 * 60_000)`.
Proxy: hardcoded `11 * 60_000`. Ordering is correct **at defaults** — the harness's deny-by-timeout arrives before the
client aborts, so the user gets a logged `timeout-denied` decision rather than a bare client abort. Two gaps
(finding 7, non-blocking, both fail closed):
- Raising `OMB_COMPOSIO_APPROVAL_TIMEOUT_MS` above 11 minutes silently **inverts** the ordering: the proxy aborts
  first and denies, while the harness card stays open; a human who later clicks Allow gets an approval that relays
  nothing, with no explanation in the thread.
- **Late-allow with no return path.** Approval wait (up to 10 min) + `relay()`'s own `AbortSignal.timeout(10 * 60_000)`
  can exceed the CLI's MCP tool timeout. If the CLI has already given up on the tool call but the proxy process is
  still alive, a human "Allow" **still relays the action to Composio** — the side effect happens with no result path
  back to the turn and no record in the transcript. (If the whole turn was killed, the proxy dies with it and the
  fetch aborts — safe. It is the in-between that is untidy.) The build report's claim that the timeout path shares the
  deny code path is correct by inspection; this is a different, unflagged case.

Report caveat #1 ("timeout not live-tested") is confirmed accurate by inspection: `requestComposioApproval`'s
`setTimeout` resolves `"deny"` on exactly the same non-relay branch as an explicit deny. No live test needed.

---

## Part 3 — Consistency with native cards

- **Resolves via the same respond routes.** ✅ Patches 7d/7e intercept `/api/bots/:id/respond` and
  `/api/threads/:id/respond` *before* `answerRequest`, exactly mirroring the `resolvePeerComms` intercept immediately
  above each one (`index.js:4506-4511`, `4532-4537`). Same placement, same return shape
  (`{ok:true, outcome:"allowed-once"|"rejected"}`). This is the right pattern and it is followed faithfully.
- **Second bot / delegated turn approving its own card.** Two distinct answers:
  - *Resolving a card directly* — no caller-identity check exists (bypass E). Any local caller can resolve any pending
    `requestId`. Consistent with native/peer cards; pre-existing.
  - *`ask_bot` / delegation* — the 7c route calls `autoVerdict(owner.bot, …, { unattended: isUnattended(owner.bot.id) })`,
    and patch 3a exists precisely so an `ask_bot` invocation from a human-initiated turn is **not** flagged unattended.
    So a delegated turn **inherits attended status**: if bot A delegates to bot B and B has `autoApprove:true`, A can
    drive a Composio write on B that auto-approves with no human in the loop, and the card never appears — the
    `auto-approved` decision row is the only trace. If B has `autoApprove:false` the card is raised in **B's** thread,
    not the conversation the human is watching; `notify` does fire (`index.js:888`), so it is surfaced rather than
    silent, but the human is answering in a thread they did not initiate. Latent today because `autoApprove` is `false`
    fleet-wide — this is a reason to keep it that way on any Composio-enabled bot, and it belongs in the docs (finding 8).
- **`autoApprove:true` handling matches the documented rule.** ✅ `index.js:2896` calls
  `autoVerdict(owner.bot, tool, summary, { unattended: isUnattended(owner.bot.id) })`; on `verdict.approve` it appends
  an `auto-approved` decision row with `source`/`rule` and returns `{decision:"allow", autoApproved:true}` **without**
  publishing a card. Auto-allow, logged. Webhook/unattended turns correctly do **not** inherit auto mode
  (`auto-approve.js:90-105`). Note the residual: because the summary is slug-only, the `DESTRUCTIVE`/`SENSITIVE`
  regex guards in `auto-approve.js` can never fire on a Composio action's *arguments* — under `autoApprove:true` every
  Composio write auto-approves. Given `autoApprove` is `false` fleet-wide today, this is a documentation item, not a
  blocker — but it is the reason finding 6 matters twice.
- **`alwaysAllow` interplay (finding 9, latent).** The 7c route calls `autoVerdict` **without** `scope`; the fold
  recomputes it **with** `scope: "composio"` (`index.js:762`). `approvalKey` differs between the two. Currently inert
  in practice, because the fold sets `allowKey: undefined` for any scoped card (`index.js:852-853`), so the UI shows
  no "Always allow" button and no composio grant can be created through it. Two latent consequences worth fixing
  while you're in here: (a) a hand-set `alwaysAllow` entry matches at the route but not in the fold, and since the
  tool string is *identical for every Composio action* (`Composio: COMPOSIO_MULTI_EXECUTE_TOOL`), any such grant is
  necessarily blanket — exactly the coarseness `approvalKey`'s `COMMAND_TOOLS` special-case exists to prevent;
  (b) if the route's verdict is null but the fold's scoped recompute approves, the fold auto-answers through
  `instance.adapter.respondToRequest` — which never calls `resolveComposioApproval`, so the pending promise hangs to
  timeout. Fail-closed, but a dead end. Fix: pass `scope: "composio"` at the route, and key the grant on the action
  slug (`Composio:GMAIL_SEND_EMAIL`), not the wrapper.
- **Missing consistency check (finding 10).** `/api/internal/connectors/approval` does not check
  `owner.bot.composio === false`, which its sibling `/api/internal/connectors/request` does (`index.js:2955`).
  Unreachable today (the proxy only exists when Composio is mounted), but it is an inconsistency in a security route.

---

## Part 4 — Code quality

**Good.** Genuinely close to house style: the long explanatory comment blocks carrying *why* and the falsification
history match the surrounding code's voice; `publishComposioRequestEvent` / `logComposioDecision` deduplicate cleanly;
patch 7g's rework to reuse `bus.publish` and the existing fold instead of hand-rolled store writes is the right call
and is what makes the cards indistinguishable from native ones. Error handling is uniformly fail-closed. All three
live patched files pass `node --check` (re-run by this review, not inherited: `connector-proxy.js` OK, `index.js` OK,
`drivers/claude.js` OK). **No secrets logged** — verified: the classifier's `console.error` prints only tool name + slugs
+ classification; the card `summary` carries only slugs; `TOKEN` and `upstreamHeaders` are never logged; the decision
log records slugs, never arguments. (Ironically the *reason* nothing sensitive leaks is finding 6 — arguments are
never touched at all.)

**Nits:**
- `logComposioExecuteClassification` recomputes `isReadOnlyAction(slug)` per slug after the caller already computed
  `allReadOnly` — harmless, slightly redundant.
- The classifier's stderr still goes nowhere capturable (patch 6 report §4 established `connector-proxy.js` stderr
  isn't in `server.log`). The `[carrier_openmausbot patch 7]` log line is effectively write-only. The `appendDecision`
  rows are the real audit trail; the log line should not be relied on.
- `scripts/patch_omb_source.py`'s `write()` still uses text mode → the CRLF flip on every apply. Pre-existing, now
  rewriting a 295 KB `index.js`. `open(path, "w", encoding="utf-8", newline="")` fixes it. Cosmetic, but it makes
  every future diff of the live tree noisy.

---

## Part 5 — Billing guards & enablement path

- **Guard scripts untouched.** `git diff --name-only baf9cd4..f922967` returns exactly two files:
  `docs/omb-patches.md`, `scripts/patch_omb_source.py`. Filtered for `billing|guard|bots.json` → **none**.
  Explicit stat against `scripts/billing_guard.py`, `scripts/omg_billing_audit.py`, `*billing*` → empty. ✅
  `~/.openmausbot/billing-audit.py` is outside the repo and is not touched by any commit in the range. ✅
- **`bots.json` `composio` flag remains the only enablement path.** ✅ The mount condition
  `bot.composio !== false && composio.configured(cfg) && instance.adapter.capabilities.composioMcp === true`
  is unchanged at `index.js:1354` (1:1 turns) and `index.js:1828` (room turns). Patch 7 only changes what happens
  *after* that gate mounted the integration. The opt-out polarity hazard (absent field = enabled) that Phase 2A found
  on Moss is **still** pre-existing and unaddressed by patch 7 — `scripts/omb_composio_health.py` (added in the
  patch-6 base commit) detects it but nothing enforces it.

---

## REQUEST-CHANGES — numbered, actionable

**Blocking**

1. **The patch chain cannot apply to a pristine install, and fails open on reinstall. It breaks at TWO points.**
   Reproduced against a **fully pristine baseline** — `connector-proxy.js` and `drivers/claude.js` from
   `buildout/backups/*.pre-patch6`, and `index.js` + `procs.js` reconstructed by reverse-applying every entry's
   `new`→`old` in reverse list order (every reversal asserted present, so the reconstruction is exact):
   ```
   ⚠️  NEEDED    procs.js / index.js×5 / drivers-claude.js 6a      (6 entries — fine)
   ❓ MISMATCH   [connector-proxy.js]  patch 7a: classify composio execute call
   ❓ MISMATCH   [index.js]            patch 7g: composio-approval gate reuses the real
   [ERROR] 2 patch(es) could not be applied (file changed or missing).
   apply-run exit=2  →  markers written: connector-proxy.js 0, drivers/claude.js 0
   ```
   - **7a** — its `old` text *is* patch 6b's applied output, and 6b's entry is commented out
     (`scripts/patch_omb_source.py:257-274`). With 6b retired, nothing ever produces 7a's anchor.
   - **7g** — its `old` is a substring of **7b's `new`** (verified: `7g.old ⊂ 7b.new → True`). This is not merely an
     ordering hazard: `main()` evaluates `check_patch` for **every** entry against the on-disk file *before* applying
     any of them, so a patch whose anchor is created by an earlier patch **in the same file** will always report
     `MISMATCH` on a pristine tree, regardless of list order. The two-phase check-then-apply design cannot express
     layered edits at all.

   Because `if missing: sys.exit(2)` precedes the apply loop, a real (non-`--check`) run applies **nothing** — not
   patch 7, not patch 6a, not patches 1–3b. OpenMausBot ships an updater (`resources/../app-update.yml`) and updates
   replace `resources/server/server/` wholesale, so after the next update the fleet runs with `composio:true` bots and
   **no write-gate**, and the only signal is a non-zero exit from a script someone has to remember to run.

   *Fix:* re-anchor 7a's `old` on the pristine `connector-proxy.js` text (derive it from
   `backups/connector-proxy.js.pre-patch6` — that file has no other patch entries, so pre-patch6 *is* pristine for it),
   and delete the commented-out 6b block rather than leaving a live entry depending on a retired one. Fold 7g into
   7b's `new` (or give the script a real dependency/sequencing model — apply-as-you-go instead of check-all-then-apply).
   Verify **both** directions: applies clean on the reconstructed pristine tree with zero `MISMATCH`, and reports
   `applied` against the current live install.

2. **Document Patch 7 in `docs/omb-patches.md`.** There is **no `## Patch 7` section** (headings stop at Patch 6), yet
   Patch 6's text links to `#patch-7--composio-write-gate-at-the-proxy-connector-proxyjs--indexjs` — a **dead anchor**.
   The only working Composio gate in the system is undocumented in the file whose entire job is recording patch state,
   and the sole surviving description of it is a build report outside the repo. Add the section, including: the
   fail-closed matrix, the 10-min/11-min timeout pair and its env var, the `autoApprove:true` rule, and the
   self-approval limitation from finding 8.

3. **Invert the proxy to default-deny on tool name.** `EXECUTE_TOOL_NAME_RE` gates exactly `COMPOSIO_EXECUTE_TOOL` /
   `COMPOSIO_MULTI_EXECUTE_TOOL`; every other `tools/call` relays untouched, and `tools/list` is transparent so the
   agent sees whatever upstream advertises. Gate **every** `tools/call` except an explicit safe-name allowlist
   (`COMPOSIO_SEARCH_TOOLS`, `COMPOSIO_GET_TOOL_SCHEMAS`, `COMPOSIO_MANAGE_CONNECTIONS`, `COMPOSIO_WAIT_FOR_CONNECTIONS`),
   so a new or renamed executor upstream defaults to carded rather than to open. Match by suffix, as the existing
   `MANAGE_CONNECTIONS` interception already does.

4. **Make `extractActionSlugs` exhaustive, not first-hit.** Replace the fixed 6-keys × 2-levels walk with a recursive
   walk that collects those key names at **any** depth, and keep the `JSON.stringify` token scan as a fallback for
   `found.size === 0`. As written, a read-looking value in a scanned key suppresses discovery of a write slug in an
   unscanned or deeper key, and `allReadOnly` then relays with no card (bypass A). Add unit coverage for at least:
   nested `tool_calls`/`items` arrays, a slug under an unknown key name, and a mixed read+write batch (must gate).

5. **Replace verb-prefix inference with an explicit read allowlist.** `READ_ONLY_ACTION_RE` infers semantics from a
   verb prefix over a namespace Composio owns and changes without notice; it is the sole decider of whether a human is
   asked, and it fails **open**. Move to an explicit allowlist of known-read slugs (or known-read slugs per connected
   toolkit) with everything else gated. If the full-allowlist approach is too heavy for now, the minimum viable
   tightening is: drop `QUERY` and `CHECK` from the verb list, require the whole slug to match a read *shape* rather
   than a prefix, and gate anything containing a mutating token (`_AND_REPLACE`, `_SQL`, `_EXEC`, `_RUN`).
   *(The two illustrative classes in Part 2C are unverified against this install's live catalog — the structural
   argument does not depend on them.)*

6. **Put the arguments on the card.** `summary` is slug-only, so the human approving `GMAIL_SEND_EMAIL` cannot see the
   recipient, subject, or body — which is the entire decision. Add a bounded, redacted argument digest (recipient /
   subject / repo+branch / file path / row count, truncated, secrets stripped) to `summary`. This also re-arms
   `auto-approve.js`'s `DESTRUCTIVE`/`SENSITIVE` guards, which currently can never fire on a Composio action because
   they are matched against a summary that contains no arguments. Second-order benefit: this is the only change that
   materially raises the cost of the prompt-injection path (bypass D).

**Test-coverage note for finding 1:** the pristine baseline used for that reproduction covered **all four** patched
files — `connector-proxy.js` and `drivers/claude.js` from the pre-patch6 backups, `index.js` and `procs.js`
reverse-reconstructed from the live tree. An earlier partial run that left the live `index.js` in place found only the
7a break; the full baseline is what surfaced 7g.

**Non-blocking — fix or document before fleet rollout**

7. **Timeout coupling.** Have the proxy derive its abort from the same `OMB_COMPOSIO_APPROVAL_TIMEOUT_MS` (harness
   returns it, or the proxy reads it), instead of a hardcoded 11 min — raising the harness value today silently
   inverts the ordering. Separately, decide the late-allow case: if the CLI has already timed out the tool call, an
   allow arriving afterwards still relays the action to Composio with no path back to the turn and no transcript
   record. Consider recording the relay outcome as an activity message regardless of whether the CLI is still
   listening.

8. **Write the self-approval limitation into the threat model.** `resolveComposioApproval` matches a global map with
   no caller-ownership check, and the respond routes are loopback-only with no token — a bot with any standing shell
   grant can approve its own card from a parallel tool call in the same turn. **Pre-existing and equivalent for native
   cards; not a patch-7 regression.** But it bounds what the gate can claim. Until the respond routes carry a caller
   identity: never co-grant shell/command tools with `composio:true`, keep `autoApprove:false` on every
   Composio-enabled bot, and say so in the docs.

9. **`alwaysAllow`/scope mismatch.** Pass `scope: "composio"` in the 7c route's `autoVerdict` call so it agrees with
   the fold's recompute, and key the grant on the action slug rather than the wrapper name — otherwise any grant that
   ever gets created is a permanent blanket allow over every Composio write. Also handle the dead-end case where the
   fold's recompute approves and answers through the provider adapter, leaving the Composio promise to time out.

10. **Add the missing `owner.bot.composio === false` check** to `/api/internal/connectors/approval`, matching
    `/api/internal/connectors/request` (`index.js:2955`).

11. **Housekeeping:** `patch_omb_source.py`'s `write()` → `newline=""` to stop the CRLF flip on every apply; note in
    the docs that `connector-proxy.js` stderr is not captured anywhere, so `appendDecision` rows — not the
    `[carrier_openmausbot patch 7]` log line — are the audit trail.

**Explicitly not required to change**

- Patch 6a can stay. It is inert but harmless, and its corrected comments now honestly record the falsified premise —
  that history is worth keeping in-tree. The `controlsHost`/`mcp__computer` parity comment remains unverified and is
  correctly labeled as such.
- The 13-entry / "6/6" numbering mismatch flagged in the patch-6 report is a non-issue; one entry per touched file is
  the established convention.
- Helm's `engine=claude` billing violation is real and current but is **not** caused by these commits (confirmed:
  nothing in the range touches any guard script, `bots.json`, or Helm's config). Needs its own investigation.

---

## Bottom line

The architecture is correct and the fail-closed discipline is better than most code that claims it — the gate blocks
the relay, resolves through the same routes and the same fold as native cards, and denies on every error path I could
construct. Merge it once finding 1 is fixed (without that, the next app update silently removes the gate — and the
script's check-then-apply design has to change, not just the two anchors), findings
2–6 are addressed (the gate's coverage is currently narrower than its documentation implies), and findings 7–11 are
either fixed or written down. The build report's own caveats were accurate and its negative results were honest; the
only material thing it did not surface is the pristine-install chain break.

**VERDICT: REQUEST-CHANGES.**

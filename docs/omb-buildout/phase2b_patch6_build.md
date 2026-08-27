# Phase 2B — Patch 6 Build: Composio Approval-Gate Fix

Executed 2026-08-27 against the live OMB harness at `http://127.0.0.1:8799`, repo `C:/Users/micha/carrier_hermes` (branch `carrier_openmausbot`, worktree `C:/Users/micha/worktrees/carrier_openmausbot`).

## Headline finding — read this before anything else

**The primary fix (patch 6a) does not work.** It is applied, on disk, syntactically valid, and survives an idempotent re-apply — but live testing on a completely fresh session proved it does not close the approval gap it was written to close. `mcp__composio__*` calls still execute with **zero** `request.opened` approval cards after this patch, identical to the pre-patch behavior documented in Phase 2A. `autoApprove:false` is still silently a no-op for Composio.

**The actual safety interlock remains what Phase 2A already identified: Yeoman and Inbox are pinned to `ollama::llama3.1:8b-instruct-q4_K_M`, a model that cannot reliably drive MCP tool calls.** That pinning — not this patch, not `autoApprove`, not the permission broker — is the only thing currently preventing an ungated Composio write. Do not move either bot to a stronger model based on this patch.

Because the premise was falsified mid-build, **the brief's step 4 (WRITE test — send a test email via Gmail Composio, expect a denyable card) was not executed.** There is no card to deny; running it would have attempted a real `GMAIL_SEND_EMAIL` call against the live managed-broker Gmail account with nothing available to stop it. Advisor guidance during this build was explicit that this test should not be run once the premise was disproven, and I agreed — the non-routable recipient address would not have prevented Composio from attempting the send.

Patch 6b (the defense-in-depth action classifier) is applied and passed static/syntax checks, but could not be runtime-verified — see below.

Everything else the brief asked for (repo changes, idempotent patch script, live-install apply, restore, billing-guard/health-check verification, commit) was completed and is reported below.

---

## 1. Repo work

- Worktree created at the sibling path per the brief's pitfall warning: `git worktree add C:/Users/micha/worktrees/carrier_openmausbot carrier_openmausbot`. Verified: `git worktree list` shows it, `git -C .../worktrees/carrier_openmausbot branch --show-current` → `carrier_openmausbot`.
- `scripts/patch_omb_source.py`: added two new entries following the existing `PATCHES` list pattern — `PATCH 6a` (`drivers/claude.js`) and `PATCH 6b` (`connector-proxy.js`). **Numbering note:** the brief calls this "patch #6" and expects `check_omb_patches.py → 6/6`. The script had 5 pre-existing dict entries (patches 1, 2a, 2b, 3a, 3b — 4 *logical* patch numbers, since 2a/2b share logical number "2"). Adding one entry per touched file (matching the existing one-file-per-entry convention, same as 2a/2b) makes **7** entries total, not 6. I kept the established per-file-entry convention rather than restructuring the schema to force an exact "6/6" — see §3 for actual output.
- `docs/omb-patches.md`: added a "Patch 6" section, later revised in place (before committing) to state the live-verified negative result rather than the originally-intended "fixed" framing. Full section reproduced in §5.
- `scripts/omb_composio_health.py` (new): standalone, zero-LLM, zero-network-beyond-`bots.json` check. Flags any bot missing an explicit `composio` field. Not part of the billing guard.
- `check_omb_patches.py` (skill dir, not a git repo — saved directly, not committed): added a docstring note explaining it's patch-count-agnostic by design and documenting a real gap — it hardcodes the `main` branch checkout path, so it cannot see an unmerged branch's patches until merge. Confirmed empirically in §3.

## 2. Source diffs (live install, patches 6a/6b)

Both files were patched via `patch_omb_source.py`, not by hand. One incidental side effect: writing through Python's default text-mode `open(path, "w")` on Windows expands `\n` → `\r\n`, so **both entire files flipped from LF to CRLF line endings** (content unaffected — confirmed by diffing after stripping `\r` from both sides, content-only diff below; `node --check` passed on both). This affects every future re-application of this script on Windows, not just patch 6 — worth a follow-up but out of scope here since it's cosmetic and pre-existing in the script.

### `drivers/claude.js` (patch 6a, final version after the mid-build comment correction — see §4)

```diff
@@ -491,7 +491,17 @@
             const allowed = [];
             if (turn.integrations?.composio) {
                 mcpServers.composio = { ...turn.integrations.composio };
-                allowed.push("mcp__composio");
+                // carrier_openmausbot patch 6a: do NOT pre-allow mcp__composio.
+                // Every Composio action, including write-shaped ones like
+                // GMAIL_SEND_EMAIL, is funneled through the single wrapper
+                // tool COMPOSIO_MULTI_EXECUTE_TOOL — pre-allowing the whole
+                // server (the previous behavior) blanket-approved every
+                // Composio call before OMB's own autoVerdict()/approval-card
+                // pipeline ever saw it, silently bypassing autoApprove:false.
+                // Leaving it off `allowed` was INTENDED to route it through
+                // the same --permission-prompt-tool mcp__ogb__approve broker
+                // used by host-controlling computer tools above (the
+                // `controlsHost` branch). Live-verified 2026-08-27: it does
+                // NOT — mcp__composio__* calls still execute with zero
+                // request.opened cards after this change, on both a resumed
+                // and a brand-new session. See docs/omb-patches.md "Patch 6"
+                // for the evidence. The controlsHost/mcp__computer parity
+                // claim above is UNVERIFIED, not confirmed working — no bot
+                // is currently configured with computer:"local" to test it.
+                // Until this is genuinely fixed, the ollama-only model
+                // pinning on Yeoman/Inbox remains the real safety interlock.
             }
             if (turn.integrations?.computer) {
                 mcpServers.computer = {
```

### `connector-proxy.js` (patch 6b, final version — corrected once more after the same false claim was found here too, see §7)

```diff
@@ -113,6 +113,65 @@
             return typeof slug === "string" && ["add", "connect", "initiate"].includes(action) ? [slug.toLowerCase()] : [];
         }))];
 }
+// carrier_openmausbot patch 6b: classify composio execute calls — logging
+// only, never blocks or rewrites anything. Originally intended as
+// defense-in-depth behind claude.js's patch 6a broker gate; live-verified
+// 2026-08-27 that patch 6a does NOT gate composio calls (see
+// docs/omb-patches.md "Patch 6"). There is currently no gate for Composio
+// at all — this log is the only visibility into write-shaped calls that
+// exists right now, not a backstop behind a working one.
+const READ_ONLY_ACTION_RE = /^([A-Z0-9]+_)?(SEARCH|GET|LIST|FETCH|FIND|READ|RETRIEVE|QUERY|CHECK)_/;
+const READ_ONLY_META_TOOLS = new Set(["COMPOSIO_SEARCH_TOOLS", "COMPOSIO_GET_TOOL_SCHEMAS", "COMPOSIO_WAIT_FOR_CONNECTIONS"]);
+const EXECUTE_TOOL_NAME_RE = /^COMPOSIO_(MULTI_)?EXECUTE_TOOL$/i;
+const UPPER_SNAKE_TOKEN_RE = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b/g;
+function extractActionSlugs(args) {
+    if (!args || typeof args !== "object" || Array.isArray(args))
+        return [];
+    const found = new Set();
+    for (const key of ["tool_slug", "toolSlug", "slug", "action", "tool", "name"]) {
+        if (typeof args[key] === "string")
+            found.add(args[key]);
+    }
+    for (const key of ["tools", "actions", "tool_slugs", "calls"]) {
+        const list = args[key];
+        if (!Array.isArray(list))
+            continue;
+        for (const item of list) {
+            if (typeof item === "string") {
+                found.add(item);
+                continue;
+            }
+            if (!item || typeof item !== "object")
+                continue;
+            for (const itemKey of ["tool_slug", "toolSlug", "slug", "action", "tool", "name"]) {
+                if (typeof item[itemKey] === "string")
+                    found.add(item[itemKey]);
+            }
+        }
+    }
+    if (found.size === 0) {
+        // Unfamiliar shape: scan the serialized arguments for anything that
+        // looks like an action slug rather than silently treating it as safe.
+        try {
+            for (const token of JSON.stringify(args).match(UPPER_SNAKE_TOKEN_RE) ?? [])
+                found.add(token);
+        }
+        catch {
+            // ignore
+        }
+    }
+    return [...found];
+}
+function isReadOnlyAction(slug) {
+    return READ_ONLY_META_TOOLS.has(slug) || READ_ONLY_ACTION_RE.test(slug);
+}
+function logComposioExecuteClassification(name, args) {
+    const slugs = extractActionSlugs(args);
+    // Fail-open: no slug found at all is ambiguous, so it logs as write.
+    const entries = slugs.length ? slugs.map((slug) => `${slug}:${isReadOnlyAction(slug) ? "read" : "write"}`) : ["<unresolved>:write"];
+    const hasWrite = slugs.length === 0 || slugs.some((slug) => !isReadOnlyAction(slug));
+    console.error(`[carrier_openmausbot patch 6] ${name} -> ${entries.join(", ")}${hasWrite ? " (write-shaped or unresolved; NOT gated — see docs/omb-patches.md Patch 6)" : " (read-only)"}`);
+}
 async function showConnectorCards(slugs) {
     const response = await fetch(`${HARNESS}/api/internal/connectors/request`, {
         method: "POST",
@@ -141,6 +200,10 @@
             send(textResult(id, "OpenMausBot is handling connection completion and will continue the task automatically."));
             return;
         }
+        // carrier_openmausbot patch 6b: logging only, never blocks or rewrites —
+        // see the function comment above (no working gate exists yet).
+        if (EXECUTE_TOOL_NAME_RE.test(name))
+            logComposioExecuteClassification(name, params.arguments);
     }
     const response = await relay(message);
     if (response && id !== undefined)
```

`COMPOSIO_EXECUTE_TOOL` (singular, non-multi) does not exist anywhere in this install — grepped the full server directory, only `COMPOSIO_MULTI_EXECUTE_TOOL` appears (`index.js:1603`). The classifier's regex covers both names per the brief's instruction ("if it exists"), but only the MULTI variant is real here.

## 3. Idempotency + syntax proof

```
=== APPLY (run 1) ===
⚠️  NEEDED      [drivers/claude.js] carrier_openmausbot patch 6a: do NOT pre-allow mcp__composio
⚠️  NEEDED      [connector-proxy.js] carrier_openmausbot patch 6b: classify composio execute call
Applying 2 patch(es)...
  ✅ Patched: drivers\claude.js
  ✅ Patched: connector-proxy.js

=== APPLY (run 2 — proving idempotency) ===
✅ APPLIED     [drivers/claude.js] carrier_openmausbot patch 6a: do NOT pre-allow mcp__composio
✅ APPLIED     [connector-proxy.js] carrier_openmausbot patch 6b: classify composio execute call
✅ All 7 patches already applied. Nothing to do.

=== node --check ===
claude.js: OK
connector-proxy.js: OK
```

**`check_omb_patches.py` (the brief's literal step 1 command) vs the worktree's own script — two different results, both correct for what they check:**

```
$ python3 C:/Users/micha/AppData/Local/hermes/skills/autonomous-ai-agents/openmausbot/scripts/check_omb_patches.py
✅ All 5 patches already applied. Nothing to do.

$ python3 C:/Users/micha/worktrees/carrier_openmausbot/scripts/patch_omb_source.py --check --omb-dir <live>
✅ All 7 patches already applied. Nothing to do.
```

`check_omb_patches.py` hardcodes `~/carrier_hermes/scripts/patch_omb_source.py` — the **main branch** checkout — not the branch/worktree this patch was built on. Patches 1–3b show there because a prior cycle already merged `carrier_openmausbot` into `main` (`git merge-base --is-ancestor carrier_openmausbot main` confirms main is a descendant). Patch 6 lives only on `carrier_openmausbot` per the brief's explicit "commits happen on this branch / no push" instruction, so it is invisible to the main-branch delegate until a future merge. I did not merge or push to work around this — that's the orchestrator's call after Opus review. Documented this gap directly in `check_omb_patches.py`'s docstring (see §1).

## 4. Live verification — what actually happened

Harness restart: `taskkill /IM OpenMausBot.exe /F` found nothing running (harness was already down); launched via `Start-Process` (the brief's `cmd /c start` form did not actually spawn a persisting process in this shell — PowerShell's `Start-Process` did). Polled `/api/instances` until `200`; took ~2 boot cycles and a full process kill/relaunch to get a clean listener (first attempt bound the port but hung on all requests — resolved by a clean `Stop-Process -Force` + single relaunch). `server.log` confirms clean start with no `[err]` lines.

**Test 1 — READ, resumed session (as the brief's exact test).** Patched Yeoman to `{"instanceId":"claude","model":"claude-haiku-4-5"}`, sent the Hacker-News-search-style prompt from Phase 2A to the same thread (`3196c41c-...`). Result: `COMPOSIO_SEARCH_TOOLS` and `COMPOSIO_MULTI_EXECUTE_TOOL` both ran `ok:true`, **zero `request.opened` events**, `turn.completed ok:true`.

This alone doesn't prove the patch failed — it could be session-resume carrying forward a permission grant from Phase 2A's pre-patch turn (this thread resumed the exact same Claude Code CLI session, `sessionId: 3fed3204-3c47-434c-9035-09779b99d33d`, that Phase 2A originally used). So a second, controlled test was run:

**Test 1b — READ, brand-new session (the actual proof).** Created a fresh task via `POST /api/bots/8680e15b.../tasks` → new thread `e611e9a8-2db4-4811-ba26-92044fc20228`, no resume cursor. Sent the same read-only Composio prompt. New session confirmed (`sessionId: b686ac59-a2e1-444b-9d25-aa10de388959`, distinct from Phase 2A's). Event excerpt:

```json
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_SEARCH_TOOLS"}
{"type":"item.completed","itemType":"tool","ok":true}
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_GET_TOOL_SCHEMAS"}
{"type":"item.completed","itemType":"tool","ok":true}
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL"}
{"type":"item.completed","itemType":"tool","ok":true}
{"type":"turn.completed","ok":true,"stopReason":"end_turn","cost":0.0729451}
```

**No `request.opened` event anywhere in this thread's event log.** Session-resume is ruled out as the explanation. The patch, as applied, does not gate these calls.

This also directly contradicts a comment already present in `claude.js` before this patch ("a headless acceptEdits run silently denies anything unlisted") — the observed behavior was neither a denial nor a prompt; the calls simply succeeded, exactly as before the patch.

**Test 2 (WRITE/deny) — not executed.** See headline finding. Restored and cleaned up instead.

**Cleanup, in order, completed before writing this report:**
1. Deleted the fresh test task/thread (`DELETE /api/bots/.../tasks/e611e9a8-...`).
2. Restored Yeoman: `PATCH /api/bots/8680e15b.../` → `{"modelSelection":{"instanceId":"claude","model":"ollama::llama3.1:8b-instruct-q4_K_M"}}`. Verified via `GET /api/bots`: `composio:true, autoApprove:false, modelSelection.model:"ollama::llama3.1:8b-instruct-q4_K_M"`. Matches Phase 2A's pre-pilot baseline.

**`controlsHost`/`mcp__computer` parity — untested, and deliberately not tested.** The claude.js comment for the `computer` integration claims the same "omit from `allowed` → routes to broker" pattern works there. That claim is now suspect given patch 6a's failure, but I did not enable a bot with `computer:"local"` to test it — no bot currently has that config (only Helm, with `computer:"vm"`, a different code path/`controlsHost` value), and creating one to test would open a live host-control surface beyond this brief's authorized scope. Flagged in the docs and code comment as unverified rather than assumed-working.

**Patch 6b (classifier) — not runtime-verified.** `connector-proxy.js` runs as a grandchild process (Claude CLI → MCP subprocess); its `console.error` output is not captured in `server.log` or any other log file found on this system. Confirmed by grepping `server.log` for the classifier's own log prefix (`carrier_openmausbot patch 6`) after both live tests — zero matches. Static verification only: `node --check` passes, logic reviewed by inspection (extracts a slug from several candidate argument shapes, falls back to scanning serialized args for an upper-snake-case token, classifies against a read-only regex, fails open to "write" when ambiguous). Per this project's own precedent (Phase 1B labeled 2a/2b `VERIFIED-STATIC-ONLY` for an analogous reason), 6b's status is **VERIFIED-STATIC-ONLY, not runtime-exercised.**

## 5. `docs/omb-patches.md` — Patch 6 section (inline)

> **Status: NOT resolved.** Both halves of this patch are applied, on disk, and idempotent — but live testing (below) proved 6a does not close the approval gap it was written to close. Composio calls still execute with zero approval cards after this patch, identically to before it. The safety interlock is still the ollama-only model pinning on Yeoman/Inbox, not this patch.
>
> **Symptom (found in Phase 2A pilot):** With `Yeoman.autoApprove === false` and no `alwaysAllow` grant, every `mcp__composio__*` tool call — including four rounds of `COMPOSIO_MULTI_EXECUTE_TOOL` — executed with **zero** approval cards. `autoVerdict()` should have returned `{approve: null, source: "no-grant"}` but was never consulted at all.
>
> **Root cause:** `drivers/claude.js` did `allowed.push("mcp__composio")` and passed it in `--allowedTools`, blanket-allowlisting the entire `mcp__composio` MCP server before OMB's own approval-card pipeline ever got a say — bypassing `autoApprove:false` for every Composio action, read or write, since all of them funnel through the single `COMPOSIO_MULTI_EXECUTE_TOOL` wrapper name.
>
> **Fix attempted (6a):** `drivers/claude.js` no longer pushes `mcp__composio` onto `allowed`, intending Composio calls to fall through to `--permission-prompt-tool mcp__ogb__approve` like other gated tools, mirroring the existing `controlsHost`/`mcp__computer` comment nearby.
>
> **⚠️ Verified NOT effective at runtime.** Tested twice: a resumed session (thread `3196c41c...`) and — the controlling test — a brand-new session with no resume cursor (thread `e611e9a8-2db4-4811-ba26-92044fc20228`, session `b686ac59-a2e1-444b-9d25-aa10de388959`). Both: `COMPOSIO_SEARCH_TOOLS`, `COMPOSIO_GET_TOOL_SCHEMAS`, `COMPOSIO_MULTI_EXECUTE_TOOL` all executed `ok:true`, zero `request.opened` events, `turn.completed ok:true`. Session-resume ruled out as the explanation. This contradicts the file's own pre-existing comment ("a headless acceptEdits run silently denies anything unlisted") — the calls were neither denied nor prompted, just executed, identically to pre-patch. **Working conclusion: omitting a tool from `--allowedTools` does not, by itself, route an MCP tool call through `--permission-prompt-tool` on this CLI version — at least not for `mcp__composio`.** Whether the parallel `controlsHost`/`mcp__computer` case actually works is untested (no bot has `computer:"local"`; one was not created to test this given live-account blast radius) and should not be assumed correct either.
>
> **Practical consequence: patch 6a alone does not close the approval gap.** The only thing currently preventing an ungated Composio write from Yeoman or Inbox remains the ollama model pinning identified in Phase 2A. Do not move either bot to a stronger model until this is genuinely fixed.
>
> **Fix (6b, defense-in-depth logging, not a gate):** `connector-proxy.js` classifies `COMPOSIO_EXECUTE_TOOL`/`COMPOSIO_MULTI_EXECUTE_TOOL` calls by extracting the action slug and matching a read-only pattern, logging write-shaped/unresolved calls to stderr (fail-open to "write"). Never blocks or rewrites. Originally designed to sit behind 6a's gate — since 6a does not gate anything, this log is currently the *only* visibility into write-shaped Composio calls that exists, not a backstop behind a working one.
>
> **6b not runtime-verified either:** `connector-proxy.js`'s stderr is not captured in `server.log` or any log found on this system (confirmed via grep after the live tests — zero matches for its log prefix). Static/syntax-verified only (`node --check` passes, logic reviewed by inspection). Per Phase 1B's own precedent for the same situation: **VERIFIED-STATIC-ONLY, not runtime-exercised.**
>
> **Given 6a does not work, 6b's design is mis-ordered.** The likely correct fix is Phase 2A's un-chosen option (b): have `connector-proxy.js` itself raise the approval card for write-shaped actions via the same mechanism it already uses for `MANAGE_CONNECTIONS`, rather than relying on the CLI-level broker for Composio. That's a design decision outside this patch's scope.
>
> **Billing-guard compatibility:** does not touch `bots.json`'s `composio` field, its opt-out polarity, or the `bot.composio !== false` mount condition. The three guard scripts remain untouched.

Full text (identical, this is the complete section) is in the repo at `docs/omb-patches.md` under `## Patch 6`.

## 6. Billing-guard compatibility — explicit verification

Per the brief's hard requirement, confirmed the diff touches **none** of the three guard scripts (`billing-audit.py`, `omg_billing_audit.py`, `billing_guard.py` — not present in either diff in §2, and not in `git diff --stat` for the repo commit). Confirmed the mount condition is unchanged: `composio.js`'s `mcpIntegration` is invoked from the driver only when `turn.integrations.composio` is set, which traces back to the harness's existing `bot.composio !== false` gate in `index.js` (`PATCH /api/bots/:id`, unmodified by this patch) — this patch only touches what happens *after* that gate already decided to mount Composio, not the gate itself. `composio` remains in `bots.json` exactly where the guard reads it — confirmed via `omb_composio_health.py`'s output below, which reads the same file.

```
$ python3 C:/Users/micha/.openmausbot/billing-audit.py
✅ openaiCompat key set (zero-model OR guard)

🚨 VIOLATIONS (1):
   Helm: decision bot using engine=claude (expected grok/codex)
⚠️  WARNINGS (2):
   Inbox: composio=True (should be False)
   Yeoman: composio=True (should be False)
exit code: 0
```

The 2 WARNINGs are exactly the expected pilot composio warnings (Inbox, Yeoman), matching Phase 2A's baseline. **The 1 VIOLATION (Helm running `engine=claude model=claude-sonnet-5` instead of `grok/codex`) is pre-existing and unrelated to this patch** — I never touched Helm's config, and Phase 2A's own billing-audit run recorded Helm correctly on `codex`/`gpt-5.6-*`. Something changed Helm's engine/model between Phase 2A and now, outside this session's changes. Worth a separate look; not caused by patch 6.

```
$ python3 scripts/omb_composio_health.py
Checked 26 bot(s) in C:\Users\micha\.openmausbot\bots.json

composio=true (2):
  - Inbox (4658d515-81f7-435a-a76f-0d2d271f4be0)
  - Yeoman (8680e15b-da3c-47ee-9ff7-29e838f6710c)

✅ Every bot has an explicit composio field. No silent-enablement hazard.
exit code: 0
```

No bot is missing the field — the Moss-style hazard from Phase 2A has not recurred.

## 7. Commit

Four commits on `carrier_openmausbot` (worktree `C:/Users/micha/worktrees/carrier_openmausbot`), **not pushed**:

```
ceee06a patch6: fix same false-claim in docs/omb-patches.md Patch 6 section
d1f2759 patch6: fix remaining false-claim comments/log string in connector-proxy.js
a1aab0d patch6: correct in-code comment to match live-verified result
baf9cd4 patch6: route Composio MCP through permission broker + action classifier + composio health check
```

`baf9cd4` is the main patch (3 files: `scripts/patch_omb_source.py`, `docs/omb-patches.md`, new `scripts/omb_composio_health.py`). The next three are cleanup made during this same build, each a separate commit per the never-amend instruction: after the live test disproved the original claim that the broker route was "the proven working pattern," `a1aab0d` fixed the `claude.js` comment, then `d1f2759` caught the same false claim still present in `connector-proxy.js`'s comments and its classifier's own log-line suffix (missed in the first pass), then `ceee06a` fixed the identical claim still standing in `docs/omb-patches.md`'s 6b subsection. All three are wording-only — no functional change, confirmed by re-running `node --check` and `patch_omb_source.py --check` (7/7) after each. `check_omb_patches.py` in the skill dir was edited and saved directly (not a git repo, per the brief).

## 8. What Opus should scrutinize

1. **Patch 6a does not achieve its goal.** This is the load-bearing finding — everything else in this report is secondary to it. Re-verify independently if possible; I ruled out session-resume as a confound but have not ruled out every alternative explanation (e.g., some other Claude Code CLI permission layer specific to MCP-configured servers that this codebase's `allowedTools` mechanism doesn't actually control for MCP tools at all, as opposed to built-in tools).
2. **The likely correct fix is Phase 2A's un-chosen option (b):** have `connector-proxy.js` itself raise the approval card for write-shaped `COMPOSIO_MULTI_EXECUTE_TOOL` calls (reusing the same `/api/internal/connectors/request`-style mechanism it already uses for `MANAGE_CONNECTIONS`), rather than relying on the CLI-level `--permission-prompt-tool` broker for Composio specifically. I did not implement this — it's a design decision (which endpoint raises the card, how it's resolved, whether it blocks the call pending human response) outside this brief's scope, and the brief was explicit that the classifier should stay logging-only.
3. **The `controlsHost`/`mcp__computer` comment in `claude.js` is now unverified, not confirmed.** If any other patch or design decision has been relying on that comment being true, it should be re-examined the same way patch 6a was.
4. **Numbering mismatch:** brief expected "6/6"; actual is 7 entries (2 new: 6a, 6b) against 5 pre-existing, for 7/7. Documented, not silently forced to match.
5. **`check_omb_patches.py`'s main-branch-only path** means it will not reflect patch 6 (or any unmerged branch work) until a merge happens. This is pre-existing script design, not something this patch introduced, but worth confirming it's the intended operating model before relying on it as a fleet-wide health signal.
6. **Helm's `engine=claude`/`claude-sonnet-5` billing violation** is real, current, and not something this session caused — surfaced here since it showed up in the required billing-audit run, but it needs separate investigation.
7. **CRLF line-ending flip on both patched live files** (content-only, cosmetic) — a latent bug in `patch_omb_source.py`'s `write()` on Windows, pre-existing in the script, not something patch 6 introduced but newly triggered by this session's apply run.

# Patch 6 — Composio Approval-Gate Fix (BUILD brief, Sonnet)

You are implementing a security fix in OpenMausBot (OMB). Live install: C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/. Harness: http://127.0.0.1:8799 (running; PATCH /api/config and provider reloads can interrupt turns — avoid them).

## The bug (root-caused in Phase 2A — read C:/Users/micha/.openmausbot/buildout/reports/phase2a_composio_pilot.md first)
drivers/claude.js (~line 494) does `allowed.push("mcp__composio")` and passes it via --allowedTools (~line 563) to the Claude Code CLI. This blanket-allowlists the ENTIRE composio MCP server, so mcp__composio__* calls NEVER reach OMB's permission broker / autoVerdict() / approval cards. autoApprove:false is silently bypassed for all Composio tools, including write actions (GMAIL_SEND_EMAIL etc.).

## Required fix (hybrid, patch #6 in the carrier_openmausbot patch set)
1. **drivers/claude.js**: remove `mcp__composio` from the blanket allowlist push so composio calls route through the existing permission broker path (--permission-prompt-tool mcp__ogb__approve, same mechanism as other gated tools, verified working in Phase 1B).
2. **connector-proxy.js**: add an action classifier for COMPOSIO_MULTI_EXECUTE_TOOL (and COMPOSIO_EXECUTE_TOOL if it exists). Parse the MCP call arguments to extract the underlying action slug(s):
   - READ-ONLY actions — slug matches ^([A-Z0-9_]+_)?(SEARCH|GET|LIST|FETCH|FIND|READ|RETRIEVE|QUERY|CHECK)_ or the meta tools COMPOSIO_SEARCH_TOOLS / COMPOSIO_GET_TOOL_SCHEMAS / COMPOSIO_WAIT_FOR_CONNECTIONS: relay normally. Combined with (1) these will still card at the broker; that is ACCEPTABLE for now (safe default). Do NOT build a bypass for them in this patch.
   - WRITE-SHAPED actions (SEND, CREATE, DELETE, UPDATE, POST, PUT, PATCH, WRITE, UPLOAD, MOVE, ARCHIVE, EXECUTE, RUN, ADD, REMOVE, SET, MODIFY, REPLY, FORWARD, MERGE, PUSH, or anything not matching the read-only pattern): defense-in-depth — verify the classification is logged (console + relay) so a future audit can see write actions distinctly. If a lightweight hook exists to annotate the relayed call (e.g. adding a header or log line), use it. DO NOT silently drop or rewrite calls.
   The PRIMARY gate is (1) — the broker cards everything again. The classifier is layered logging/defense, not the sole gate. Keep it simple and fail-open to "treat as write" for anything ambiguous.
3. **Billing-guard compatibility (CRITICAL, Michael's hard requirement)**: the billing guard scripts (C:/Users/micha/.openmausbot/billing-audit.py, carrier_hermes/scripts/omg_billing_audit.py, billing_guard.py) are IMMUTABLE — do not edit them. They read the per-bot `composio` flag from bots.json. Your fix must NOT introduce any enablement path that bypasses that flag: confirm after the fix that composio integration is still mounted ONLY when bot.composio !== false, and that the flag remains in bots.json where the guard reads it. State this verification explicitly in your report.
4. **Polarity health check**: add a small standalone script scripts/omb_composio_health.py in the repo (NOT part of the guard) that: lists any bot missing an explicit composio field (Moss-style silent enablement hazard), lists bots with composio=true, and exits 1 if any bot lacks the field. Zero LLM, zero network beyond localhost:8799 / bots.json.

## Repo work (all patches must survive OMB auto-updates)
- Repo: C:/Users/micha/carrier_hermes, branch carrier_openmausbot. PITFALL: create the worktree at a SIBLING path, NOT inside the repo: `git worktree add C:/Users/micha/worktrees/carrier_openmausbot carrier_openmausbot` (if a stale worktree exists, reuse or repair it). Immediately verify: `git worktree list && git -C C:/Users/micha/worktrees/carrier_openmausbot branch --show-current` must show carrier_openmausbot. All commits happen on this branch.
- Update scripts/patch_omb_source.py: add patch #6 (both files) as idempotent apply/check entries following the existing pattern (read it first).
- Update the verifier at C:/Users/micha/AppData/Local/hermes/skills/autonomous-ai-agents/openmausbot/scripts/check_omb_patches.py to know about patch #6 (same detection pattern style).
- Update docs/omb-patches.md with patch #6: symptom, root cause, diff summary, verification steps.
- Apply the patch to the live install via patch_omb_source.py (proving the idempotent path works), NOT by hand-editing only.

## Live verification (after applying + restarting OMB)
Restart: taskkill //IM OpenMausBot.exe //F ; then: cmd //c start "" "C:\Users\micha\AppData\Local\Programs\openmausbot\OpenMausBot.exe" ; poll http://127.0.0.1:8799/api/instances until up.
1. python3 check_omb_patches.py → 6/6 applied. node --check on both patched files.
2. Temporarily PATCH Yeoman (id 8680e15b-da3c-47ee-9ff7-29e838f6710c) to {"modelSelection":{"instanceId":"claude","model":"claude-haiku-4-5"}}.
3. READ test: message Yeoman to search news via Composio. EXPECT: request.opened approval card for the composio MCP call now appears (this is the fix working). Approve it via POST /api/bots/:id/respond {behavior:"allow"} (read-only). Confirm the tool executes and returns real data.
4. WRITE test: message Yeoman to send a test email via Gmail Composio to michael+test@example.invalid. EXPECT: approval card appears. DENY it via the respond API. Confirm the send did NOT happen (no GMAIL_SEND execution in events) and the bot reports the denial in text.
5. Check events NDJSON for both tests; capture excerpts as proof. Zero EADDRINUSE / broker unavailable.
6. RESTORE Yeoman to {"modelSelection":{"instanceId":"claude","model":"ollama::llama3.1:8b-instruct-q4_K_M"}} and verify via GET /api/bots.
7. Run python3 C:/Users/micha/.openmausbot/billing-audit.py → must exit 0 with only the 2 expected pilot composio warnings. Run your new omb_composio_health.py → document output.

## Commit (NO push — the orchestrator pushes after Opus review)
git add the changed repo files (patch_omb_source.py, docs/omb-patches.md, scripts/omb_composio_health.py) in the worktree; commit on carrier_openmausbot with message "patch6: route Composio MCP through permission broker + action classifier + composio health check". Also commit the check_omb_patches.py change in its skill dir is NOT a git repo — just save the file. Do NOT push.

## Output
Report to C:/Users/micha/.openmausbot/buildout/reports/phase2b_patch6_build.md: full diffs of both source patches, repo files changed, live test proofs (event excerpts for read-approve and write-deny), billing-guard compatibility verification statement, health check output, commit SHA, and anything Opus should scrutinize.

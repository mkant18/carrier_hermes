# Patch 7 — Composio Write-Gate at the Proxy (BUILD brief, Sonnet)

Architectural decision (by the orchestrator, final): the approval gate for Composio lives in connector-proxy.js — the only layer that sees the underlying action slug. The CLI-level --allowedTools approach (patch 6a) is live-proven ineffective and stays as-is (harmless). You are implementing patch 7.

MANDATORY PRE-READING:
- C:/Users/micha/.openmausbot/buildout/reports/phase2b_patch6_build.md (what failed and why)
- C:/Users/micha/.openmausbot/buildout/reports/phase2a_composio_pilot.md (API map)
- Source: C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/ — read connector-proxy.js, composio.js, and in index.js the request machinery (request.opened / request.resolved / /api/internal/connectors/request handler / POST /api/bots/:id/respond and /api/threads/:id/respond) plus how permission requests are created/awaited for the ogb broker path.

## Design (patch 7, in connector-proxy.js + a new internal harness endpoint if needed)
1. Reuse patch 6b's classifier (already present: extractActionSlugs/isReadOnlyAction). On COMPOSIO_(MULTI_)?EXECUTE_TOOL calls:
   - ALL slugs read-only → relay through unchanged (no card). Read-only = existing regex + meta tools.
   - ANY slug write-shaped or unresolved → BLOCK the relay and raise a real approval request in the owning thread, wait for resolution:
     - allow → relay the original MCP message unchanged
     - deny (or timeout, default 10 minutes) → do NOT relay; return a proper MCP error/text result to the CLI: "OpenMausBot: this Composio action (<slugs>) requires approval and was denied/timed out." (mirror the textResult() pattern already used for MANAGE_CONNECTIONS)
2. To raise the card: study how /api/internal/connectors/request creates connector cards and how the ogb permission broker creates request.opened permission entries. Prefer creating a REAL permission request (requestType "permission", tool name like "Composio: <slug>") resolvable via the existing POST /api/bots/:id/respond and /api/threads/:id/respond routes and visible in the UI like any other card. If the existing internal endpoint can't express that, ADD a minimal bearer-gated internal endpoint in index.js (e.g. POST /api/internal/connectors/approval {botId?, threadId?, tool, summary} → {requestId}, plus long-poll GET or reuse the existing request-resolution plumbing) following the established patterns. Keep it small and consistent with existing code style.
3. connector-proxy.js knows the harness URL + bearer token already (it calls /api/internal/connectors/mcp). It must learn the thread/bot identity — check what env/args the proxy is spawned with (composio.js mcpIntegration / SPAWNED_PROXIES) and extend minimally if the thread id isn't already passed.
4. Fail-closed: if the approval request cannot be created (endpoint error, no thread id), DENY the write-shaped call with a clear error message. Never fail-open.
5. Keep 6b's classification logging. Update its misleading "NOT gated" wording to reflect that patch 7 now gates.

## Constraints
- Billing guards (billing-audit.py, omg_billing_audit.py, billing_guard.py) IMMUTABLE. Do not touch bots.json semantics, the composio opt-out gate, or autoApprove handling.
- alwaysAllow/autoApprove interplay: if bot.autoApprove===true OR an alwaysAllow grant matches (study auto-approve.js autoVerdict), it is ACCEPTABLE (and preferred) to consult the same logic so behavior is consistent with native tools. If wiring autoVerdict in is complex, a simpler rule is fine for now: autoApprove===true → auto-allow with a log line; otherwise card. Document which you did.
- Idempotent patch entries in scripts/patch_omb_source.py (worktree C:/Users/micha/worktrees/carrier_openmausbot, branch carrier_openmausbot — already exists, verify with git worktree list + branch --show-current). Number them patch 7a/7b/... per file touched, following the existing convention.
- Update docs/omb-patches.md (Patch 7 section; also append one line to Patch 6 pointing at Patch 7 as the actual fix).
- Apply to the live install VIA patch_omb_source.py; node --check both files; restart OMB (taskkill //IM OpenMausBot.exe //F; cmd //c start "" "C:\Users\micha\AppData\Local\Programs\openmausbot\OpenMausBot.exe" — if the harness binds but hangs, force-kill and relaunch once; poll /api/instances with PowerShell Invoke-RestMethod, NOT git-bash curl which false-negatives on this box).
- After any OMB restart, verify decision-tier bots kept engine=codex (a prior restart reverted Helm to claude/sonnet-5 from stale in-memory state). If any reverted, re-PATCH: Helm/Marshal → codex/gpt-5.6-sol, Wrench/Deck/Stacks/Chart/Bosun/Rigger/Surveyor → codex/gpt-5.6-luna, and note it.

## Live verification (the part patch 6 could not do)
1. patch_omb_source.py --check → all entries applied. node --check clean.
2. PATCH Yeoman (8680e15b-da3c-47ee-9ff7-29e838f6710c) → {"instanceId":"claude","model":"claude-haiku-4-5"}.
3. READ test (new task/thread): Composio news search → must relay WITHOUT a Composio card (native tool cards like WebSearch may still appear; deny those and steer to Composio). Proof: MULTI_EXECUTE ok:true, zero Composio-originated request.opened.
4. WRITE test: ask Yeoman to send an email via Gmail Composio to michael+patch7test@example.invalid. EXPECT: approval card (request.opened) for the write-shaped action. DENY via respond API. PROOF REQUIRED: request.opened + request.resolved(deny) in events; NO successful GMAIL_SEND execution (the MULTI_EXECUTE for the send must come back as the denial error, ok:false or error text); bot's reply acknowledges denial.
5. OPTIONAL positive control (safe): a write-shaped no-auth action if one exists; otherwise skip — do NOT approve any real Gmail/GitHub write.
6. Timeout path: trigger one write-shaped call and let it time out ONLY if you shortened the timeout via an env var/config for the test; otherwise skip (do not stall 10 min). Document.
7. Restore Yeoman → ollama::llama3.1:8b-instruct-q4_K_M; verify via GET /api/bots.
8. billing-audit.py → exit 0, only the 2 pilot warnings. omb_composio_health.py → clean. Confirm decision tier still codex 9/9.
9. Cleanup test threads/tasks.

## Commit (NO push)
Commit all repo changes on carrier_openmausbot: "patch7: gate write-shaped Composio actions with real approval cards at connector-proxy". Never amend; separate commits for corrections.

## Output
Report → C:/Users/micha/.openmausbot/buildout/reports/phase2b_patch7_build.md: full diffs, endpoint design chosen and why, live proofs (event excerpts for read-pass-through and write-card-deny), fail-closed evidence, guard-compatibility statement, health/audit outputs, commit SHAs, open risks for Opus.

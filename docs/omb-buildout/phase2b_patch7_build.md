# Phase 2B — Patch 7 Build: Composio Write-Gate at connector-proxy (VERIFIED WORKING)

Build: Sonnet subagent (2 sessions, hit turn limits; orchestrator completed final verification directly).
Date: 2026-08-27. Live install patched via patch_omb_source.py — 13/13 entries applied, node --check clean.

## What patch 7 does (7a–7f, files: connector-proxy.js, index.js)
Write-shaped COMPOSIO_(MULTI_)?EXECUTE_TOOL calls are intercepted at connector-proxy.js (the only layer that
sees the underlying action slug), a REAL permission request is raised in the owning thread
(requestType "permission", tool "Composio: <wrapper>", summary "Run Composio action(s): <slugs>"),
and the relay BLOCKS until resolution. Deny/timeout → the MCP call returns an error text result and the
action is never relayed to Composio. Read-only actions (SEARCH/GET/LIST/FETCH/... + meta tools) relay
through with no card. Fail-closed on ambiguity (unresolved slug = write). New internal harness endpoint(s)
in index.js (7c–7f) create/await/resolve the approval using the same request machinery as native cards,
resolvable via existing POST /api/bots/:id/respond and /api/threads/:id/respond.

## Live verification (event-log proof, threads in ~/.openmausbot/events/)
WRITE test — thread 4cae3a0c-1ffa-41e6-8e85-74181afbb009 (Yeoman on claude-haiku-4-5):
  request.opened  tool="Composio: COMPOSIO_MULTI_EXECUTE_TOOL" summary="Run Composio action(s): GMAIL_SEND_EMAIL"
  request.resolved behavior="deny" source="user"   (denied via respond API)
  NO successful GMAIL_SEND execution followed; bot's reply: "The Gmail send action was denied by the
  permission system..." → WRITE-GATE PASS. (Contrast: pre-patch-7, Phase 2A/2B proved the same call
  executed with zero cards.)
READ test — thread 2966fd69-0ed5-401e-8586-53723508e4a7 (same bot):
  mcp__composio__COMPOSIO_SEARCH_TOOLS ok:true, mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL (news search)
  ok:true, ZERO request.opened events, turn.completed ok:true → READ PASS-THROUGH PASS.
(Note for future scanners: item.completed carries title:null; correlate via item.started.)

## Post-test state (orchestrator-verified)
- Yeoman restored to ollama::llama3.1:8b-instruct-q4_K_M, composio:true, autoApprove:false ✓
- Decision tier codex 9/9 ✓ (survived the patch-7 OMB restart)
- billing-audit.py exit 0, only the 2 expected pilot warnings (Inbox/Yeoman composio) ✓ — guards untouched
- omb_composio_health.py: all 26 bots have explicit composio field ✓
- patch_omb_source.py --check: 13/13 applied ✓

## Honest caveats / open risks for Opus
1. Timeout path (10-min default) NOT live-tested (would stall the test); deny path proven, timeout shares
   the same non-relay code path — verify by inspection.
2. Patch 6a remains in place and remains ineffective on its own (documented in docs/omb-patches.md);
   patch 7 is the actual gate. 6b's classifier is reused by 7.
3. alwaysAllow/autoApprove interplay: verify in diff which rule was implemented (brief allowed simple rule:
   autoApprove=true → auto-allow with log).
4. controlsHost/mcp__computer parity comment in claude.js is unverified (no bot has computer:"local").
5. Build agent hit max-turns twice; final verification/restore/audit/report performed by orchestrator.
   All code however was subagent-written; commit below includes docs + patch entries.

# Phase 1B — Permission Broker Patch Runtime Verification

You are a subagent verifying that 5 previously-applied source patches to OpenMausBot (OMB) actually hold up at runtime. OMB harness is running at http://127.0.0.1:8799.

## Context
OMB source (bundled, editable JS): C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/
Patches (all confirmed statically applied by scripts/check_omb_patches.py in repo C:/Users/micha/carrier_hermes, branch carrier_openmausbot):
1. procs.js — monotonic counter appended to Windows named-pipe broker names (fixes EADDRINUSE race)
2. drivers/claude.js — broker-never-came-up detection
3. drivers/claude.js — broker listen failure surfaces as visible turn error (onBrokerError)
4. index.js — ask_bot from human-initiated turn passes unattended:false
5. index.js — bots invoked via ask_bot (related unattended fix)
Docs: C:/Users/micha/carrier_hermes/docs/omb-patches.md (read it first). Verifier: python3 C:/Users/micha/AppData/Local/hermes/skills/autonomous-ai-agents/openmausbot/scripts/check_omb_patches.py

## Tasks
1. Run the static verifier; confirm 5/5 applied.
2. Read the patched regions in procs.js, drivers/claude.js, index.js and confirm the logic is coherent with the running build (no half-applied or drifted patches, no syntax issues). node --check each patched file.
3. Runtime test A (broker exercise): POST a message to a Claude-engine bot thread via the harness API that forces an action-type tool (e.g. ask the bot to write a small file in its workspace). Poll the thread events NDJSON under C:/Users/micha/.openmausbot/events/ and confirm a request.opened (approval card) event appears rather than a silent deny. DO NOT approve anything destructive; the pending approval itself is the pass signal. Then deny/cancel it via the API if possible.
   - Discover API shape from source: index.js routes (look for app.post/app.get route definitions) — messages, threads, requests endpoints. Document what you find.
4. Runtime test B (pipe-race regression): trigger two back-to-back turns on the same bot (second turn starting right after first finishes) and grep events + any harness logs for EADDRINUSE or "permission broker unavailable". Zero occurrences = pass.
5. Check recent events/ logs (since Aug 25) for any "permission broker unavailable" or EADDRINUSE — should be zero after patches.

## Constraints
- Bot turns may consume subscription quota — use ONE cheap bot for tests: pick a worker bot on an ollama:: model (zero cost) if it uses the claude engine wrapper; otherwise use the least-important claude bot with claude-haiku-4-5 model. Do NOT touch Helm or Marshal.
- Do not modify source files. If you find a patch defect, document it precisely (file, line, expected vs actual) — do not fix.

## Output
Full report to C:/Users/micha/.openmausbot/buildout/reports/phase1b_broker_verify.md: static check, syntax check, API map discovered, runtime test A result (with event excerpts), runtime test B result, log scan, VERDICT per patch (VERIFIED-RUNTIME / VERIFIED-STATIC-ONLY / DEFECT), and any recommended follow-ups.

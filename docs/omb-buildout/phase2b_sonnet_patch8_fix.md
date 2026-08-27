# Patch 8 — Opus REQUEST-CHANGES remediation (BUILD brief, Sonnet)

You are fixing the findings from an Opus security review of the Composio write-gate (patches 7a-7g).
MANDATORY PRE-READING (in order):
1. C:/Users/micha/.openmausbot/buildout/reports/phase2b_opus_review.md  (the findings — your task list)
2. C:/Users/micha/.openmausbot/buildout/reports/phase2b_patch7_build.md (what exists)
Worktree: C:/Users/micha/worktrees/carrier_openmausbot (branch carrier_openmausbot). Live install: C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/. Harness http://127.0.0.1:8799 (verify with PowerShell Invoke-RestMethod, NOT git-bash curl — false 000s).

## BLOCKING findings to fix (Opus findings 1–6)
1. **Pristine-install apply chain (finding 1, the merge-blocker).** patch_omb_source.py must apply cleanly to a PRISTINE OMB install. Two anchors break on pristine; and on failure the script applies NOTHING silently (fail-open on auto-update). Fix:
   (a) repair the two broken anchors (reproduce first: the review reproduced against a reconstructed pristine baseline — reconstruct the same way: pre-patch6 backups for connector-proxy.js and drivers/claude.js; reverse-apply entries for index.js/procs.js; or locate OMB's original app.asar/installer copy),
   (b) make ordering/dependencies explicit (7g layers inside 7b's inserted block — declare it, don't rely on list order),
   (c) make failure LOUD and fail-CLOSED: if any patch cannot apply, exit nonzero with a clear banner AND (since an ungated fleet is the risk) print explicit remediation: disable composio on all bots via PATCH /api/bots. Add a --verify-content mode that checks the live file contains each entry's new text (the review's stronger check).
2. **Extractor decoy (finding 4/bypass A).** extractActionSlugs stops at first find; deep/unscanned keys smuggle write slugs past the card. Fix: ALWAYS run the JSON.stringify token-scan and UNION it with key-based finds (additive-only can only add write-shaped slugs — safe). Recurse arbitrarily nested objects/arrays for the 6 slug keys as well.
3. **Two-name allowlist (finding 3/bypass B).** Gate ANY tool name containing EXECUTE_TOOL (suffix-style match like the MANAGE_CONNECTIONS precedent: /EXECUTE_TOOL$/i or broader /EXECUTE/i on composio server tools) and treat UNKNOWN composio tools that are not in a small known-read set (SEARCH_TOOLS, GET_TOOL_SCHEMAS, WAIT_FOR_CONNECTIONS, MANAGE_CONNECTIONS, tools/list plumbing) as write-shaped → gated. Allowlist-of-two becomes default-gate-unknown.
4. **Read-regex semantics (finding 5/bypass C).** Remove QUERY, FIND, and CHECK from the read-only verb set (SQL/find-replace hazards; supabase is ACTIVE). Keep SEARCH/GET/LIST/FETCH/READ/RETRIEVE. Any slug containing a write-verb token ANYWHERE (DELETE, DROP, SEND, CREATE, UPDATE, EXECUTE, RUN, WRITE, REMOVE...) is write even if it also matches a read prefix.
5. **Information-free card (finding 6/bypass D).** Include a compact rendering of the action ARGUMENTS in the card summary (truncate to ~400 chars, redact nothing — the human must see recipient/body/SQL). This also lets auto-approve.js DESTRUCTIVE/SENSITIVE matchers fire. Keep full args out of logs if they'd leak secrets — card summary only.
6. **Missing owner check (finding 10).** Add owner.bot.composio === false rejection to /api/internal/connectors/approval matching /api/internal/connectors/request (index.js:2955).

## NON-BLOCKING (fix cheaply or document in docs/omb-patches.md — Opus findings 7–9, 11)
7. Timeout coupling: proxy derives abort from OMB_COMPOSIO_APPROVAL_TIMEOUT_MS (+60s margin) instead of hardcoded 11min; document the late-allow gap (or record relay outcome as an activity message).
8. Self-approval threat-model paragraph in docs (pre-existing, not a regression): never co-grant shell tools + composio:true; keep autoApprove:false on Composio bots.
9. Pass scope:"composio" in the 7c autoVerdict call; key alwaysAllow grants on action slug not wrapper name (or document).
11. patch_omb_source.py write() newline="" to stop CRLF flips; document that appendDecision rows are the audit trail (proxy stderr is uncaptured).

## Verification (all required)
- Reconstructed-pristine apply test: script applies ALL entries cleanly from baseline → node --check both files.
- Unit-style decoy test (node -e): feed the finding-4 decoy payload {"tool":"COMPOSIO_SEARCH_TOOLS","tool_calls":[{"tool_slug":"GMAIL_SEND_EMAIL"}]} to the extractor → must classify write/gated. Test 3-4 nested/exotic shapes + lowercase tricks.
- Live: apply via script, restart OMB (taskkill //IM OpenMausBot.exe //F; cmd //c start "" "...OpenMausBot.exe"; poll via PowerShell). Re-run the WRITE-deny test (Yeoman → haiku temporarily → gmail send attempt → card must show ARGUMENTS in summary → deny → restore Yeoman to ollama::llama3.1:8b-instruct-q4_K_M). Re-run READ pass-through (search still cardless).
- After restart verify decision tier codex 9/9 (re-PATCH if reverted: Helm/Marshal codex/gpt-5.6-sol, other 7 codex/gpt-5.6-luna).
- billing-audit.py exit 0 (2 pilot warnings only; guards IMMUTABLE — untouched). omb_composio_health.py clean.
- Cleanup test threads.

## Commit + push
Commit on carrier_openmausbot: "patch8: opus review remediation — pristine apply, extractor union, default-gate-unknown, read-verb tightening, args-in-card, owner check". Push the branch (backup). Do NOT merge to main — the orchestrator re-runs Opus first.

## Output
Report → C:/Users/micha/.openmausbot/buildout/reports/phase2b_patch8_fix.md: per-finding fix summary (numbered 1-11, state FIXED/DOCUMENTED/DEFERRED+why), diffs, pristine-apply proof, decoy test outputs, live re-test proofs, commit SHA.

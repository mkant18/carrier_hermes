# HANDOFF — OMB Buildout: Composio Write-Gate (resume at Patch 8)

**Date:** 2026-08-27 ~04:10 ET · **Session:** Fable orchestrator, subagent-driven development
**Next session's job:** dispatch the Patch 8 remediation build, Opus re-review, merge on APPROVE, then fleet Composio matrix proposal.

## Where we are (one paragraph)
OpenMausBot (OMB) buildout via subagents (Haiku/Sonnet build, Opus review, Fable orchestrates only). Phases 1A/1B/2A done; Composio proven end-to-end; a critical approval-bypass was found (Composio calls skipped approval cards entirely). Patch 6 (first fix) failed honestly; Patch 7 (write-gate at connector-proxy) is BUILT, LIVE, and PROVEN (Gmail send blocked behind a real approval card, denied, not sent). Opus security review returned REQUEST-CHANGES with 6 blocking findings; the Patch 8 remediation brief is fully written and ready to dispatch. Michael halted dispatch for the night.

## Exact resume step
1. Dispatch the build (Michael already approved this plan; re-confirm only if he changed his mind):
   `cd C:/Users/micha/.openmausbot/buildout && claude -p "Read C:/Users/micha/.openmausbot/buildout/briefs/phase2b_sonnet_patch8_fix.md and execute it exactly and completely. Finding 1 (pristine-install apply) is the merge-blocker." --model sonnet --dangerously-skip-permissions --max-turns 200 --output-format json > reports/phase2b_patch8_run.json 2> reports/phase2b_patch8_run.err`
   (run via terminal background=true, notify_on_complete=true)
2. On completion: verify report `reports/phase2b_patch8_fix.md` + commit on `carrier_openmausbot`; if max-turns hit, resume with `--continue` (worked before).
3. Re-run Opus review (brief pattern in reports/phase2b_opus_review.md dispatch; scope = patch 8 commits + re-check findings 1-6 closed).
4. Opus APPROVE → merge `carrier_openmausbot` → `main` + push (Michael's standing instruction: auto-merge on pass, no human gate).
5. Then: fleet-wide Composio rollout matrix proposal → needs Michael's approval (pilot = Yeoman+Inbox only right now).

## Key state
- Repo: `C:/Users/micha/carrier_hermes`; worktree `C:/Users/micha/worktrees/carrier_openmausbot` (branch carrier_openmausbot, head 9c1ba06, pushed).
- Live OMB install patched 13/13 (`scripts/patch_omb_source.py --check`). Harness 8799 up. Patch 7 gate ACTIVE.
- All reports/briefs archived in-repo: `docs/omb-buildout/` (esp. `phase2b_opus_review.md` = the task list, `phase2b_sonnet_patch8_fix.md` = the ready brief).
- Pilot bots Yeoman+Inbox: composio:true, pinned ollama::llama3.1 (model pinning = extra interlock; do NOT bump their model until patch 8 merged).
- Decision tier: codex 9/9 (NO-GROK temp policy; Helm/Marshal=gpt-5.6-sol, leads=gpt-5.6-luna). RESTARTS OF OMB CAN REVERT THIS — re-check after any restart.
- Billing guards IMMUTABLE and passing (exit 0, only 2 expected pilot warnings). Guard is king.
- Composio managed-broker mode live with 5 real connected accounts (GitHub, Gmail x2, GCal, Supabase, Reddit) — why the gate matters.
- 5am daily machine restart CANCELLED by Michael. pre-5am-save cron (4:30) kept as daily backup. Boot-recovery scheduled tasks registered (OMB/watchdog/portproxy).

## Pitfalls for the next agent
- git-bash curl to 127.0.0.1:8799 false-negatives (000) — use PowerShell Invoke-RestMethod or python urllib.
- ollama:: models cannot drive MCP tools (narrate instead) — bump test bot to claude-haiku-4-5 temporarily, ALWAYS restore after.
- /tmp/ doesn't resolve for native python — use C:/Users/micha/AppData/Local/Temp/.
- Never edit billing-audit.py / omg_billing_audit.py / billing_guard.py.
- Worktrees go at sibling paths (C:/Users/micha/worktrees/...), never inside the repo.

## Suggested skills to load
openmausbot, claude-code, carrier-hermes-fleet-ops (if fleet context needed), composio (installed via npx skills, symlinked into Claude Code).

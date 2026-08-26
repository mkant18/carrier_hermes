# Silent Running (EMCON) — Operator Guide & Go-Live Checklist

> **Status:** BUILT & STAGED — all 3 crons **PAUSED**. Not live until Michael authorizes.
> **Author:** Hermes Agent, 2026-08-26
> **Skill:** `silent-running` (autonomous-ai-agents) — the Helm doctrine.
> **Companion skills:** carrier-hermes-fleet-ops, carrier-roster, carrier-kanban-dispatch.

Silent Running is the fleet's AFK autonomous night watch. When Michael's PC is idle
and has spare capacity, the crew works a fixed 7-tier priority ladder **slowly** on
**local LLMs**, staying under **80% CPU/GPU**, checkpointing to git every 10 min with
**zero-LLM** functions, using OAuth only for high-level decisions, memory verification,
and trend analysis. Helm owns the whole process.

## The 7-tier priority ladder

1. **Backlog** — clear all active Kanban tasks (local LLM workers)
2. **Maintenance** — Shipwright pipeline; coding wing assists fixes, research wing assists maintenance research
3. **Memory** — optimize/perfect agent memories via the OpenViking L0/L1/L2 concept; LT + Helm OAuth-verify each change
4. **Cleaning** — remove stale/temp/unused artifacts
5. **Trends** — identify patterns (frequent bot stalls, billing/usage). **OAuth Sonnet/Opus ONLY — never OpenRouter**
6. **Training** — self-optimize from last-48h corrections + optimal production (research investigates best method first)
7. **Features** — Helm+research scout trending GitHub → research picks best → coding plans → Marshal splits to Kanban → dev cycle

## Locked thresholds (with Michael 2026-08-26)

| Setting | Value |
|---|---|
| START gate | input idle ≥ 10 min AND CPU < 40% AND GPU < 40% |
| RUN ceiling (hard cap) | 80% CPU/GPU |
| Pacing | capacity-gated, max 2 concurrent worker units |
| Helm cadence | every 15 min while eligible |
| Checkpoint cadence | every 10 min while active |
| Trend tier | OAuth Sonnet/Opus only, never OpenRouter |

## Components (carrier_hermes/scripts/ → mirrored to ~/.hermes/scripts/)

| Script | Role | LLM |
|---|---|---|
| silent_running_common.py | capacity read (psutil + nvidia-smi + GetLastInputInfo), thresholds, state, gating | zero |
| silent_running_gate.py | cron monitor_script — hash-stable when ineligible (suppresses Helm), fires Helm when eligible | zero |
| silent_running_ladder.py | 7-tier inspector → JSON (top_tier, capacity, gates, concurrency) | zero |
| silent_running_governor.py | 80% brake + exit finalize (no_agent, 2 min) | zero |
| silent_running_checkpoint.py | git WIP commit+push of worker worktrees (no_agent, 10 min) | zero |
| silent_running_memory.py | tier-3 OpenViking memory review queue builder | zero |
| silent_running_trends.py | tier-5 stall + billing/usage digest for OAuth analysis | zero |
| silent_running_broadcast.py | "Silent Running, EMCON" tri-platform ping | zero |

## Staged crons (all PAUSED)

| Job ID | Name | Schedule | Type |
|---|---|---|---|
| d65f527e1ef8 | Silent Running Orchestrator (Helm) | every 15m (monitor_script=gate) | LLM (Helm, OAuth) |
| fade86fd8141 | Silent Running Governor | every 2m | no_agent (zero-LLM) |
| 41dc283bfff6 | Silent Running Checkpoint | every 10m | no_agent (zero-LLM) |

## Control files (carrier/ dir)

- `SILENT_RUNNING_HALT` — create to fully disable; delete to allow.
- `SILENT_RUNNING_BRAKE` — governor-managed; present == pause new spawns (auto).
- `silent_running_state.json` — phase machine + cycle + tier_last_run + capacity.
- Also honors fleet-wide `DISPATCH_LOCK` and `SPEND_HALT`.

## GO-LIVE checklist (do these, in order, when ready to authorize)

1. **Clear the stale DISPATCH_LOCK** if still present (blocks silent-running from starting):
   ```bash
   cat "C:/Users/micha/AppData/Local/hermes/carrier/DISPATCH_LOCK"   # inspect why it's there first
   rm "C:/Users/micha/AppData/Local/hermes/carrier/DISPATCH_LOCK"    # only if safe
   ```
2. **Ensure Ollama can start with the model** (idle watcher toggles HermesOllama; model must be pulled):
   ```bash
   curl -s http://localhost:11434/api/tags   # must list qwen2.5:7b-instruct-q4_K_M
   ```
3. **Confirm the gateway is running** (crons only fire with the gateway up):
   ```bash
   hermes gateway list
   ```
4. **Resume the three crons** (governor + checkpoint first, orchestrator last):
   ```
   cronjob resume fade86fd8141   # governor
   cronjob resume 41dc283bfff6   # checkpoint
   cronjob resume d65f527e1ef8   # orchestrator
   ```
5. **Verify first EMCON**: next time the PC sits idle ≥10 min with CPU/GPU<40%, the
   fleet should post "Silent Running, EMCON" to Discord #fleet + Buzz + Telegram.

## Verification already done (2026-08-26 build)

- All 8 scripts run clean from both carrier_hermes/scripts/ and ~/.hermes/scripts/.
- gate.py prints identical output twice while PC active → will hash-suppress (won't wake Helm).
- ladder.py returns correct top_tier + spawn_allowed under load.
- trends.py surfaced a real stall pattern (pid-not-alive × 3 blocked tasks) and
  confirmed $0 actual cost on 228 anthropic OAuth calls.
- memory.py flagged global MEMORY.md at 86% cap for review.
- broadcast composes the exact phrase "Silent Running, EMCON".
- billing_guard.py PASS (custom/localhost is not a metered provider).

## Go-live executed (2026-08-26)

- **DISPATCH_LOCK diagnosis:** the lock was transient, written at Shipwright
  maintenance run-start (cron `shipwright-maintenance` 75571fa22080, fires
  02/10/18:00). Root cause of the churn: the `code_auditor` (Diver) worker was
  **crash-looping** — spawned, never emitted a heartbeat, reaped at ~60s as
  "pid not alive" (4 crashes in 30 min). Each Shipwright run set the lock; the
  loop churned it. code_auditor is pinned local-LLM-primary (`qwen2.5`, provider
  `custom`) with `fallback: None` — the likely crash cause (first-inference hang /
  no OAuth fallback). **This is a Shipwright-pipeline bug, separate from
  silent-running.**
- **Fix applied:** parked the two zombie audit tasks
  (`e91a2b0a-…` Diver run, `t_4b259dcc` audit) to `blocked`/`human` with an
  explanatory comment, clearing worker_pid/claim/heartbeat so the loop stops.
  Left the deeper code_auditor spawn fix for the maintenance team (flagged, not
  silently rewritten).
- **All three crons RESUMED in order:** Governor fade86fd8141 → Checkpoint
  41dc283bfff6 → Orchestrator d65f527e1ef8. Governor test-fired clean (set the
  `user_active` brake correctly while Michael was at the keyboard). System now
  rests in standby; it will enter EMCON automatically on the next idle ≥10 min
  window with CPU/GPU < 40%.

### Follow-up for the maintenance team (not blocking silent-running)

- Fix `code_auditor` spawn crash: either give it an OAuth fallback in
  `profiles/code_auditor/config.yaml` (currently `fallback: None`), or ensure
  Ollama is warm/reachable for that bot before the Diver step runs. Until then
  the Shipwright Diver step will keep crashing when the maintenance cron fires.

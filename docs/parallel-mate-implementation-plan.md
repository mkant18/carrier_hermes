# Parallel-Mate Fleet Dispatch — Implementation Plan

**Job ID:** PARALLEL-MATE-PLAN-01
**Author:** Wrench 🔧 (coding_lt)
**Date:** 2026-08-26
**Input:** `carrier_hermes/docs/parallel-mate-architecture-research.md` (Probe, PARALLEL-MATE-RESEARCH-01)
**Status:** PLAN ONLY — no code written. Mate executes against this.

---

## 1. Architecture — Target State

### 1.1 Dispatch Model (Crewmate, not Secondmate)

Wrench dispatches N concurrent ephemeral Mate instances via `kanban_create`. Each Mate
instance is a single Kanban task row (`assignee: firstmate`, `workspace_kind: worktree`)
with a unique `t_<hex>` task id. Mate instances are task-scoped workers — they live and
die per job. This is the **crewmate** model: one Wrench, N disposable Mates, not N
independent Mate homes (the secondmate model is explicitly out of scope here).

### 1.2 ASCII Diagram

```
                         WRENCH (coding_lt)
                              |
              pre-dispatch check (kanban_list count + path overlap)
              |
              +-- kanban_create(assignee=firstmate, workspace_kind=worktree)
              |
    +---------+---------+---------+
    |         |         |         |
  Mate-1    Mate-2    Mate-3    Mate-N
  t_<aaa>   t_<bbb>   t_<ccc>   t_<...>
    |         |         |         |
 .worktrees/ .worktrees/ .worktrees/ .worktrees/
 t_<aaa>/   t_<bbb>/   t_<ccc>/   t_<...>/
    |         |         |         |
  branch    branch    branch    branch
  wt/t_aaa  wt/t_bbb  wt/t_ccc  wt/t_...
    |
  kanban_complete(summary, metadata, paths_touched[])
    |
    +---------+---------+---------+
                        |
              AGGREGATOR TASK (optional)
              kanban_create(parents=[t_aaa, t_bbb, ...])
              promotes only when ALL parents done
                        |
                     WRENCH
                  review + trap
```

### 1.3 Concurrency Model

- **Default cap:** 3 concurrent Mate instances (conservative given shared Claude Max ITPM
  pool across Helm, Marshal, all Lts). This is the recommended starting point pending
  Michael's decision in §6.
- **Enforcement:** Wrench-side pre-dispatch count check via `kanban_list`. Before any
  `kanban_create(assignee='firstmate', ...)`, Wrench counts current rows with
  `assignee='firstmate' AND status IN ('running', 'ready')`. If count >= cap, Wrench
  holds the dispatch in its own sortie queue and reports the hold to #fleet.
- **Per-task isolation boundary:** each Mate instance has exactly one Kanban task row,
  one git worktree at `.worktrees/t_<task_id>/`, one branch `wt/t_<task_id>`, and one
  claims file at `_agent/state/firstmate-fleet/t_<task_id>.json`. No two concurrent
  Mates share any of these.
- **Path exclusivity:** no two concurrently running or ready Mate tasks may declare
  overlapping paths in their `target_paths[]` field. Wrench checks this at dispatch time
  by reading all running/ready Mate task claims files.

---

## 2. Implementation Phases

### Phase 0 — Worktree GC + Packet Template Standardization

**Goal:** Fix the two issues that exist TODAY before multiplying worktree creation rate.
These changes are deployable at N=1 and prove the packet template in production before
concurrency is raised.

**Dependencies:** none (first in sequence)

**Files to create or modify:**

```
carrier_hermes/
  scripts/
    worktree_gc.sh              [CREATE]
  docs/
    job-packet-template.md      [CREATE]
  profiles/coding_lt/
    SOUL.md                     [MODIFY — add packet template reference + pre-dispatch check]
```

**worktree_gc.sh** — a no-agent bash script run weekly via cron:
1. List all paths under `.worktrees/*/`.
2. For each worktree, extract the task id from the directory name.
3. Query the Kanban DB: `SELECT status FROM tasks WHERE workspace_path LIKE '%<task_id>%'`.
4. If status is `done` or `archived` and the task completed more than 7 days ago: run
   `git worktree remove --force <path>` and log to `_agent/coding_lt/worktree_gc.log`.
5. If no matching Kanban row exists (orphan): same removal + log.
6. Print a summary line for cron delivery.

**job-packet-template.md** — the canonical Wrench→Mate packet shape:
```
# Job Packet — Wrench → Mate | <JOB-ID>
mate_instance_id: mate-<N>-of-<total>    <!-- e.g. mate-1-of-3 -->
from: coding_lt
to: firstmate
created_at: <ISO8601>
branch: hermes/<project>/<short>
worktree: required
target_paths:
  - <path relative to repo root>
  - <path relative to repo root>

## Mission
<what to build — plain English, self-contained>
Repo root: <absolute path>

## Context (self-contained)
<all facts Mate needs — no assumed shared history with Wrench or Helm>

## Acceptance criteria
<what done looks like — specific, testable>

## Out of scope
<explicit list of what Mate should NOT touch>
```

**Acceptance criteria for Phase 0:**
- `worktree_gc.sh` exists, is executable, and a dry-run produces correct output on the
  current orphan worktrees (e.g. `ws01-install`, any task-id worktrees whose Kanban row
  is `done`/`archived`).
- `job-packet-template.md` is written and reviewed by Michael.
- Wrench uses the new template for the very next single-Mate dispatch and the packet
  passes review with no missing fields.
- `coding_lt` SOUL.md updated to reference the template and the pre-dispatch check.

---

### Phase 1 — Claims Ledger + Wrench Pre-Dispatch Check

**Goal:** Populate the already-designed-but-empty `_agent/state/firstmate-fleet.json`
claims schema, restructured into per-task-id files, and teach Wrench to check it before
every dispatch.

**Dependencies:** Phase 0 (packet template must be standardized first so `target_paths[]`
is machine-readable)

**Files to create or modify:**

```
carrier_hermes/
  _agent/state/firstmate-fleet/
    .gitkeep                    [CREATE — initialize the directory]
    <task_id>.json              [runtime, written by Mate at start, read by Wrench]
  schemas/
    firstmate_fleet_instance.schema.json   [CREATE — per-instance schema]
  scripts/
    check_mate_claims.py        [CREATE — Wrench's pre-dispatch path-overlap checker]
  profiles/coding_lt/
    SOUL.md                     [MODIFY — add explicit pre-dispatch check procedure]
  profiles/firstmate/
    SOUL.md                     [MODIFY — add claims file write-on-start procedure]
```

**Per-instance claims file schema** (`_agent/state/firstmate-fleet/<task_id>.json`):
```json
{
  "task_id": "t_<hex>",
  "mate_instance_id": "mate-1-of-3",
  "job_id": "<JOB-ID>",
  "status": "running",
  "branch": "hermes/foo/short",
  "worktree": ".worktrees/t_<hex>/",
  "target_paths": [
    "scripts/foo.py",
    "tests/test_foo.py"
  ],
  "dispatched_at": "<ISO8601>",
  "completed_at": null
}
```

**check_mate_claims.py** — run by Mate or a cron as a helper; Wrench reads its output
via `kanban_show` on a dedicated checker task (since Wrench has no terminal tool):
- Input: proposed `target_paths[]` and `branch` for the new dispatch.
- Reads all `_agent/state/firstmate-fleet/*.json` where `status == "running"`.
- Outputs: CLEAR (no overlap) or CONFLICT (lists conflicting paths + owning task id).
- Writes result to `_agent/coding_lt/preflight_<timestamp>.json` for Wrench to read.

**SOUL.md changes for firstmate:**
- On task start, write `_agent/state/firstmate-fleet/<task_id>.json` with `status: running`.
- On `kanban_complete`, update `status: done` and set `completed_at`.

**SOUL.md changes for coding_lt (Wrench):**
- Before every `kanban_create(assignee='firstmate', ...)`:
  1. Count running/ready Mate rows via `kanban_list`. If count >= cap: hold and report.
  2. Read all `_agent/state/firstmate-fleet/*.json` (via file tool, which Wrench has).
  3. Check proposed `target_paths[]` against all running claims. If overlap: hold and
     report conflict to Helm. Never dispatch into a conflict.

**Acceptance criteria for Phase 1:**
- `_agent/state/firstmate-fleet/` directory exists with `.gitkeep`.
- `firstmate_fleet_instance.schema.json` written and matches the per-instance shape above.
- `check_mate_claims.py` runs without error on the current repo state.
- A simulated dispatch with overlapping paths produces a CONFLICT output.
- `firstmate` SOUL.md updated; the next Mate task start writes its claims file correctly.
- `coding_lt` SOUL.md updated; pre-dispatch procedure is in the active session protocol.

---

### Phase 2 — Extend Stall Watcher for Per-Instance Liveness

**Goal:** Upgrade `coding_stall_watcher.py` to understand N concurrent Mate instances
and add worktree-write liveness checking so a genuinely-working Mate is not false-positive
flagged as stalled.

**Dependencies:** Phase 1 (claims ledger gives per-instance identity; needed to report
which Mate-N of M is stalled, not just "a task with some title")

**Files to create or modify:**

```
carrier_hermes/
  scripts/
    coding_stall_watcher.py     [MODIFY]
  cron/
    stall_watcher.cron.yaml     [MODIFY if needed — confirm schedule is <= 30min interval]
```

**Changes to `coding_stall_watcher.py`:**

1. **Per-instance identity in alerts.** Read `_agent/state/firstmate-fleet/<task_id>.json`
   for each stalled task to get `mate_instance_id` and `job_id`. Include these in the
   AIPass alert so Wrench's inbox message says "mate-2-of-3 (job JOB-ID) is stalled"
   rather than just a task id string.

2. **Worktree-write liveness check.** Before flagging a task as stalled:
   - Read the task's `worktree` path from its claims file.
   - Walk the worktree directory (bounded: max 200 files, max 5 seconds).
   - Find the newest `mtime` across all files.
   - If `newest_mtime > task.started_at + 30_minutes AND newest_mtime > now - 10_minutes`:
     the Mate is writing files — log "provably working (file activity)" and skip the alert.
   - Only escalate if no recent file activity AND 30-min clock has elapsed.

3. **Concurrency-aware summary.** The cron run's summary line should report:
   `"N Mate instances running: M stalled (escalated), K provably working (skipped)"`.

4. **Alert format update.** AIPass alert to Wrench inbox:
   ```
   STALL_ALERT | mate-<N>-of-<total> | <job_id> | task <task_id>
   Status: running for <elapsed> with no heartbeat or file activity.
   Last known worktree activity: <timestamp or NONE>.
   Recommended action: [check AIPass inbox | reset to ready | escalate to Helm]
   ```

**Acceptance criteria for Phase 2:**
- `coding_stall_watcher.py` updated and runs without error on the current repo.
- A simulated stalled task (claims file present, no recent worktree writes) produces an
  AIPass alert with `mate_instance_id` and `job_id` in the body.
- A simulated working task (recent worktree writes) is correctly skipped (no alert).
- Cron schedule confirmed at 30-min or less; cron config updated if needed.

---

### Phase 3 — Raise Concurrency Cap + Fan-In Aggregator

**Goal:** Raise the active concurrency cap from 1 to Michael's chosen N (default
recommendation: 3). Wire up the `kanban_create(parents=[...])` fan-in pattern for jobs
that decompose into multiple parallel Mate instances.

**Dependencies:** Phase 2 (stall watcher must be N-aware before running N Mates in
production; Phase 1 must be in place for conflict avoidance)

**Files to create or modify:**

```
carrier_hermes/
  profiles/coding_lt/
    SOUL.md                     [MODIFY — document fan-in pattern, set N cap value]
  docs/
    parallel-mate-playbook.md   [CREATE — Wrench's operational guide for multi-Mate jobs]
```

**Fan-in pattern (Wrench SOUL.md addition):**

When a coding job decomposes into N parallel sub-tasks with non-overlapping paths:

1. Verify N <= concurrency cap via `kanban_list` count check.
2. For each sub-task, verify non-overlapping paths via claims ledger check.
3. Create N Mate task rows: `kanban_create(assignee='firstmate', workspace_kind='worktree', ...)`.
   Record all N task ids as `mate_task_ids`.
4. Create one aggregator/review task: `kanban_create(assignee='coding_lt', parents=mate_task_ids)`.
   This aggregator only becomes `ready` when all N Mate tasks reach `done`.
5. Post `🛫 DISPATCH | Wrench → Mate-1..N | <JOB-ID>` to #fleet with all N task ids.
6. On aggregator activation: read each Mate task's `kanban_show()` summary + metadata.
   Verify all return packets are complete (status, branch, tests_run, paths_touched[],
   blockers[]). If any incomplete, send back to that Mate with the specific missing field.
7. Consolidate and return a single result packet to Helm.
8. Post `🛬 TRAP | Wrench | <JOB-ID> <outcome>` to #fleet.

**parallel-mate-playbook.md** — Wrench's field reference covering:
- When to decompose a job into parallel Mates vs. keep it serial.
- How to split a job into non-overlapping sub-tasks (by directory, by concern, by test vs.
  implementation).
- The full pre-dispatch checklist: preflight → count check → path check → dispatch.
- What to do on stall alert (per Phase 2 alert format).
- What to do when a Mate's return packet is incomplete.
- When to escalate to Helm vs. retry Mate directly.

**Acceptance criteria for Phase 3:**
- `coding_lt` SOUL.md updated with cap value (N) and fan-in pattern.
- `parallel-mate-playbook.md` written and reviewed by Michael.
- First real parallel dispatch (2 concurrent Mates, non-overlapping paths) completes
  successfully: both tasks reach `done`, aggregator promotes, Wrench consolidates and
  traps to Helm.
- Zero path conflicts observed (claims check prevented overlap).
- Zero orphaned worktrees after task completion (GC script cleans up).

---

### Phase 4 — Soak Test + Steady-State Tuning

**Goal:** Run the fleet at low concurrency (2 Mates) for 2 weeks, measure real per-turn
token usage, then decide whether to raise the cap toward Michael's ultimate target.

**Dependencies:** Phase 3 (all prior phases must be complete and stable)

**Files to create or modify:**

```
carrier_hermes/
  docs/
    parallel-mate-soak-log.md   [CREATE — running log of soak-test observations]
  scripts/
    mate_token_usage_summary.py [CREATE — query Hermes usage or Anthropic logs for per-task
                                           token burn, compute average per Mate turn]
```

**Soak test protocol:**
1. Run 5+ real coding jobs with 2 concurrent Mates over 2 weeks.
2. After each job: log actual ITPM consumed (from Anthropic usage endpoint or proxy logs),
   wall-clock time, stall events, and conflict-avoidance interventions in `soak-log.md`.
3. Compute average tokens per Mate turn. Project: how many concurrent Mates can run
   before the shared Claude Max ITPM pool (2M ITPM at Tier 4) hits 50% saturation across
   all bots?
4. Based on measurements, decide whether to raise cap from 2 to 3 (recommended default)
   or to 4 (aggressive).
5. Update the concurrency cap in `coding_lt` SOUL.md and `parallel-mate-playbook.md`.

**Acceptance criteria for Phase 4:**
- At least 5 successful 2-Mate parallel jobs completed without stalls or conflicts.
- `soak-log.md` contains per-job token usage observations.
- A decision on final concurrency cap is recorded and SOUL.md is updated with it.
- No 429 rate-limit errors observed on other bots (Helm, Marshal, other Lts) during
  Mate fleet operation.

---

## 3. Supervision Design

### 3.1 State File Naming Convention

Per-instance state lives at:

```
_agent/state/firstmate-fleet/
  <task_id>.json     -- written by Mate at task start; updated at done
```

This mirrors firstmate's `state/<task_id>/` per-directory convention and avoids all
concurrent-write races (each Mate writes only its own file). Wrench reads them all for
the pre-dispatch check and the aggregator review.

No shared "fleet state" single file — the original `_agent/state/firstmate-fleet.json`
schema (which was never populated) is superseded by this per-instance structure. The
existing `schemas/firstmate_fleet.schema.json` is retired; the new per-instance schema
is `schemas/firstmate_fleet_instance.schema.json`.

### 3.2 How Wrench Monitors Completion

Two channels, both already exist or are low-cost extensions:

**Channel A — Kanban dependency gate (zero new work):**
The aggregator task created in Phase 3 (`kanban_create(parents=[mate1, mate2, ...])`)
only promotes to `ready` when all parents are `done`. The Hermes dispatcher handles
this automatically. Wrench activates as the aggregator's assignee and runs its review.
This is the primary, zero-cost completion signal.

**Channel B — Stall watcher (Phase 2 extension):**
`coding_stall_watcher.py` (extended in Phase 2) sends an AIPass alert to Wrench's inbox
if any Mate instance is stalled (running > 30 min with no heartbeat and no worktree file
activity). Wrench checks its AIPass inbox on each activation and acts on alerts per the
playbook.

There is no LLM-based polling loop — the bash/Python watcher does the O(N) monitoring
for $0, and only surfaces genuine stalls to Wrench (the O(1) LLM-tier supervisor). This
matches firstmate's "zero-token under normal churn" design exactly, using Hermes-native
primitives instead of firstmate's bash watcher.

### 3.3 What Wrench Does When a Mate Stalls or Fails

On receiving a `STALL_ALERT` AIPass from `coding_stall_watcher.py`:

1. Read the alert fully. Identify: `mate_instance_id`, `job_id`, `task_id`, elapsed time.
2. Post `⚠️ BOLTER | Wrench | <task_id> stalled — diagnosing` to #fleet.
3. Call `kanban_show(task_id=<task_id>)` to read the task's current state and comment thread.
4. Diagnose:
   - **Recoverable (missing info, wrong path):** write a clarifying AIPass to Mate's
     inbox with the correction. Reset the task to `ready` (via Kanban block/unblock
     or by noting it for Marshal). Post recovery outcome to #fleet.
   - **Unrecoverable (missing tool, human gate needed):** escalate to Helm with full
     blocker context. Post `⚠️ BOLTER | Wrench | <task_id> — escalating to Helm` to #fleet.
5. If a Mate task crashes (`outcome: crashed`): Hermes dispatcher automatically re-queues
   it as `ready`. Wrench checks if re-dispatch is still safe (path not claimed by another
   running Mate) before the task auto-restarts.

### 3.4 Avoiding Quota Saturation

Three defensive layers:

1. **Pre-dispatch count check (Phase 1):** never create a new Mate task if count of
   running/ready Mate tasks >= cap. Holds new work in Wrench's sortie queue.
2. **Stagger dispatch timing:** when decomposing a job into N parallel Mates, create
   each task row in sequence with a brief inter-dispatch gap (not simultaneous start) to
   avoid N large initial context windows hitting the API at the same second.
3. **Soak-phase measurement (Phase 4):** real per-turn token usage informs the final
   cap. If measurements show headroom, cap goes up. If other bots are seeing 429s during
   fleet operation, cap goes down immediately — Wrench reduces the active count by
   blocking the lowest-priority Mate and not re-dispatching until 429s clear.

---

## 4. Dispatch Contract Changes (Before / After)

### Before (current state — two coexisting ad-hoc shapes)

**Shape A (t_e8b8e392 pattern — markdown):**
```
# Job Packet — Wrench → Mate | <JOB-ID>
## Mission
<what to build>
Repo root: <path>
Target file(s): <prose, not a list>
Branch: hermes/<project>/<short>
## Context you need
<all facts>
```

**Shape B (t_5e0ae4a3 pattern — YAML-ish header):**
```
job_id: <id>
from: coding_lt
to: firstmate
created_at: <date>
priority: high
shadow_mode: false
michael_visible_summary: <prose>
## Goal
<what to build>
## Context (self-contained)
<all facts>
```

Problems with current shapes:
- No `mate_instance_id` field (cannot distinguish Mate-1 from Mate-2 in fleet logs).
- `target_paths[]` is prose, not a parseable list (blocking conflict-avoidance check).
- `worktree: required` assertion is missing (must be explicit per INTER_AGENT_PROTOCOL).
- No `acceptance_criteria` section (Mate must infer done-ness from prose mission).
- Two shapes means Mate parses inconsistently; any machine-checks must handle both.

### After (standardized template — Phase 0)

```
# Job Packet — Wrench → Mate | <JOB-ID>
mate_instance_id: mate-<N>-of-<total>
from: coding_lt
to: firstmate
created_at: <ISO8601>
branch: hermes/<project>/<short>
worktree: required
target_paths:
  - <path relative to repo root>
  - <path relative to repo root>

## Mission
<what to build — plain English, self-contained>
Repo root: <absolute path>

## Context (self-contained)
<all facts Mate needs — no assumed shared history with Wrench or Helm>

## Acceptance criteria
<what done looks like — specific, testable>

## Out of scope
<explicit list of what Mate should NOT touch>
```

Changes from before to after:
- `mate_instance_id` added (required; e.g. `mate-1-of-1` for solo dispatch).
- `target_paths[]` is now a YAML-style list (machine-checkable for conflicts).
- `worktree: required` made explicit.
- `acceptance_criteria` section added (eliminates "done when I think so" ambiguity).
- `out_of_scope` section added (prevents path creep into other Mates' declared files).
- Single canonical shape replaces two ad-hoc shapes.

The `mate_instance_id` field is `mate-1-of-1` for all solo dispatches — this means the
template is backward compatible with N=1 use; Mate receives the same format whether
alone or in a fleet.

---

## 5. Risks and Mitigations

### Risk 1 — Worktree Conflicts (Two Mates Write the Same File)

**Severity:** High. Two Mates writing the same file in their respective worktrees will
produce a merge conflict when branches are integrated, wasting a full turn of work.

**Mitigation:** Phase 1 claims ledger + pre-dispatch path check. Wrench checks all
running Mate claims files for `target_paths[]` overlap before creating a new Mate task.
If overlap detected, dispatch is held and Wrench re-scopes the job. Git conflict is the
backstop (catches transitive overlaps the explicit list misses), not the primary guard.

### Risk 2 — Quota Drain (N Mates + Wrench + Marshal Saturate Claude Max Pool)

**Severity:** High. Multiple long coding turns (tens of thousands of tokens each) run
concurrently against the shared Claude Max Sonnet ITPM pool (2M ITPM at Tier 4, shared
across all bots). A single bad run of 3 Mates doing large refactors could hit 429s on
Helm and Marshal simultaneously.

**Mitigation:** Conservative starting cap (2 Mates, not 3) during Phase 4 soak.
Pre-dispatch count check prevents exceeding cap. Stall watcher catches wedged Mates
burning context without completing so they can be cut off early. If 429s observed on
other bots: immediately reduce cap to 1 (effectively serial) until saturation clears.

### Risk 3 — Claims File Not Written (Mate Starts Without Registering)

**Severity:** Medium. If a Mate instance starts work before writing its claims file
(e.g. crashes in the first turn before the write step), the conflict-avoidance check
has no record of its paths, and a second Mate could be dispatched into a real overlap.

**Mitigation:** Mate SOUL.md updated (Phase 1) to make claims file write the FIRST
action on task start, before any code reading or writing. The `kanban_show()` call at
the top of every Mate turn is already the first action; claims file write is added
immediately after. The write is idempotent (same task_id = same file, safe to re-write
on retry). Wrench also cross-checks running Mate task ids against existing claims files
and flags missing ones as a preflight warning.

### Risk 4 — Stale Claims Files (Done Mate's File Not Updated, Blocking Future Dispatch)

**Severity:** Medium. If a Mate task completes without updating its claims file to
`status: done`, Wrench's pre-dispatch check will see a "running" claims file for a
completed task, potentially blocking a legitimate new dispatch.

**Mitigation:** `worktree_gc.sh` (Phase 0) cross-references claims files against Kanban
task status and removes/marks stale files where the Kanban row is `done`/`archived`.
This runs weekly. Wrench's pre-dispatch check also cross-validates claims file
`status: running` against the Kanban row's actual status — if they disagree, the claims
file is ignored and Wrench logs a hygiene warning.

### Risk 5 — Fan-In Aggregator Activated Before All Mates Are Actually Done

**Severity:** Low — Hermes's `parents=[]` dependency gate already prevents this by
design; the aggregator only promotes when ALL parent task ids reach `done` state in the
Kanban DB. This is a documented, tested Hermes primitive.

**Residual risk:** a Mate task marked `done` by Wrench's review before it actually
merged its branch. Mitigation: Wrench's aggregator review step checks that each Mate's
`branch` and `paths_touched[]` are present in the return packet before calling
`kanban_complete` on the Mate task.

---

## 6. Open Decisions — Michael Must Answer Before Phase 3

These questions are flagged to Marshal to surface to Helm (Michael).

| # | Question | Options | Probe Recommendation |
|---|----------|---------|----------------------|
| OD-1 | Max concurrent Mate instances (the cap)? | (a) 2, (b) 3, (c) 4, (d) no cap / 429-backpressure | (b) 3 — conservative given shared ITPM pool; measure at 2 during soak before raising |
| OD-2 | Stall watcher interval: 30 min (current) or tighter? | (a) keep 30 min, (b) reduce to 15 min, (c) add a worktree-mtime heartbeat at 10 min | (a) keep 30 min — the worktree-write liveness check in Phase 2 handles false positives; interval change adds little at this concurrency level |
| OD-3 | Mate tasks stay on shared `carrier` board or get their own `coding` board? | (a) stay on `carrier` board, Wrench-side count check, (b) dedicated `coding` board, use `kanban.max_in_progress` natively | (a) stay on shared board — avoids migration cost; Wrench already has `kanban_list` |
| OD-4 | Restructure `_agent/state/firstmate-fleet.json` → per-instance files (Phase 1) or keep single file + locking? | (a) per-instance files (recommended), (b) single file + flock/lockfile | (a) per-instance — matches firstmate pattern, avoids Windows-host locking fragility, no migration cost (file never populated) |
| OD-5 | Who builds `worktree_gc.sh` — in scope as Phase 0 or deferred to Shipwright wing? | (a) in scope, Mate builds it as first coding task, (b) defer | (a) in scope — orphans exist today; cheap to fix before multiplying worktree creation |
| OD-6 | Should Mate's return packet format be validated by a schema checker (small script) or remain advisory (SOUL.md instruction only)? | (a) add a schema validation step in the aggregator task, (b) advisory only | (a) schema validation — when N Mate packets are aggregated, a missing field in one silently corrupts the consolidated report; better to catch it structurally |

**Marshal note:** OD-1 (concurrency cap) and OD-5 (worktree GC scope) must be resolved
before Phase 2/3 work is dispatched. OD-2, OD-3, OD-4, and OD-6 can be decided at or
before Phase 1 starts.

---

## 7. Execution Handoff — For Marshal

When this plan is approved and Michael's OD answers are in, Marshal should create the
following Kanban tasks in order:

**Phase 0 tasks (can dispatch immediately, no dependencies):**
1. `assignee: firstmate` — Build `scripts/worktree_gc.sh` per §2 Phase 0 spec.
   `workspace_kind: worktree`. `target_paths: scripts/worktree_gc.sh, cron config update`.
2. `assignee: firstmate` — Write `docs/job-packet-template.md` per §4 After spec.
   `workspace_kind: scratch`. (Documentation only — no code.)

**Phase 0 SOUL update (Wrench does this, not Mate):**
3. `assignee: coding_lt` — Update `coding_lt` SOUL.md to reference packet template and
   add pre-dispatch check protocol. Depends on task 2 above.

**Phase 1 tasks (depend on Phase 0 tasks 1 and 2 being done):**
4. `assignee: firstmate` — Create `_agent/state/firstmate-fleet/` directory, write
   `.gitkeep`, write `schemas/firstmate_fleet_instance.schema.json`, write
   `scripts/check_mate_claims.py`. Depends on Phase 0 tasks.
5. `assignee: coding_lt` (or `firstmate`) — Update `firstmate` SOUL.md with claims file
   write-on-start procedure. Depends on task 4.
6. `assignee: coding_lt` — Update `coding_lt` SOUL.md with pre-dispatch claims check
   procedure. Depends on task 4.

**Phase 2 tasks (depend on Phase 1):**
7. `assignee: firstmate` — Modify `scripts/coding_stall_watcher.py` per §2 Phase 2 spec.
   Depends on Phase 1 tasks.

**Phase 3 tasks (depend on Phase 2 + Michael's OD answers):**
8. `assignee: firstmate` — Write `docs/parallel-mate-playbook.md` per §2 Phase 3 spec.
9. `assignee: coding_lt` — Update `coding_lt` SOUL.md with fan-in pattern and confirmed
   cap value (from OD-1). Depends on OD-1 answer.

**Phase 4 (soak — Wrench-led, no new Mate dispatch tasks):**
10. Run 5+ real 2-Mate parallel jobs, log results in `docs/parallel-mate-soak-log.md`.
    Create `scripts/mate_token_usage_summary.py`. Decide final cap. Update SOUL.md.

---

*Plan complete. All Mate-executed phases are self-contained coding tasks — no plan-document
changes required during implementation. Wrench reviews each Mate return packet for
`status`, `branch`, `tests_run`, `paths_touched[]`, `blockers[]` before marking done.*

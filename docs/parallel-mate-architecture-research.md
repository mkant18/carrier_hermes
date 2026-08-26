# Parallel-Mate Fleet Pattern — Architecture Research

**Job ID:** PARALLEL-MATE-RESEARCH-01
**Author:** Probe 🔭
**Date:** 2026-08-26
**Sources:**
- https://github.com/kunchenguid/firstmate (README, AGENTS.md, docs/architecture.md — fetched via raw.githubusercontent.com)
- `carrier_hermes` repo: `ARCHITECTURE.md`, `COST_MODEL.md`, `docs/INTER_AGENT_PROTOCOL.md`, `RISKS.md`, `bots/BOT_MATRIX.md`
- `carrier_hermes/profiles/firstmate/SOUL.md`, `profiles/coding_lt` (no SOUL.md exists — see §2)
- Live Kanban board `carrier` (`kanban.db`): task bodies for `t_e8b8e392`, `t_518f43da`, `t_5e0ae4a3`, `t_9beca9b2`, worktree rows
- `carrier_hermes/.worktrees/` (6 live worktrees inspected), `git worktree list`
- `carrier_hermes/scripts/` (dispatch_lock.sh, dispatch_preflight.sh, coding_stall_watcher.py, blocked_task_watchdog.py)
- Hermes docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban, /delegation
- Hermes config: `~/.hermes/config.yaml`, `~/.hermes/profiles/{firstmate,coding_lt}/config.yaml`

**Confidence markers:** high = read directly from source/repo; medium = inferred from consistent patterns across multiple files; low = no direct evidence, best-guess.

---

## §1 — firstmate supervision engine (deep read)

**Important caveat (confidence: high):** the firstmate `docs/architecture.md` on GitHub is written in an extremely dense, jargon-heavy style (its own internal vocabulary: "wedge," "no-verb," "provably-working," "worktree-write deferral") and several of its cross-references point at scripts/docs not fetched here (`bin/fm-crew-state.sh`, `bin/fm-classify-lib.sh`, full `docs/tmux-backend.md`, etc.). The synthesis below is accurate to what was retrieved (README.md, AGENTS.md, and the architecture.md sections reachable via extraction), but the *exact* bash logic inside `bin/fm-watch.sh` was not visible in raw form — GitHub's markdown render strips code blocks from the API-extracted text. Treat the "how it works" claims as **architecture-level (medium-high confidence)**, not line-by-line verified.

### Zero-token bash watcher (`bin/fm-watch.sh`)
- Runs as a persistent bash process outside the LLM loop — literally zero tokens burned while idle.
- Sleeps on the fleet (polls per-task state directories on an interval) and **classifies wakes in bash**, not via an LLM call.
- Only wakes the first mate (spawns/notifies the primary agent session) when a wake is **actionable**. Benign/no-verb signals (e.g. "still working" status pings) are absorbed silently.
- Actionable wake categories (verbatim from source): captain-relevant status signals, no-verb signals whose crew is *not* provably working, authenticated check output (PR merge polling, mention polling), stale panes not provably working, provably-working stale panes past `FM_STALE_ESCALATE_SECS`, declared external waits past `FM_PAUSE_RESURFACE_SECS`, and heartbeat backstop hits.
- Wakes are written to a **durable local queue** (`state/.wake-queue`) *before* any side-effecting action, so an interrupted watcher can recover the queue without losing events. This is the key resilience property: state lives on disk, not in the watcher's memory.

### State files
Per-task runtime state lives under `state/` inside the firstmate home (`FM_HOME`), one row/file set per task id:
- `state/<id>/.status` — append-only log of wake-event lines (`kind: note`). **Not** a "current state" snapshot — it's an event log. Current-state reconciliation is a separate read (`bin/fm-crew-state.sh <id>`).
- `state/<id>/.turn-ended` — touched by a turn-end hook; used to detect an agent that stopped without doing anything ("blind stop").
- `state/<id>/.meta` — spawn metadata (backend, timestamps, trace context).
- `state/<id>/.wake-queue` — durable queue of pending actionable wakes, epoch|seq|kind|key|payload format, acknowledged only after the handling turn completes.
- `state/<id>/.watcher-down` — generation-bound recovery marker coupling watcher downtime to safe wake-queue replay.
- Dozens of narrower sidecar files (`.hash-*`, `.stale-*`, `.paused-*`, `.wedge-escalations-*`, `.writing-*`) are described as "watcher internals; never touch" — i.e. private to the bash watcher's own bookkeeping, not part of the contract other tooling should read.

### Worktree assignment per crewmate
- Each dispatched task ("ship" or "scout") gets a **clean, disposable git worktree**, provisioned by a companion tool ([`treehouse`](https://github.com/kunchenguid/treehouse)) or an Orca-managed worktree when `backend=orca`.
- Crewmates never touch the firstmate operator's own checkout directly — worktrees are the sole isolation boundary preventing two parallel tasks from clobbering each other's working tree state.
- The worktree record (which task owns which worktree path) is itself watched: the supervision engine checks for files newer than the start of a pane's "quiet window" *inside that task's recorded worktree* as a liveness signal independent of terminal-pane output — i.e. "is this crew actually writing files" is a first-class supervision signal, not just "is the pane producing text."

### Actionable vs. benign wake detection ("no-verb" distinction)
- A **"no-verb" signal** is a status line that doesn't itself assert an actionable verb (e.g. a bare "still here" ping) — these are benign *only if* `bin/fm-crew-state.sh` independently confirms positive evidence the crew is still working (an actively running step attributed to that crew's own code, or matching file-write evidence).
- If no positive evidence exists, the same no-verb wake becomes actionable (crew may be stuck/dead).
- This is the mechanism that keeps the watcher **zero-token under normal churn**: routine "I'm still working" chatter from N parallel crewmates does not by itself wake (and burn tokens on) the supervising first mate.

### "No-verb / provably-working" distinction (why it matters for concurrency)
This is the crux of what makes concurrent supervision *cheap*. Firstmate is explicitly designed so that supervising N crewmates does not cost O(N) LLM turns per polling interval — the bash watcher does the O(N) work for $0, and only escalates the O(1) genuinely-actionable events up to the LLM-backed first mate. Without this distinction, a naive "poll N tasks, ask an LLM to decide if each is fine" design would burn tokens linearly with fleet size on every tick.

### Secondmate vs. crewmate architecture
- **Crewmate** = an ephemeral, task-scoped worker spawned by the first mate for a single ship/scout task, living in a disposable worktree, torn down (or PR'd/merged) at task completion. This is the parallel-task unit the research brief is targeting.
- **Secondmate** = a *persistent*, isolated firstmate **home** (its own `FM_HOME`, own state/config/projects, own session lock) — effectively a whole second first-mate instance, optionally on a different machine (SSH-reachable). A secondmate is described in-source as "a crewmate with an isolated firstmate home and a charter, not a second architecture" — i.e. same engine, just given durable identity and its own backlog instead of being scoped to one task.
- **Explicit scoping instruction from the brief confirmed correct:** carrier_hermes wants the **crewmate model** (N ephemeral task-scoped workers under one supervisor), not secondmates (N persistent supervisor instances). This maps directly onto "Wrench dispatches N concurrent Mate task instances," not "Wrench spins up N independent Mate *profiles*."

### AGENTS.md — dispatch/supervision contract
`AGENTS.md` is firstmate's single always-loaded operating contract (analogous to carrier_hermes's `docs/INTER_AGENT_PROTOCOL.md` + each bot's `SOUL.md` combined). Relevant structural patterns:
- **Hard rule ordering** — numbered, priority-ordered hard rules the agent must never violate (e.g. "never write to a project directly," "never merge a PR without explicit captain word," "never tear down unlanded work," "crewmates never address the captain directly — all communication flows through firstmate," "report outcomes faithfully"). This is a *stronger, more mechanical* version of carrier_hermes's SOUL.md "Never-be" fields.
- **Crewmate briefs** (`bin/fm-brief.sh`) are a **scaffolded contract**, not free text: every brief must retain a worktree-isolation assertion and a "stop if launched in the primary checkout" guard. This is directly analogous to (and stricter than) carrier_hermes's current Wrench→Mate Kanban task body pattern (see §2) — firstmate enforces the worktree assertion structurally via a script, carrier_hermes currently relies on Mate's own SOUL.md discipline plus `workspace_kind: worktree` on the Kanban row.
- **Routing/dispatch precedence**: explicit per-task captain override → best-fit configured dispatch-profile rule → configured default → static crew harness. Dispatch profiles (`config/crew-dispatch.json`) let the captain steer *which backend/model/effort* handles which task by natural-language rule, resolved against live quota data (`quota-axi`) before every dispatch — i.e. firstmate does its own real-time capacity-aware model routing per crewmate spawn.
- **Backend abstraction**: verified harnesses are `claude`, `codex`, `opencode`, `pi`, `pi-signed`, `grok`, `kimi`, `cursor` (+ `muse` for crewmates only). This directly parallels carrier_hermes's Mate backend order (`claude-code → codex → opencode → native workers`), confirming carrier_hermes already follows the firstmate multi-backend-fallback pattern — the gap is only in *concurrency*, not backend diversity.
- **Session-start ritual** (`bin/fm-session-start.sh`) runs once per session: acquire a session lock, run detect-only bootstrap checks, drain the durable wake queue (present unread wakes as the first work item), emit the supervision operating-instructions block, print a fleet-state digest (per-task metadata + tail of status log + liveness ping), then context digest. **This "drain wake queue on wake" pattern is the direct analog of what a Hermes-native Wrench polling loop would need to do on every tick if it can't get a bash-watcher equivalent for free (see §3).**

---

## §2 — Current carrier_hermes Mate invocation

### Dispatch flow today (confirmed live from Kanban DB + repo)
1. **Wrench (`coding_lt`)** receives a coding job (from Marshal or Helm) via Kanban.
2. Wrench writes a **self-contained Kanban task body** targeting `assignee: firstmate`, e.g. `t_e8b8e392` ("Build scripts/sub_capacity_router.py"), `t_518f43da` ("Local LLM Integration"), `t_5e0ae4a3` ("OB1 semantic search").
3. Job packet format observed (from `t_e8b8e392` body) is Markdown, not JSON:
   ```
   # Job Packet — Wrench → Mate | <JOB-ID>
   ## Mission
   <what to build>
   Repo root: <path>
   Target file(s): <path(s)>
   Branch: hermes/<project>/<short>
   ## Context you need
   <all facts Mate needs — no assumed shared history>
   ```
   Some packets (`t_5e0ae4a3`) instead use a YAML-frontmatter-like header (`job_id`, `from`, `to`, `created_at`, `priority`, `shadow_mode`, `michael_visible_summary`) followed by `## Goal` / `## Context (self-contained)` sections. **Format is not yet standardized** — this is itself a gap (see §3).
4. Wrench also writes a **local sortie log** in `_agent/coding_lt/sorties/<JOB-ID>.md` documenting recon gathered and the dispatch decision *before* creating the Kanban task — this is Wrench's own audit trail, separate from the Kanban row.
5. `coding_lt`'s toolset (confirmed in `bots/BOT_MATRIX.md`) is **kanban (dispatch) + AIPass + session_search + memory + file (`_agent/coding_lt/**`) + discord** — explicitly **no** terminal/code_execution/browser/delegation. **Wrench cannot itself touch code.** Dispatch is 100% via `kanban_create`.
6. **Does Wrench use `delegate_task`?** No — confirmed by toolset table: `delegation` is in the OFF list for `coding_lt`. All coding dispatch goes through Kanban `kanban_create(assignee='firstmate', ...)`, never `delegate_task`. This matches `docs/INTER_AGENT_PROTOCOL.md` rule #6 ("No inheritance lies — Helm must not delegate_task a leaf and pretend it is Inbox/Tasker/Clerk") applied fleet-wide: Lt tier holds **no execution tools**.
7. **Does Mate (firstmate) use claude-code?** Yes — `firstmate` SOUL.md: "Backend order: claude-code → codex → opencode → native workers." `firstmate`'s Hermes toolset includes `delegation` (confirmed in `~/.hermes/profiles/firstmate/config.yaml` platform_toolsets) — so Mate *can* spin up sub-agents itself (e.g. for a "janitor/docs" pass on paid DeepSeek per SOUL.md), but that's Mate's own internal fan-out, not how Wrench reaches Mate.

### State files Mate writes today
- **No `_agent/state/firstmate-fleet.json` exists yet** (confirmed absent via file search) despite being named as Mate's write root in both `firstmate/SOUL.md` line 27 and `docs/INTER_AGENT_PROTOCOL.md` §2.4, and despite a JSON Schema already defined for it (`schemas/firstmate_fleet.schema.json`: `{claims: [{path, bot, job_id}]}`). **This is a real gap**: the schema anticipates a claims ledger (which bot/job holds a lock on which path) that would be the natural concurrency-safety primitive, but it is not yet populated.
- `_agent/coding_lt/sorties/<id>.md` — Wrench's own dispatch log (not Mate's).
- No `_agent/mailbox/firstmate/` inbox/outbox content found (dirs may exist but empty at time of research — AIPass is defined in protocol but this specific job flow used Kanban body + comments, not file-based AIPass, for the observed dispatches).
- Sortie/report artifacts: none of the 3 sampled Mate tasks had a written report file distinct from the Kanban `result` field; `t_e8b8e392`/`t_5e0ae4a3` show `status=done` with an **empty `result` column** in the DB — actual outcome narrative appears to live only in Kanban comments/events, not captured in this extract. **Worth flagging to Wrench/Marshal as a return-packet completeness gap independent of parallelism.**

### Does Mate use worktrees?
**Yes, consistently.** `git worktree list` shows 6 active worktrees under `.worktrees/<task_id>/`, and Kanban DB query confirms: **19 `firstmate` tasks used `workspace_kind: worktree`** (vs. 11 `scratch`). Every worktree directory is a full clone of the repo tree (`ARCHITECTURE.md`, `bots/`, `profiles/`, `scripts/`, etc.), one git branch per worktree (`git worktree list` shows distinct branches like `wt/t_8290a27f`, `wt/e91a2b0a-...`). **This confirms the Hermes Kanban `workspace_kind: worktree` primitive (see §3) is already the mechanism carrying Mate's per-task isolation today — it is a native Hermes feature, not something Mate/firstmate had to build.** Two worktrees (`e91a2b0a-...`, `t_4b259dcc`) are actually owned by a *different* assignee (`code_auditor`, a Shipwright-wing bot), confirming the worktree-per-task pattern is already fleet-wide, not Mate-specific.

### Return packet format
- Per `docs/INTER_AGENT_PROTOCOL.md` §2.4 and `firstmate/SOUL.md`: `status`, `branch`, `paths_touched[]`, `tests_run`, `blockers[]`, summary ≤40 lines.
- In practice (from Kanban DB), completion is via `kanban_complete(summary=..., metadata={...})` — the Hermes-native mechanism — landing in the task's `result`/`summary` columns and `events` log. The **schema is currently aspirational**: none of the 3 sampled completed Mate tasks had a populated `result` field matching that shape in the raw DB dump (may be in `metadata` JSON not surfaced by this query, or in Kanban comments — worth Wrench spot-checking).

---

## §3 — Gap analysis

### 3.1 Supervision: watcher equivalent vs. manual polling
- **Gap: no bash-watcher equivalent exists in carrier_hermes today.** Hermes's Kanban dispatcher (`kanban.dispatch_in_gateway`, default interval 60s) *does* provide zero-LLM polling for **task lifecycle** (claim reclamation, stale-task reclamation past `kanban.dispatch_stale_timeout_seconds`, default 4h with no heartbeat in the last hour, promotion of `todo→ready`) — this is a genuine free primitive, running inside the gateway process, that already does part of firstmate's watcher job.
- **What's missing vs. firstmate:** Hermes's dispatcher reclaims *stalled/crashed* tasks, but has no concept of "actionable vs. benign wake" classification for a *supervising* agent — it doesn't wake Wrench when a Mate instance needs attention, it only handles worker-crash recovery for the dispatcher itself. carrier_hermes already has the beginning of a bolt-on for this: `scripts/coding_stall_watcher.py`, a `no_agent` cron (zero LLM tokens) that queries the Kanban DB every 30 min for `assignee='firstmate' AND status IN ('running','blocked') AND started_at < now-30min`, and writes an AIPass alert to Wrench's inbox + prints a summary (cron delivers to Wrench's bot-chat). **This is structurally the exact same shape as `bin/fm-watch.sh`**: zero-token bash/Python polling a durable state store, escalating only on actionable staleness, writing to a durable queue (AIPass mailbox) rather than an ephemeral notification.
- **Gap for N-concurrent case:** `coding_stall_watcher.py` currently hardcodes `assignee='firstmate'` (singular) and produces one alert per stalled task — this scales fine to N since it's already a `SELECT ... WHERE ...` over all rows, **but it has no concept of per-Mate-instance identity** (task title strings only) and no "is this task provably still writing files" liveness check (firstmate's worktree-write-deferral signal) — a Mate that's genuinely still working (writing files, just not yet hitting a `kanban_heartbeat`) would false-positive as stalled at the 30-min mark the same as a truly wedged one.
- Similarly `blocked_task_watchdog.py` already does escalating-tier nudges (10/30/45/60 min) for **human-blocked** tasks fleet-wide, with per-task-id sidecar state to fire each tier once — this is a decent analog to firstmate's `FM_PAUSE_RESURFACE_SECS` re-surfacing cadence, but again keyed on `block_kind='human'`, not on "Mate crew instance N of task X."

### 3.2 Worktree isolation: audit
- **Already working, confirmed live.** `.worktrees/` contains 6 real git worktrees; `git worktree list` confirms clean branch separation; Kanban `workspace_kind='worktree'` is already the dominant mode for `firstmate` (19/30 = 63% of all Mate tasks ever dispatched use it). **No new worktree infrastructure needs to be built** — Hermes's built-in `workspace_kind: worktree` (creates `.worktrees/<task_id>/` via `git worktree add`, preserved on completion) is a first-class, already-battle-tested primitive doing exactly what firstmate's `treehouse` dependency does.
- **Gap:** nothing currently *audits* worktree hygiene — stale worktrees from `done`/`archived` tasks are not visibly cleaned up (`e91a2b0a-...`/`t_4b259dcc` worktrees belong to `blocked` code_auditor tasks that may be long-stale; `ws01-install` worktree has no matching Kanban task id pattern at all, suggesting an orphan from manual setup). Firstmate's teardown (`bin/fm-teardown.sh`) explicitly owns "complete landed-work" testing and safe worktree removal — carrier_hermes has no equivalent teardown/GC script for `.worktrees/`.

### 3.3 State naming: distinguishing Mate-1 vs Mate-N
- **Gap, but low-severity — Kanban task id already *is* the natural namespace.** Every Mate dispatch already gets a unique `t_<hex>` Kanban task id, and (per §3.2) a unique worktree path keyed by that same id (`.worktrees/t_<hex>/`). This means **the disambiguating key already exists and requires no new invention** — it just needs to be *used consistently* as the state-file namespace, the same way firstmate uses `state/<task-id>.*`.
- The one real naming gap: the **planned** `_agent/state/firstmate-fleet.json` (schema already defined, file never populated — see §2) is currently *singular*, implying one shared fleet-state file. For N-concurrent Mates this file becomes a **shared-write hazard** unless every Mate instance writes via read-modify-write with file locking, or unless it's restructured as `_agent/state/firstmate-fleet/<task_id>.json` (one file per instance, Wrench aggregates) — directly mirroring firstmate's actual pattern of one `state/<id>/...` directory per task rather than one shared file.

### 3.4 Concurrency cap: safe max given subscription model
- carrier_hermes runs on **Claude Max OAuth** (Mate's primary model, `quality` Sonnet) with rate limits documented in `ARCHITECTURE.md`: Sonnet 4.x = 4,000 RPM / 2M ITPM / 400K OTPM at Tier 4 (Max 20x). SuperGrok limits are undocumented/header-derived only.
- **No hard config cap exists today.** Hermes itself exposes `kanban.max_in_progress` (config key, default unset/unlimited) — "Caps the number of simultaneously running tasks... useful for slow workers (local LLMs, resource-constrained hosts)." This is a **board-wide** cap (all assignees), not per-assignee — so it cannot alone express "max 3 concurrent Mates but unlimited everything else" without either (a) giving Mate tasks their own board, or (b) building a Wrench-side pre-dispatch check.
- `dispatch_lock.sh` / `dispatch_preflight.sh` already provide a **binary** fleet-wide kill switch (`DISPATCH_LOCK`) checked before any dispatch — this is a circuit breaker, not a concurrency throttle; it stops *all* new dispatch, not "cap at N".
- **Recommendation basis (not yet a decision — flagged to §5):** 2M ITPM / 400K OTPM at Sonnet tier, divided across N concurrent Mate sessions each potentially running a multi-file coding turn (tens of thousands of tokens per turn), suggests **2–4 concurrent Mates** is a conservative starting cap before ITPM headroom becomes a real risk, especially since Wrench, Marshal, Helm, and other Sonnet-tier bots share the same Claude Max pool. This is an estimate from the documented rate limits, not a measured ceiling — Michael's decision belongs in §5.

### 3.5 Dispatch contract: what changes in the Wrench→Mate job packet
- **Gap: job packet format is not standardized today** (§2 showed 2 different shapes across 3 sampled tasks). Before adding N-way concurrency, the packet needs (at minimum) an explicit **Mate-instance identifier** distinct from the Kanban task id (so a Wrench-side dashboard/log can say "Mate-2 of 3, working on X"), and an explicit **non-overlapping path/file manifest** so Wrench can verify conflict-freedom *before* dispatch rather than discovering a collision after two Mates both write `scripts/foo.py`.
- Firstmate's `bin/fm-brief.sh` scaffold enforces the worktree-isolation assertion structurally (a script generates the brief; briefs can't accidentally omit it). carrier_hermes has no script-generated brief — packets are hand-written per dispatch by Wrench's own reasoning. **This is a real structural gap**: nothing currently *prevents* Wrench from writing a packet whose target file overlaps another in-flight Mate's target file.

### 3.6 Result aggregation: how Wrench collects results from N Mates
- **Gap.** Today, Wrench dispatches one task and (implicitly) waits for a Kanban completion event on that one row — single-threaded supervision. There is no existing "fan-in" pattern in carrier_hermes: no Wrench task currently has multiple Mate children it aggregates. Hermes's native primitive for this is `kanban_create(parents=[...])` (a synthesis/aggregation task that only promotes to `ready` once all parent Mate tasks are `done`) — **directly available today, zero new infrastructure**, but Wrench's SOUL/protocol doesn't yet describe using it this way, and Wrench has no execution tools to *read* multiple result payloads and reconcile them itself beyond what Kanban surfaces (which is fine, since Wrench's job is routing/review, not code execution).

### 3.7 Conflict avoidance: never touch overlapping paths
- **Gap, most safety-critical one.** `docs/INTER_AGENT_PROTOCOL.md` line "Parallel only with non-overlapping paths" already exists as a *stated rule* for `firstmate`'s Authority field — but there's **no enforcement mechanism**. Nothing currently computes or checks a path-overlap set across concurrently running Mate tasks before dispatch. The aspirational `_agent/state/firstmate-fleet.json` claims schema (`{path, bot, job_id}`) is precisely designed to be this enforcement primitive (a claims ledger Wrench could check-and-set before creating a new Mate Kanban row) — **but it was never wired up, and even the schema doesn't define a way to release a claim (no `released_at`/TTL field), so as designed it would grow unboundedly and never self-clean.**

---

## §4 — Implementation options (ranked by fit with existing carrier_hermes patterns)

### Gap 3.1 — Supervision / watcher
1. **(Recommended) Extend `coding_stall_watcher.py`** to (a) accept a `--assignee firstmate` filter already present but generalize the query to group by task and report per-instance identity from the packet, (b) add a lightweight "is this task's worktree still receiving file writes" check (`os.path.getmtime` walk over `.worktrees/<id>/`, bounded depth/time like firstmate's `FM_WORKTREE_WRITE_*` knobs) before flagging stale, to avoid false-positiving genuinely-working Mates. This reuses the existing `no_agent` cron pattern exactly — zero new infrastructure, ~50-100 line patch.
2. Build a true bash/PowerShell zero-token watcher modeled directly on `bin/fm-watch.sh`, polling `.worktrees/*/` mtimes + Kanban DB directly (bypassing even the cron scheduler latency) — higher fidelity to firstmate's design, but duplicates work Hermes's dispatcher + existing cron scripts already do 80% of. Only worth it if sub-minute wake latency becomes a real requirement.
3. Do nothing beyond current `kanban.dispatch_stale_timeout_seconds` (4h) reclaim — too coarse for coding turns (a wedged Mate would sit for up to 4h before Hermes itself notices), rejected as insufficient on its own.

### Gap 3.2 — Worktree isolation
1. **(Recommended) Add a `worktree_gc.sh` script** that lists `.worktrees/*`, cross-references each against the Kanban DB (`workspace_path` for non-`done`/`archived` tasks), and flags/removes orphans (worktrees with no matching live task, or matching a `done` task older than N days). Run as a weekly `no_agent` cron alongside existing watcher scripts. Mirrors firstmate's `bin/fm-teardown.sh` "complete landed-work" test conceptually, in carrier_hermes's own script-per-concern style.
2. Rely on Hermes's own scratch/worktree preservation semantics and manual `git worktree prune` run by Wrench/Michael periodically — lower effort, but the June-2026-era ARCHITECTURE.md governance principle ("governance rules are structural, not advisory") argues against leaving this manual.

### Gap 3.3 — State naming
1. **(Recommended) Namespace by Kanban task id, not a shared file.** Replace the planned single `_agent/state/firstmate-fleet.json` with `_agent/state/firstmate-fleet/<task_id>.json` (one file per in-flight Mate instance, written only by that instance, read/aggregated by Wrench or the watcher script). This directly mirrors firstmate's `state/<id>/...` per-task directory convention and avoids any concurrent-write race entirely (each Mate only ever writes its own file).
2. Keep one shared JSON file but add file-locking (`flock`/`msvcrt.locking`) around read-modify-write — matches the *original* schema shape with less restructuring, but reintroduces a write-contention bottleneck under concurrency and is more failure-prone on Windows (this fleet's host OS) where advisory locking is less uniform than POSIX flock.

### Gap 3.4 — Concurrency cap
1. **(Recommended) Wrench-side pre-dispatch check** — before `kanban_create(assignee='firstmate', ...)`, Wrench queries current `COUNT(*) WHERE assignee='firstmate' AND status IN ('running','ready')` and refuses/queues if at cap. Since Wrench has no execution tools, this would need to be a tiny helper Wrench can call — but Wrench's toolset is `kanban`-only, no code_execution — so this really means **either** (a) a `kanban_list`-based count check Wrench does natively via the `kanban_list` tool it already has access to (no new tooling needed, just a SOUL/protocol instruction), **or** (b) a Hermes-native `kanban.max_in_progress` cap if Mate tasks get their own dedicated board (clean separation, but changes how Wrench/Marshal currently share the single `carrier` board).
2. Set `kanban.max_in_progress` globally on the `carrier` board — simplest to implement (one config line) but caps *all* assignees fleet-wide together, not just Mate, which would also throttle Deck/Stacks/Chart dispatches sharing the same board. Rejected unless Michael is fine with a fleet-wide (not Mate-specific) cap.
3. No cap, rely on Claude Max 429s as the natural backpressure signal, with Wrench catching failed dispatches and backing off. Cheapest to build, but reactive rather than preventive, and 429s on a shared subscription pool affect *every other bot's* availability too (Helm, Marshal, all Lts) — not isolated to coding.

### Gap 3.5 — Dispatch contract
1. **(Recommended) Standardize the job packet to one Markdown template** (the `t_e8b8e392` shape is cleaner than the YAML-header shape) with mandatory fields: `mate_instance_id` (human-readable, e.g. `mate-1-of-3`), `target_paths[]` (explicit list, not prose), `branch`, `worktree: required`. Wrench composes it by hand today (no execution tools to template it), so standardization is a documentation/SOUL-instruction change, not code — lowest-cost option that directly closes the gap.
2. Build a `scripts/compose_mate_brief.py` helper that Wrench... **cannot run** (no terminal/code_execution tool) — this option is **not viable for Wrench** under current tool scoping, and would require either loosening Wrench's toolset (against `docs/INTER_AGENT_PROTOCOL.md`'s "Lts hold no execution tools" rule) or having Marshal/Helm run it upstream. Included only to note why it's rejected.
3. Leave format loose, rely on Mate's own judgment to parse whichever shape arrives — status quo, works today for N=1, but increases misparse risk exactly when packets need machine-checkable fields (`target_paths[]`) for conflict-avoidance (§3.7). Rejected for the concurrent case.

### Gap 3.6 — Result aggregation
1. **(Recommended) Use native `kanban_create(parents=[mate1_id, mate2_id, ...])`** for a synthesis/review task that only promotes once all Mate children are `done` — zero new infrastructure, this is exactly the pattern Hermes docs show for research fan-in and is already proven in this very research task's own parent/child structure (`t_a94727a4` → `t_fa66b0ed`, the implementation-plan task, blocked on this one). Wrench (or a dedicated aggregator step) reads each child's `kanban_show()` summary/metadata once promoted.
2. Have Mate instances write to a shared results file Wrench polls — duplicates what Kanban already gives for free; only useful if a *narrative* combined report (not just N separate task rows) is wanted, in which case it's an *addition* on top of option 1, not a replacement.

### Gap 3.7 — Conflict avoidance
1. **(Recommended) Populate and enforce the existing `_agent/state/firstmate-fleet.json` claims schema** — but restructure per Gap 3.3's recommendation (one file per task id under `_agent/state/firstmate-fleet/`, aggregated view computed on read, not on write). Wrench checks target paths against all currently-`running`/`ready` Mate tasks' declared `target_paths[]` (from the standardized packet, Gap 3.5) via `kanban_list` before creating a new dispatch — pure Kanban-tool-based check, no new execution capability needed for Wrench. This closes 3.5 and 3.7 together with one packet-format change plus one Wrench-side habit change (a `kanban_list` scan before every `kanban_create`).
2. Rely on git itself as the collision detector (a merge/rebase conflict surfaces the overlap after the fact) — cheapest, zero new work, but reactive: two Mates could both burn a full turn on conflicting work before either merges, wasting exactly the subscription quota headroom Gap 3.4 is trying to protect. Rejected as sole mechanism, acceptable as a backstop.
3. Full static analysis of task packets to detect *transitive* overlaps (e.g. both touch a shared config file indirectly) — high engineering cost, not justified until simple explicit-path checking (option 1) proves insufficient in practice.

---

## §5 — Open questions for Michael

| Question | Options | Recommended |
|---|---|---|
| Max concurrent Mate instances? | (a) 2 (b) 3 (c) 4 (d) no cap, rely on 429 backpressure | **(b) 3** — conservative given shared Claude Max ITPM pool across Helm/Marshal/all-Lts, revisit after measuring real per-turn token usage |
| Adopt `fm-watch.sh` directly (port the bash script) or extend the existing `coding_stall_watcher.py` cron? | (a) port fm-watch.sh verbatim (b) extend existing cron script (c) hybrid: new lightweight watcher script, not a port | **(b) extend existing cron** — `coding_stall_watcher.py` already does 80% of the job with the exact same zero-token philosophy; porting firstmate's bash adds a second parallel supervision system to maintain |
| Should Mate tasks move to their own dedicated Kanban board so `kanban.max_in_progress` can cap them without affecting Deck/Stacks/Chart? | (a) yes, new `coding` board (b) no, stay on shared `carrier` board with a Wrench-side pre-check instead | **(b) stay on shared board** — avoids board-split migration cost; Wrench already has `kanban_list` access to do the pre-check natively, no new tool needed |
| Restructure `_agent/state/firstmate-fleet.json` into a per-task-id directory now, or leave the schema as-is and add locking? | (a) restructure to per-instance files (b) keep single file + flock/lockfile | **(a) restructure** — matches firstmate's own actual pattern, avoids Windows-host locking fragility, and the file has never been populated yet so there's no migration cost |
| Standardize the Wrench→Mate job packet template now, before building concurrency, or as part of the same rollout? | (a) standardize first, as its own small change (b) bundle into the concurrency rollout | **(a) standardize first** — it's a pure documentation/SOUL change Wrench can start using on the very next single-Mate dispatch, de-risks the bigger concurrency change by proving the template works at N=1 first |
| Who owns building/testing the worktree GC script — Wrench dispatches it to Mate as a coding task, or is it out of scope for this initiative? | (a) in scope, dispatch to Mate as Phase 0 (b) defer to a separate maintenance/Shipwright-wing task | **(a) in scope as Phase 0** — orphaned worktrees already exist today (see §3.2 audit); cheap to fix before adding more concurrent worktree creation |

---

## Recommended approach (summary)

- Keep the **crewmate model** (N ephemeral task-scoped Mate dispatches under one Wrench), not firstmate's secondmate model (N persistent supervisor homes) — this matches the brief's explicit scoping and carrier_hermes's existing Lt-tier-routes/leaf-executes architecture.
- **No new worktree infrastructure needed** — Hermes's native `workspace_kind: worktree` already does what firstmate's `treehouse` dependency does, and 19/30 historical Mate dispatches already use it correctly.
- **Reuse, don't replace**, the existing zero-token cron pattern (`coding_stall_watcher.py`, `blocked_task_watchdog.py`) as the Hermes-native analog of `bin/fm-watch.sh` — extend it with per-instance identity and worktree-write liveness checking rather than porting firstmate's bash watcher wholesale.
- **Standardize the Wrench→Mate job packet** to one Markdown template with mandatory `mate_instance_id`, explicit `target_paths[]`, and `branch` fields — do this first, at N=1, before adding concurrency.
- **Populate the already-designed-but-unused `firstmate_fleet.schema.json` claims ledger**, restructured to one file per Kanban task id (mirrors firstmate's `state/<id>/` pattern), as the conflict-avoidance mechanism Wrench checks via `kanban_list` before every new Mate dispatch.
- **Use native `kanban_create(parents=[...])`** for result fan-in/aggregation — zero new infrastructure; this exact pattern is already running in production for this research task's own parent/child chain.
- **Cap concurrency via a Wrench-side pre-dispatch count check** using the `kanban_list` tool Wrench already has, not via `kanban.max_in_progress` (which would throttle the whole shared `carrier` board, not just Mate).
- **Fix the worktree hygiene gap first** (orphaned `.worktrees/` entries exist today, confirmed live) with a small GC script, before multiplying worktree creation rate.
- Every proposed change is either (a) a documentation/SOUL-instruction change Wrench can adopt immediately with its existing toolset, or (b) a small, narrowly-scoped script addition in the same style as the scripts already in `scripts/` — nothing in this plan requires loosening any bot's tool scoping or violating the Lt-tier "no execution tools" rule.
- Sequencing recommendation for the follow-up implementation plan: **Phase 0** (worktree GC + packet template standardization, testable at N=1) → **Phase 1** (claims ledger restructure + Wrench pre-dispatch check) → **Phase 2** (extend stall watcher for per-instance liveness) → **Phase 3** (raise concurrency cap from 1 to Michael's chosen N, using `kanban_create(parents=[...])` for fan-in) → **Phase 4** (soak test at low N, then raise toward the target cap).

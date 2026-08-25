# Cost-Optimal Carrier Hermes Fleet Hardening Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
> **Coding default:** Any coding/repo work is routed through **FirstMate** (Hermes profile + skill), not generic `delegate_task` leaves.

**Goal:** Keep the multi-bot Carrier Hermes fleet on a single Hermes runtime, maximize subscription-zero-marginal-cost usage, minimize OpenRouter spend, and close every structural/quality gap from the architecture review—without giving up named bots or FirstMate parallel coding.

**Architecture:** Three lanes on one Hermes install: (1) **Command** — `chief_of_staff` on SuperGrok OAuth classifies and dispatches only; (2) **Ops specialists** — named profiles with hard toolsets, driven by **Kanban workers + per-profile cron** (not CoS `delegate_task` leaves, which inherit CoS tools); (3) **Coding crew** — `firstmate` profile is the default coding path, using worktree-isolated workers and role-tiered models. Watcher is **script-first** (`no_agent`) with optional cheap LLM summaries. Free OpenRouter is limited to aux + MoA references; live email/calendar judgment is **pinned paid** DeepSeek V3 (or better). Governance is structural: write-safe roots, no-send tools, dispatch lock file, dual audit (session DB + append-only log + Discord).

**Tech Stack:** Hermes Agent (profiles, gateway, cron, Kanban, MoA, approvals, MCP), SuperGrok OAuth + Claude Max OAuth + OpenRouter, Todoist/Google/mail MCPs as available, Discord gateway, Obsidian vault `_agent/` tree, FirstMate contract ported from `carrier_ops/firstmate/`.

**Repo root:** `/Users/michaelkanter/carrier_hermes`  
**Related source of truth (read-only reference):** `~/Desktop/Existing Folders/Coding_Projects/carrier_ops/` (`AGENTS.md`, `firstmate/AGENTS.md`)

---

## Cost model (non-negotiable targets)

| Work class | Billing | Model pin | Never |
|---|---|---|---|
| CoS classify/dispatch | SuperGrok sub $0 marginal | `xai-oauth/grok-4.5` | Burn Claude on “what is this request?” |
| Drafting / vault Q&A / research synthesis | Claude Max sub $0 marginal | `anthropic/claude-sonnet-4-6` | Free small models for voice/judgment |
| True high-stakes / MoA hard mode | SuperGrok aggregator + cheap refs | MoA `frontier` | Opus on every research ask |
| Email triage + calendar mutations | OpenRouter **paid** stable | `deepseek/deepseek-chat-v3-0324` only | Free rotate for inbox/calendar |
| Aux (titles, compression, vision) | Free or cheapest paid | one pinned free/cheap ID + fallback | Subscription main model |
| Fleet heartbeat / kill path | **$0 LLM** | bash `no_agent` cron | Gemma every 5m forever |
| Coding implementer | Claude Max Sonnet (or Grok if Claude limited) | FirstMate implementer | Free models writing prod code |
| Coding test/docs/janitor | Cheap paid OR Haiku-class via Max if available | specialist coding tier | Rotating free for tests that gate merges |
| MoA references only | Free/cheap OpenRouter | 2 refs max | Free refs as sole decision-makers |

**OpenRouter hygiene:** One-time ≥$10 credits so free-tier daily cap is 1k if any free use remains; still **do not** put live ops on `:free` endpoints. Prefer **one** paid specialist ID for consistency.

**Estimated steady-state $:** Near-zero if mail/calendar volume is moderate on DeepSeek (~$0.27/M) and CoS/draft/research stay on subs. Watcher ≈ $0. Coding stays on Max/Grok subs.

---

## Design decisions (fixes mapped to review gaps)

| Gap | Fix in this plan |
|---|---|
| `delegate_task` inherits CoS tools → specialists can’t get distinct scopes | **Kanban workers + profile-scoped cron** for named bots; CoS only creates tasks / briefs |
| SOUL “write `_agent/` only” is advisory | `HERMES_WRITE_SAFE_ROOT` / per-profile sandbox + vault RO mounts where possible |
| Watcher “kill authority” is Discord-only | **Dispatch lock file** + `no_agent` script can set lock; CoS refuses dispatch when locked |
| Free model rotation on email/calendar | **Pin paid DeepSeek V3**; delete free from specialist alias |
| Free watcher 288 LLM calls/day | Heartbeat = script; LLM summary at most daily (optional) |
| Dual audit weaker than Nostr+maka | Append-only JSONL audit under `_agent/audit/` + session DB + Discord critical path |
| Approval cards → social checkmarks | No send tools anywhere; drafts only; optional Discord reaction bot later (V2) |
| firstmate / worktrees missing | **`firstmate` profile + skill**; `delegation.worktree_isolation: true` for coding lane; default CoS route for coding |
| Email/calendar MCP stubs | Wire real read tools or fail SETUP loudly; shadow mode until wired |
| Single-runtime blind spot | External LaunchAgent/cron heartbeat **outside** Hermes that pings Discord if gateway stale |
| Quality variance CoS Grok vs Claude | Explicit route table in CoS SOUL; quality profiles pinned Sonnet; no silent quality on free |

### Dispatch model (critical)

```
Discord/Telegram/CLI
        │
        ▼
 chief_of_staff (Grok 4.5, no file/browser/terminal)
        │
        ├── coding / repo / PR / implement / fix / test  →  FIRSTMATE (default)
        │         └── Kanban or firstmate skill → worktree workers
        │              implementer | reviewer | test-writer | docs-writer | janitor
        │
        ├── email triage     → kanban/cron job on profile email_reader
        ├── email draft      → profile email_drafter (Sonnet)
        ├── calendar         → profile calendar_manager
        ├── vault            → profile vault_librarian (Sonnet)
        ├── research         → profile research_agent (Sonnet)
        └── hard multi-view  → /moa frontier (Grok aggregator)
```

**Forbidden:** CoS `delegate_task` to “simulate” email_reader with inherited tools.  
**Allowed:** CoS `delegate_task` only for ephemeral scratch reasoning with **no** privileged tools, or FirstMate-internal leaves after FirstMate has the right toolsets.

---

## Target directory structure (after implementation)

```
carrier_hermes/
├── README.md
├── ARCHITECTURE.md                 # rewritten to match this plan
├── COST_MODEL.md                   # tier table + anti-patterns
├── RISKS.md                        # residual risks + go/no-go gates
├── GOVERNANCE.md                   # constitution + structural enforcement map
├── profiles/
│   ├── chief_of_staff/SOUL.md
│   ├── firstmate/SOUL.md           # NEW — coding dispatcher
│   ├── email_reader/SOUL.md
│   ├── email_drafter/SOUL.md
│   ├── calendar_manager/SOUL.md
│   ├── vault_librarian/SOUL.md
│   ├── research_agent/SOUL.md
│   └── subscription_watcher/SOUL.md
├── firstmate/                      # NEW — coding crew contract
│   ├── AGENTS.md                   # ported/adapted from carrier_ops
│   ├── projects.yaml.example
│   └── roles/
│       ├── implementer.md
│       ├── reviewer.md
│       ├── test-writer.md
│       ├── docs-writer.md
│       └── janitor.md
├── scripts/
│   ├── watcher_heartbeat.sh        # no_agent fleet monitor
│   ├── external_hermes_watchdog.sh # outside Hermes
│   ├── dispatch_lock.sh            # set/clear/check lock
│   ├── audit_append.sh             # append-only audit helper
│   ├── validate_specialist_json.py # schema gate before Todoist/state write
│   └── smoke_fleet.sh
├── schemas/
│   ├── email_triage.schema.json
│   ├── calendar_sync.schema.json
│   └── firstmate_fleet.schema.json
├── moa/frontier_preset.md
├── prompts/
│   ├── SETUP_PROMPT.md             # full rewrite
│   └── SHADOW_MODE.md              # week-1 live policy
└── .hermes/plans/                  # this plan
```

---

## Phase overview

| Phase | Name | Outcome |
|---|---|---|
| 0 | Docs & cost constitution | Written contracts before any live tools |
| 1 | Structural governance | Locks, sandbox, audit, no-send proof |
| 2 | Model tiers (cost-optimal) | Aliases, MoA, aux, no free ops pins |
| 3 | Multi-bot profiles (correct dispatch) | 8 profiles + Kanban/cron wiring |
| 4 | FirstMate coding default | Profile, skill, worktrees, CoS route |
| 5 | Watcher $0 path | no_agent heartbeat + external watchdog |
| 6 | Inbox/calendar shadow path | Real tools or explicit blocked; schemas |
| 7 | Smoke + go/no-go | Checklist; no live mutations until green |

Implement phases in order. Do not enable Todoist writes or calendar mutations until Phase 6 shadow week criteria pass.

---

### Task 1: Create plan-tracking + COST_MODEL.md

**Objective:** Document the cost constitution so implementers cannot “optimize” back into free rotation on live data.

**Files:**
- Create: `carrier_hermes/COST_MODEL.md`
- Create: `carrier_hermes/RISKS.md` (stub pointing at go/no-go)

**Step 1:** Write `COST_MODEL.md` with the cost table from this plan, plus anti-patterns:

```markdown
# Cost Model — Carrier Hermes

## Rules
1. Subscription OAuth first (xAI SuperGrok, Anthropic Claude Max).
2. OpenRouter paid only for high-volume structured ops (email/calendar).
3. OpenRouter :free only for: aux slots, MoA references, throwaway scrapes.
4. Watcher heartbeats must be no_agent scripts (zero tokens).
5. Never rotate free models on email_reader or calendar_manager.
6. Coding defaults to FirstMate on subscription tiers.

## Anti-patterns (reject in review)
- specialist alias → :free pool
- watcher cron without no_agent
- CoS on Opus for classification
- research_agent on free Llama for final reports
```

**Step 2:** Commit

```bash
cd /Users/michaelkanter/carrier_hermes
git add COST_MODEL.md RISKS.md
git commit -m "docs: add cost model and risks stubs for fleet hardening"
```

---

### Task 2: Rewrite ARCHITECTURE.md to match reality

**Objective:** Replace optimistic layer map with Kanban/profile dispatch, FirstMate lane, structural governance, and honest audit.

**Files:**
- Modify: `carrier_hermes/ARCHITECTURE.md` (full rewrite)

**Step 1:** Rewrite sections:
- Design philosophy (keep 3 principles; add “coding = FirstMate”)
- Dispatch diagram (this plan)
- Model tier table (no free specialist pool)
- Governance table with **real** Hermes mechanisms
- Profile list including `firstmate`
- Explicit “What we do not claim” (Nostr dual-write, harness SSE, etc.)

**Step 2:** Commit

```bash
git add ARCHITECTURE.md
git commit -m "docs: rewrite architecture for cost-optimal multi-bot + FirstMate"
```

---

### Task 3: Add GOVERNANCE.md (constitution + enforcement map)

**Objective:** One place mapping each rule to a structural control (not SOUL text alone).

**Files:**
- Create: `carrier_hermes/GOVERNANCE.md`

**Content must include:**

| Rule | Structural control |
|---|---|
| No sends | No mail-send MCP/CLI in any profile `hermes tools` dump |
| Vault write `_agent/` only | `HERMES_WRITE_SAFE_ROOT` or Docker volume RO+rw split |
| Tool scope | Per-profile toolsets; Kanban worker profile pin |
| Idempotency | `state.json` + schema validator before side effects |
| Dual audit | `state.db` + `_agent/audit/events.jsonl` append-only + Discord critical |
| Kill authority | `scripts/dispatch_lock.sh` + CoS preflight + watcher script |
| Prompt injection | email_reader: no discord/todoist/calendar/send; untrusted tag in SOUL |
| Coding isolation | FirstMate only; worktrees; never push main |

**Step 1:** Write file. **Step 2:** Commit.

---

### Task 4: Scripts — dispatch lock

**Objective:** Real pause/kill primitive the watcher can set without an LLM.

**Files:**
- Create: `carrier_hermes/scripts/dispatch_lock.sh`
- Create: `carrier_hermes/scripts/tests/test_dispatch_lock.sh`

**Step 1:** Implement `dispatch_lock.sh`:

```bash
#!/usr/bin/env bash
# Usage: dispatch_lock.sh {check|set|clear} [reason]
set -euo pipefail
LOCK_PATH="${CARRIER_DISPATCH_LOCK:-$HOME/.hermes/carrier/DISPATCH_LOCK}"
mkdir -p "$(dirname "$LOCK_PATH")"
cmd="${1:-check}"
case "$cmd" in
  check)
    if [[ -f "$LOCK_PATH" ]]; then
      echo "LOCKED"
      cat "$LOCK_PATH"
      exit 10
    fi
    echo "OPEN"
    exit 0
    ;;
  set)
    reason="${2:-unspecified}"
    printf 'locked_at=%s\nreason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" >"$LOCK_PATH"
    echo "SET $LOCK_PATH"
    ;;
  clear)
    rm -f "$LOCK_PATH"
    echo "CLEARED"
    ;;
  *) echo "usage: $0 check|set|clear [reason]" >&2; exit 2 ;;
esac
```

**Step 2:** Test

```bash
bash scripts/dispatch_lock.sh clear
bash scripts/dispatch_lock.sh check   # expect OPEN, exit 0
bash scripts/dispatch_lock.sh set "test"
bash scripts/dispatch_lock.sh check   # expect LOCKED, exit 10
bash scripts/dispatch_lock.sh clear
```

**Step 3:** Commit.

---

### Task 5: Scripts — append-only audit helper

**Objective:** Cheap dual-audit stand-in (session DB + local append-only file).

**Files:**
- Create: `carrier_hermes/scripts/audit_append.sh`

**Behavior:** Append one JSON line to `$VAULT/_agent/audit/events.jsonl` with `ts`, `agent`, `event`, `detail`. Create dir if missing. Never rewrite file.

**Step 1:** Implement + manual test one line. **Step 2:** Commit.

---

### Task 6: Scripts — watcher heartbeat (no_agent)

**Objective:** Zero-token monitor every 5 minutes with lock authority.

**Files:**
- Create: `carrier_hermes/scripts/watcher_heartbeat.sh`

**Checks (deterministic, no LLM):**
1. Gateway process alive (`pgrep -f` hermes gateway or `hermes status` parse).
2. Cron scheduler recently ticked (mtime of cron output dir or jobs state).
3. Dispatch lock status.
4. Disk free on `$HOME` > threshold.
5. Optional: count recent session files / error log grep for 429.
6. If gateway dead OR error storm → Discord webhook (curl) + `dispatch_lock.sh set`.
7. If healthy → exit 0 with empty stdout when `no_agent` delivery should stay silent **or** write one line to `_agent/watcher/heartbeat.log`.

**Stdout contract for Hermes cron `no_agent`:**
- Empty stdout = silent (no user spam)
- Non-empty = deliver alert text to Discord

**Step 1:** Implement. **Step 2:** Dry-run locally. **Step 3:** Commit.

---

### Task 7: Scripts — external watchdog (outside Hermes)

**Objective:** Break circular dependency if Hermes itself is dead.

**Files:**
- Create: `carrier_hermes/scripts/external_hermes_watchdog.sh`
- Create: `carrier_hermes/scripts/com.carrier.hermes-watchdog.plist.example` (LaunchAgent)

**Behavior:** Every 5m via launchd/cron: if no gateway heartbeat file fresher than 12m → Discord webhook “Hermes down”. Does not use `hermes` CLI if process dead—use `pgrep` + heartbeat mtime only.

**Step 1:** Implement + example plist. **Step 2:** Commit. (User installs LaunchAgent manually in SETUP.)

---

### Task 8: JSON schemas + validator for specialists

**Objective:** Stop free-model-quality variance from writing garbage to Todoist/state even when using paid DeepSeek.

**Files:**
- Create: `carrier_hermes/schemas/email_triage.schema.json`
- Create: `carrier_hermes/schemas/calendar_sync.schema.json`
- Create: `carrier_hermes/schemas/firstmate_fleet.schema.json`
- Create: `carrier_hermes/scripts/validate_specialist_json.py`

**Step 1:** Minimal schemas (email: message_id, urgency enum, action enum, summary; calendar: event_id, todoist_action, idempotency_key).

**Step 2:** Validator CLI:

```bash
python3 scripts/validate_specialist_json.py schemas/email_triage.schema.json path/to/out.json
# exit 0 ok, 1 fail
```

Use stdlib only if possible; else document `jsonschema` in venv.

**Step 3:** Unit-ish tests with good/bad fixtures under `scripts/tests/fixtures/`.

**Step 4:** Commit.

---

### Task 9: Model aliases + MoA + aux (SETUP section rewrite content)

**Objective:** Cost-optimal pins committed as docs + SETUP commands (execution later).

**Files:**
- Modify: `carrier_hermes/moa/frontier_preset.md`
- Modify: `carrier_hermes/prompts/SETUP_PROMPT.md` (partial—full rewrite Task 18)

**Aliases to set (final):**

```bash
hermes config set model.aliases.chief-of-staff xai-oauth/grok-4.5
hermes config set model.aliases.smart xai-oauth/grok-4.5
hermes config set model.aliases.quality anthropic/claude-sonnet-4-6
hermes config set model.aliases.frontier-quality anthropic/claude-opus-4-8
hermes config set model.aliases.specialist openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.specialist-coding anthropic/claude-sonnet-4-6
hermes config set model.aliases.rote openrouter/deepseek/deepseek-chat-v3-0324
# watcher alias unused for heartbeat LLM; keep for optional daily summary only:
hermes config set model.aliases.watcher-summary openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.cheap openrouter/deepseek/deepseek-chat-v3-0324
```

**Remove** free models from specialist/rote aliases entirely.

**MoA frontier:**
- Ref1: `openrouter/deepseek/deepseek-chat-v3-0324` (paid, stable) **or** one free ref if budget-tight
- Ref2: free maverick/scout **only as reference**, never sole decider
- Aggregator: `xai-oauth/grok-4.5`

**Aux:** pin free **with paid DeepSeek fallback** in config comments; if free 429, aux must not block main.

**Fallback chain:**
1. anthropic/claude-sonnet-4-6 (Max OAuth)
2. openrouter/deepseek/deepseek-chat-v3-0324 (paid)
3. Never free as last resort for CoS

**Step 1:** Update `moa/frontier_preset.md`. **Step 2:** Commit.

---

### Task 10: Chief of Staff SOUL — classifier + FirstMate default + lock preflight

**Objective:** CoS becomes a pure router with coding → FirstMate by default.

**Files:**
- Modify: `carrier_hermes/profiles/chief_of_staff/SOUL.md`

**Must include:**
1. Preflight: if dispatch lock held → tell Michael, do not dispatch.
2. Classification table:
   - coding/repo/PR/bugfix/implement/refactor/test → **firstmate** (always)
   - email read/triage → email_reader job
   - draft reply → email_drafter
   - calendar/todoist prep → calendar_manager
   - vault question → vault_librarian
   - web research report → research_agent
   - multi-perspective hard → `/moa`
3. Never claim to have file/terminal tools.
4. Briefs to specialists must be fully self-contained.
5. Prefer Kanban task create / profile cron trigger over `delegate_task` for named bots.
6. Concise user updates: what dispatched, to whom, job id.

**Step 1:** Rewrite SOUL. **Step 2:** Commit.

---

### Task 11: Create FirstMate profile + contract port

**Objective:** Multi-bot coding lane preserved and default.

**Files:**
- Create: `carrier_hermes/profiles/firstmate/SOUL.md`
- Create: `carrier_hermes/firstmate/AGENTS.md` (adapt from carrier_ops; Hermes runtime)
- Create: `carrier_hermes/firstmate/projects.yaml.example`
- Create: `carrier_hermes/firstmate/roles/{implementer,reviewer,test-writer,docs-writer,janitor}.md`

**SOUL essentials:**
- You are FirstMate for coding only; no email/calendar tools.
- One crewmate per task; parallel only if no overlapping paths.
- Branch pattern `hermes/<project>/<short-description>`; never push main/master.
- Credential scan before commit (keep grep from carrier_ops).
- Fleet state: `_agent/state/firstmate-fleet.json` (schema-validated).
- Prefer Hermes `delegation.worktree_isolation: true` and/or `claude-code` / `codex` skills when available.
- Model: Sonnet (quality) for implementer/reviewer; specialist/DeepSeek or Sonnet-light for janitor/docs/tests as cost allows—**prefer Max sub over free**.

**Role model pins (cost-optimal):**

| Role | Model |
|---|---|
| implementer | `quality` = claude-sonnet-4-6 (Max) |
| reviewer | `quality` or `frontier-quality` only if user asks deep review |
| test-writer | `specialist` paid DeepSeek **or** Sonnet if tests are subtle |
| docs-writer | `specialist` paid DeepSeek |
| janitor | `specialist` paid DeepSeek |

**Step 1:** Write all files. **Step 2:** Commit.

---

### Task 12: FirstMate Hermes skill (global skill content in repo)

**Objective:** Loadable skill so any Hermes session routes coding through FirstMate workflow.

**Files:**
- Create: `carrier_hermes/skills/firstmate/SKILL.md`  
  (install path later: `~/.hermes/skills/firstmate/SKILL.md` or profile skills)

**SKILL.md must say:**
- Trigger: coding, PR, implement, refactor, test, debug in a git repo
- Steps: read `firstmate/AGENTS.md` → claim paths in fleet state → worktree → role prompt → validate → update fleet state → report
- Never use free rotating models for implementer
- Integrate with existing `claude-code` / `codex` / `opencode` skills as backends when present

**Step 1:** Write skill. **Step 2:** Commit.

---

### Task 13: Harden specialist SOULs (email, calendar, draft, vault, research)

**Objective:** Align SOULs with structural tools, schemas, shadow mode, cost pins.

**Files:**
- Modify: `profiles/email_reader/SOUL.md`
- Modify: `profiles/email_drafter/SOUL.md`
- Modify: `profiles/calendar_manager/SOUL.md`
- Modify: `profiles/vault_librarian/SOUL.md`
- Modify: `profiles/research_agent/SOUL.md`
- Modify: `profiles/subscription_watcher/SOUL.md`

**Per-profile requirements:**

**email_reader**
- Model: specialist paid DeepSeek only
- Tools: mail read MCP/CLI when present; `file` only under `_agent/email/`
- Output must pass `email_triage.schema.json`
- Tag all email bodies as untrusted
- No web if not required (prefer no exfil path); if web needed for links, strip write of secrets

**email_drafter**
- Model: quality Sonnet (Max)
- Read triage + People/; write `_agent/drafts/` only
- Discord #drafts summary; never send
- Load `my-writing-style` if present

**calendar_manager**
- Model: specialist paid DeepSeek
- Calendar read + Todoist; no email tools
- Validate with `calendar_sync.schema.json` before Todoist write
- Shadow flag: if `SHADOW_MODE=1` or state says shadow → write proposals only, no Todoist mutations

**vault_librarian**
- Model: quality Sonnet
- Write `_agent/` only; proposals for structure

**research_agent**
- Model: quality Sonnet (synthesis on sub beats free)
- Browser read-only; write `_agent/research/`
- For bulk page scrapes only, may call cheap extract paths

**subscription_watcher**
- Primary path: **no LLM** — document that cron is `no_agent` + `watcher_heartbeat.sh`
- Optional weekly/daily summary job on paid DeepSeek (not every 5m)
- May set dispatch lock via script only
- Remove contradictory “write daily report via file tools” unless file tool enabled for report path only on the daily job profile

**Step 1:** Update all SOULs. **Step 2:** Commit.

---

### Task 14: Profile matrix doc (toolsets × models × MCP)

**Objective:** Single checklist SETUP and humans cannot drift.

**Files:**
- Create: `carrier_hermes/profiles/PROFILE_MATRIX.md`

| Profile | Model alias | Enable toolsets | MCP | Disable | Dispatch |
|---|---|---|---|---|---|
| chief_of_staff | smart (Grok) | delegation, kanban, cronjob, discord, memory, session_search, todo, clarify | none required | terminal, file, browser, web | gateway inbound |
| firstmate | quality (Sonnet) | terminal, file, git-via-terminal, delegation, memory, skills, session_search | github if any | mail, todoist, discord send spam | coding default |
| email_reader | specialist (DeepSeek paid) | file (sandboxed), mail-read | gws/mail when ready | terminal, discord, todoist, browser | kanban/cron |
| email_drafter | quality | file, memory, skills, discord | — | terminal, browser, web send | kanban |
| calendar_manager | specialist | file, todoist | todoist, calendar | email, browser | kanban/cron |
| vault_librarian | quality | file, memory, skills, web(read) | obsidian/OB1 | terminal, discord | kanban |
| research_agent | quality | web, browser, file, memory | — | terminal, discord | kanban |
| subscription_watcher | n/a (script) | none for heartbeat | — | everything | cron no_agent |

**Step 1:** Write matrix. **Step 2:** Commit.

---

### Task 15: SHADOW_MODE policy

**Objective:** Safe week-1 operation on live data without mutations.

**Files:**
- Create: `carrier_hermes/prompts/SHADOW_MODE.md`

**Rules:**
- Email: triage files only; no drafts that look like “queued send”
- Calendar: summary files only; Todoist dry-run / proposals
- FirstMate: allowed on non-prod repos; `scoped` mode default; no unsolicited PRs
- Exit shadow when: 7 days clean, schema validation >99%, no lock false positives, human reviewed 20 triage samples

**Step 1:** Write. **Step 2:** Commit.

---

### Task 16: Update README mapping table

**Objective:** Honest Hermes equivalents including FirstMate + Kanban.

**Files:**
- Modify: `carrier_hermes/README.md`

Replace firstmate row: `firstmate profile + worktrees + Kanban`  
Replace dual audit row with audit JSONL + state.db  
Replace watcher row with no_agent script  
Link COST_MODEL, GOVERNANCE, this plan.

**Step 1:** Edit. **Step 2:** Commit.

---

### Task 17: Smoke script

**Objective:** One command proves pins and governance hooks.

**Files:**
- Create: `carrier_hermes/scripts/smoke_fleet.sh`

**Checks:**
1. `dispatch_lock.sh check` works
2. `validate_specialist_json.py` good fixture passes / bad fails
3. `watcher_heartbeat.sh` runs exit 0 on healthy machine
4. Documents manual hermes commands for model pings (do not require network secrets in CI)

**Step 1:** Implement. **Step 2:** Run locally. **Step 3:** Commit.

---

### Task 18: Full SETUP_PROMPT.md rewrite

**Objective:** Paste-once setup that builds the hardened fleet (no free specialist pool, FirstMate, locks, Kanban notes).

**Files:**
- Modify: `carrier_hermes/prompts/SETUP_PROMPT.md` (replace entirely)

**Sections (ordered):**
1. Prerequisites (xai-oauth, anthropic oauth, OPENROUTER_API_KEY, recommend ≥$10 OR credits)
2. Copy scripts to `~/.hermes/scripts/` and chmod +x
3. Model aliases (Task 9 list)
4. MoA frontier
5. Aux + fallback chain
6. Write-safe root / vault path config
7. Create 8 profiles + copy SOULs + apply PROFILE_MATRIX toolsets
8. Install firstmate skill into Hermes skills dir
9. Enable `delegation.worktree_isolation: true` on firstmate profile (and document global if needed)
10. Discord gateway on chief_of_staff only
11. Cron: `watcher_heartbeat` every 5m **no_agent**
12. Cron: optional daily watcher summary (agent, DeepSeek, low temp)
13. External LaunchAgent instructions
14. Kanban board `carrier` + example recurring tasks (email triage shadow)
15. `_agent/` tree + audit dir + state files
16. Smoke tests including FirstMate “create empty branch dry-run in tmp repo”
17. Final checklist (expanded)

**Explicit SETUP failures:**
- Stop if mail MCP missing and user asked for live email—enter shadow stubs
- Stop if OpenRouter key missing
- Refuse to set specialist alias to `:free`

**Step 1:** Write full prompt. **Step 2:** Commit.

---

### Task 19: RISKS.md final go/no-go

**Objective:** Operational gates before live Todoist/calendar.

**Files:**
- Modify: `carrier_hermes/RISKS.md`

**Content:**
- Residual risks (single runtime, OAuth dual expiry, schema bypass if agent skips validator, Discord audit mutability)
- Go/no-go table from architecture review (updated)
- Top 3 mitigations status checklist

**Step 1:** Write. **Step 2:** Commit.

---

### Task 20: Optional — minimal firstmate fleet state helper

**Objective:** Path-claim collision detection without LLM.

**Files:**
- Create: `carrier_hermes/scripts/firstmate_fleet.py`

**Commands:** `claim`, `release`, `list-collisions` on `_agent/state/firstmate-fleet.json` validating schema.

**Step 1:** Implement with tests. **Step 2:** Commit.

---

### Task 21: Docs pass — internal consistency grep

**Objective:** No remaining docs that say free rotate specialists or delegate_task = firstmate.

**Files:** all markdown under `carrier_hermes/`

**Step 1:**

```bash
cd /Users/michaelkanter/carrier_hermes
rg -n "gemma-3n|:free|rotated pool|delegate_task to specialist" -g '*.md' || true
```

**Step 2:** Fix any hits. **Step 3:** Final commit `docs: consistency pass after hardening plan implementation`.

---

## Verification (fleet-level acceptance)

Run after SETUP on the machine (not during doc-only tasks):

```bash
# Structural
bash scripts/dispatch_lock.sh set "verify" && bash scripts/dispatch_lock.sh check; echo exit:$?
bash scripts/dispatch_lock.sh clear
python3 scripts/validate_specialist_json.py schemas/email_triage.schema.json scripts/tests/fixtures/email_triage_ok.json
bash scripts/watcher_heartbeat.sh
bash scripts/smoke_fleet.sh

# Hermes (manual)
hermes auth list
hermes config get model.aliases
hermes moa list
hermes profile list
hermes -p chief_of_staff chat -q "Classify only: 'fix the login bug in carrier_hermes'. Which bot handles it?"
# Expect: firstmate
hermes -p chief_of_staff chat -q "Classify only: 'triage my unread email'."
# Expect: email_reader
hermes -p subscription_watcher cron list
# Expect: no_agent heartbeat job every 5m
```

**Acceptance criteria:**
- [ ] No profile has mail-send capability
- [ ] specialist alias is paid DeepSeek only
- [ ] Coding classification → firstmate
- [ ] Watcher 5m job is no_agent script
- [ ] External watchdog plist example present
- [ ] Dispatch lock blocks CoS dispatch language in SOUL + script exists
- [ ] Schemas validate specialist outputs
- [ ] Shadow mode documented and default for calendar writes
- [ ] Multi-bot: 8 profiles remain
- [ ] COST_MODEL anti-patterns have zero violations in repo docs

---

## Out of scope (YAGNI for this plan)

- Rebuilding Nostr buzz / maka
- Full OpenMausBot approval card UI
- Automatic Discord reaction → send pipeline
- Podiom / OpenClaw / LiteLLM
- Doppler / WSL2 firstmate uid isolation (macOS Hermes worktrees + skills instead)
- Financial Oversight agent (V2 when API $ burn matters)
- Perfect LiteLLM-grade spend dashboard

---

## Risks & tradeoffs

| Tradeoff | Choice | Why |
|---|---|---|
| Paid DeepSeek vs free rotate | Paid pin | Consistency on email/calendar > $0.00 |
| Kanban vs delegate_task for bots | Kanban/profile cron | Real toolset isolation |
| Grok CoS vs Claude CoS | Grok primary | $0 marginal + good dispatch; quality bots on Claude |
| Script watcher vs LLM watcher | Script | $0 + real kill path |
| FirstMate in-Hermes vs external firstmate-dispatch repo | In-repo skill+profile first | One runtime; port contract from carrier_ops |
| Sonnet implementer vs DeepSeek implementer | Sonnet default | Code quality; user can override per project mode |

**Open questions (resolve during SETUP if needed):**
1. Exact vault path on this Mac (`Desktop/Existing Folders/Second Brain` vs other).
2. Which mail surface is real in 2026 setup (Google Workspace MCP vs Spark CLI vs himalaya)?
3. Is GitHub MCP or `gh` CLI preferred for FirstMate PRs when asked?
4. Discord webhook URL storage (`.env` only, never vault).

---

## Implementation order reminder

Docs (1–3) → scripts/locks/audit/watcher (4–8) → models (9) → SOULs + FirstMate (10–13) → matrix/shadow/readme (14–16) → smoke + SETUP + risks (17–19) → fleet helper + grep (20–21) → **human runs SETUP in shadow** → 7-day review → enable calendar/Todoist mutations.

**Do not** run live email send or unattended calendar writes in this plan’s delivery.

---

## Execution handoff

After this plan is approved, implement with subagent-driven-development: one fresh subagent per task, spec compliance review, then code quality review, commit per task.

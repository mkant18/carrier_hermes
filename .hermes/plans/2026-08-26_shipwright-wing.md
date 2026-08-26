# Shipwright Wing — Autonomous Maintenance Team: Implementation Plan

> **For Hermes:** This is a planning-only document. Do not implement until Michael approves and explicitly says "proceed."

**Goal:** Stand up a 5-bot autonomous maintenance wing that crawls the repo for code health issues, plans and implements fixes, submits PRs via Yeoman, reviews and iterates on them, and merges — all self-scheduled around LLM and subscription availability. Marshal owns the Kanban board; merge events surface in the hourly fleet status update.

**Architecture:**  
Wing Lead (Bosun) dispatches sequentially: Diver → Rigger → Caulker → Surveyor, with an iteration loop between Caulker and Surveyor until the PR is merge-ready. The entire pipeline is triggered by an availability-aware cron that checks local LLM health and subscription load before firing. A dedicated Discord bot application (Shipwright) represents the wing in the server.

**Tech Stack:** Hermes profiles, BOT_MATRIX, Kanban (carrier board), AIPass, git_yeoman, Ollama (qwen2.5:7b), Claude Max OAuth, SuperGrok OAuth, OpenRouter allowlist (Gemini Flash Lite / DeepSeek flash as last resort only), GitHub gh CLI.

---

## Team Roster — Shipwright Wing 🛠️

| bot_id | Callsign | Emoji | Role | Primary Model | Fallback Chain |
|---|---|---|---|---|---|
| `maintenance_lt` | Bosun | 🛠️ | Wing Lead — dispatch & review only | `claude-sonnet-5/anthropic` (OAuth) | `grok-4.5/xai-oauth` |
| `code_auditor` | Diver | 🤿 | Repo crawler + log inspector | `custom/qwen2.5:7b-instruct-q4_K_M` (local) | `claude-sonnet-5/anthropic` → `grok-4.5/xai-oauth` |
| `repair_planner` | Rigger | 🪢 | Fix design & task-list author | `claude-opus-4-5/anthropic` (OAuth) | `claude-sonnet-5/anthropic` → `grok-4.5/xai-oauth` → `google/gemini-2.5-flash-lite` (OR, last resort) |
| `patch_writer` | Caulker | ⚒️ | Fix implementer (code writer) | `custom/qwen2.5:7b-instruct-q4_K_M` (local) | `claude-haiku-4-5/anthropic` → `claude-sonnet-5/anthropic` → `grok-4.5/xai-oauth` |
| `pr_reviewer` | Surveyor | 🧭 | PR reviewer & merge gatekeeper | `claude-opus-4-5/anthropic` (OAuth) | `claude-sonnet-5/anthropic` → `grok-4.5/xai-oauth` → `google/gemini-2.5-flash-lite` (OR, last resort) |

### Model Routing Policy Notes
- **Rigger & Surveyor** (planning + review): OAuth-only primary (`claude-opus-4-5` or `claude-sonnet-5`). Second fallback = xai-oauth Grok 4.5. OpenRouter is **absolute last resort** and MUST be cheapest allowlisted model only (`google/gemini-2.5-flash-lite`). NEVER a frontier model over OR.
- **Diver & Caulker** (crawl + implement): Local LLM primary. OAuth fallbacks only — no OpenRouter in the fallback chain (subscription OAuth is $0, metered fallback adds no value).
- **Bosun (LT)**: Same as existing LTs — `claude-sonnet-5/anthropic` → `grok-4.5/xai-oauth`. No local LLM. No OpenRouter.
- The billing guard must pass at `PASS` for all 5 new profiles before any bot is activated.

---

## New Discord Bot Application — "Shipwright"

The wing needs a dedicated Discord bot application to appear in the server under its own identity (separate from Carrier Ops/Helm and First Watch). This is a **human-gated step** (Discord Developer Portal MFA required).

### Human Gate: Discord App Creation
1. Go to https://discord.com/developers/applications → **New Application** → name: `Shipwright`
2. Under **Bot** tab → **Add Bot** → copy the token
3. Disable **Public Bot**; enable **Message Content Intent** and **Server Members Intent**
4. Invite to server: `https://discord.com/api/oauth2/authorize?client_id=<APP_ID>&permissions=85056&scope=bot%20applications.commands`
5. Store token in Doppler: `doppler secrets set SHIPWRIGHT_DISCORD_TOKEN="<token>" --project carrier-ops --config prd`
6. Record the Application ID in Doppler as `SHIPWRIGHT_DISCORD_APP_ID`

### Gateway Rule
**Shipwright does NOT open a WebSocket gateway.** Helm is the sole Discord gateway poller (fleet rule). Shipwright uses **First Watch REST outbound** for all notifications to `#maintenance` (new channel) and `#fleet`. The token is available to any bot that needs to POST via REST but no bot opens a gateway with it.

### New Discord Channel
Create `#maintenance` in the server (or `#drydock`) for Shipwright-wing status updates, separate from `#fleet`. Bosun posts wing status here; merge summaries also go to `#fleet` via the normal fleet_checkin pipeline.

---

## Wing Workflow — Sequential Pipeline

```
[Availability-aware cron fires]
        ↓
 Bosun (maintenance_lt)
  - Checks pre-flight: Ollama healthy? Subscription load light?
  - Dispatches Diver via Kanban
        ↓
 Diver (code_auditor)
  - Crawls repo: bugs, dead code, redundancy, inefficiency (AST + rg + pylint/ruff)
  - Reviews ALL run logs: agent.log, gateway.log, state.db failures
  - Writes: _agent/maintenance/audit_report_<date>.md
        ↓
 Bosun reviews Diver's report (AIPass / Kanban comment)
  - Validates completeness; marks any false-positives
  - Dispatches Rigger with report path
        ↓
 Rigger (repair_planner)
  - Reads audit_report_<date>.md
  - Groups issues by severity, root-cause, effort
  - Designs fixes: exact files, approach, test plan, expected outcome
  - Writes: _agent/maintenance/fix_plan_<date>.md
        ↓
 Bosun reviews Rigger's fix plan
  - Gates: ensures fixes are safe, scoped, no breaking changes
  - Dispatches Caulker with fix_plan path
        ↓
 Caulker (patch_writer)  ←────────────────────────────┐
  - Implements ALL fixes from fix_plan (local LLM)    │
  - Creates feature branch: maint/<date>/fixes          │
  - Stages, commits each fix atomically                  │
  - Requests Yeoman to open PR when complete             │
  - Posts PR URL to Bosun via AIPass                     │
        ↓                                                │
 Surveyor (pr_reviewer)                                  │
  - Reviews PR: correctness, billing guard, tests        │
  - If changes needed → writes fix_requests_<date>.md   │
    and AIPass-notifies Caulker with specific file       │
    patches needed ──────────────────────────────────────┘
  - If APPROVED → instructs Yeoman to merge
  - Posts merge summary (PR title + description) to Bosun via AIPass
        ↓
 Bosun
  - Receives merge notification
  - Writes merge event to _agent/maintenance/merge_log.jsonl
  - Merge summary is picked up by fleet_checkin.py in next hourly run
```

---

## Availability-Aware Scheduling

The cron does NOT fire the pipeline unconditionally. A **pre-flight script** runs first and suppresses the agent turn if conditions aren't met.

### Pre-flight Conditions (ALL must pass)
1. **Ollama healthy**: `curl -s --max-time 5 http://localhost:11434/api/tags` returns 200 and includes `qwen2.5:7b-instruct-q4_K_M`
2. **Anthropic OAuth usable**: `state.db` shows the fleet has NOT hit a rate-limit or quota-wall in the last 2h (check `session_model_usage.last_seen` for recent errors)
3. **No DISPATCH_LOCK or SPEND_HALT**: `~/.hermes/carrier/DISPATCH_LOCK` and `SPEND_HALT` do not exist
4. **No other maintenance run in progress**: `state.db` on `maintenance_lt` shows no `in_progress` Kanban task
5. **Quiet window**: Fewer than N active bot sessions in the last 15 minutes (threshold TBD — likely ≤ 4 active sessions)

### Cron Schedule
```
schedule: "0 2 * * *"   # 2 AM daily — low-usage window; adjust as fleet grows
```
Or a smarter schedule: `"0 2,10,18 * * *"` (3× daily, 3 attempts, first one to pass pre-flight wins — others are no-ops if run is still in progress).

The cron uses `monitor_script` (hash-suppression) so if conditions haven't changed and a run is already in-progress, the cron tick is silent.

---

## BOT_MATRIX Additions

Add the following section to `bots/BOT_MATRIX.md` after the Coding Wing section:

```markdown
## Shipwright Wing (Autonomous Maintenance)

Fully autonomous maintenance pipeline. Runs on a schedule. No user input required per-run.
All bots report to Marshal via Kanban. Bosun is the ONLY dispatcher for this wing.

| bot_id | Callsign | Model | Toolsets ON | Toolsets OFF | MCP |
|---|---|---|---|---|---|
| `maintenance_lt` | Bosun 🛠️ | `quality` Sonnet 5 OAuth → Grok 4.5 xai-oauth | kanban (dispatch/review), AIPass, session_search, memory (`_agent/maintenance_lt/**`), file `_agent/maintenance_lt/**`, discord `#maintenance` + `#fleet` via Shipwright REST | terminal, code_execution, browser, computer_use, delegation, web, mail, todoist, calendar, OSB write | none |
| `code_auditor` | Diver 🤿 | local qwen2.5:7b → Sonnet 5 OAuth → Grok 4.5 | terminal **narrow** (rg, ruff, pylint, git log, log tail — READ-ONLY, NO git write), file `_agent/maintenance/**` (write) + repo (read-only), session_search | mail, todoist, calendar, OSB write, delegation, kanban-as-owner, browser, computer_use | none |
| `repair_planner` | Rigger 🪢 | Opus 4.5 OAuth → Sonnet 5 OAuth → Grok 4.5 xai-oauth → gemini-flash-lite OR (last resort) | file `_agent/maintenance/**` (read+write), session_search, memory (coding meta), skills | terminal, code_execution, browser, computer_use, delegation, web, mail, todoist, calendar, OSB write | none |
| `patch_writer` | Caulker ⚒️ | local qwen2.5:7b → Haiku OAuth → Sonnet 5 OAuth → Grok 4.5 | terminal (git branch/add/commit/push, ruff/pytest narrow), file (repo write + `_agent/maintenance/**`), code_execution, skills (github-pr-workflow), AIPass (to Yeoman + Bosun), session_search | mail, todoist, calendar, OSB write, browser, computer_use, kanban-as-owner | none |
| `pr_reviewer` | Surveyor 🧭 | Opus 4.5 OAuth → Sonnet 5 OAuth → Grok 4.5 xai-oauth → gemini-flash-lite OR (last resort) | terminal **narrow** (gh pr view, gh pr diff, billing_guard.py read-only), file `_agent/maintenance/**`, skills (github-code-review), AIPass (to Caulker + Bosun + Yeoman), session_search | mail, todoist, calendar, OSB write, delegation, computer_use, kanban-as-owner | none |
```

### Hard rules for this wing:
- **Diver is READ-ONLY on the repo** — no `git write`, no file mutations outside `_agent/maintenance/`
- **Caulker does NOT open PRs directly** — always goes through Yeoman (same protocol as Mate)
- **Surveyor does NOT merge directly** — instructs Yeoman to merge (Yeoman is the only bot with `gh pr merge` authority)
- **Bosun never executes code** — same Lt hard rule as all other LTs
- **All 5 bots must pass billing_guard** before any dispatch

---

## File/Directory Structure

```
C:\Users\micha\AppData\Local\hermes\
├── profiles\
│   ├── maintenance_lt\          ← new
│   │   ├── config.yaml
│   │   ├── .env
│   │   └── home\_agent\maintenance_lt\
│   │       ├── inbox\
│   │       └── outbox\
│   ├── code_auditor\            ← new
│   │   ├── config.yaml
│   │   ├── .env
│   │   └── home\_agent\maintenance\
│   │       ├── audit_report_<date>.md
│   │       └── ...
│   ├── repair_planner\          ← new
│   │   ├── config.yaml
│   │   ├── .env
│   │   └── home\_agent\maintenance\
│   │       ├── fix_plan_<date>.md
│   │       └── ...
│   ├── patch_writer\            ← new
│   │   ├── config.yaml
│   │   ├── .env
│   │   └── home\_agent\maintenance\
│   │       ├── fix_requests_<date>.md (inbound from Surveyor)
│   │       └── ...
│   └── pr_reviewer\             ← new
│       ├── config.yaml
│       ├── .env
│       └── home\_agent\maintenance\
│           ├── review_<pr#>_<date>.md
│           └── ...

C:\Users\micha\carrier_hermes\
├── bots\
│   └── BOT_MATRIX.md            ← add Shipwright Wing section
├── scripts\
│   ├── maintenance_preflight.py ← new (pre-flight availability check)
│   ├── maintenance_dispatch.py  ← new (Bosun dispatch orchestrator)
│   └── maintenance_merge_hook.py← new (writes to merge_log.jsonl, notifies fleet_checkin)
├── prompts\
│   ├── maintenance_lt.md        ← new (Bosun system prompt)
│   ├── code_auditor.md          ← new (Diver system prompt)
│   ├── repair_planner.md        ← new (Rigger system prompt)
│   ├── patch_writer.md          ← new (Caulker system prompt)
│   └── pr_reviewer.md           ← new (Surveyor system prompt)
└── .hermes\plans\
    └── 2026-08-26_shipwright-wing.md (this file)
```

---

## Implementation Tasks

### Phase 0 — Human Gate (Michael only)

**Task 0.1: Create Shipwright Discord Application**
- Go to Discord Developer Portal → New Application → "Shipwright" 
- Create bot, copy token
- Store in Doppler: `SHIPWRIGHT_DISCORD_TOKEN`, `SHIPWRIGHT_DISCORD_APP_ID`
- Invite to server with bot + message permissions
- Create `#maintenance` channel in server

**Task 0.2: Confirm Ollama model availability**
- Run: `curl http://localhost:11434/api/tags | python -m json.tool`
- Confirm `qwen2.5:7b-instruct-q4_K_M` is present
- If missing: `ollama pull qwen2.5:7b-instruct-q4_K_M`

---

### Phase 1 — Profile Creation

**Task 1.1: Create `maintenance_lt` profile**

```bash
HPY="C:/Users/micha/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
HERMES_HOME="C:/Users/micha/AppData/Local/hermes"
hermes profile create maintenance_lt --display-name "Bosun 🛠️"
```

Config (`profiles/maintenance_lt/config.yaml`):
```yaml
display_name: "Bosun 🛠️"
system_prompt_file: "C:/Users/micha/carrier_hermes/prompts/maintenance_lt.md"
provider: anthropic
model: claude-sonnet-5
fallback_chain:
  - provider: xai-oauth
    model: grok-4.5
toolsets:
  enabled:
    - kanban
    - todo
    - session_search
    - memory
    - file
    - aipass
  disabled:
    - terminal
    - code_execution
    - browser
    - web
    - computer_use
    - delegation
    - mail
    - mail_send
    - todoist
    - calendar
```

**Task 1.2: Create `code_auditor` profile**

Config (`profiles/code_auditor/config.yaml`):
```yaml
display_name: "Diver 🤿"
system_prompt_file: "C:/Users/micha/carrier_hermes/prompts/code_auditor.md"
provider: custom
model: qwen2.5:7b-instruct-q4_K_M
custom_provider:
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
fallback_chain:
  - provider: anthropic
    model: claude-sonnet-5
  - provider: xai-oauth
    model: grok-4.5
toolsets:
  enabled:
    - file
    - terminal
    - session_search
    - aipass
  disabled:
    - code_execution
    - browser
    - web
    - computer_use
    - delegation
    - mail
    - mail_send
    - todoist
    - calendar
    - kanban
```

Terminal restrictions for Diver (in config or via MCP filter):
```yaml
terminal_allowlist:
  - "rg"
  - "ruff check"
  - "pylint"
  - "git log"
  - "git diff"
  - "git status"
  - "tail"
  - "cat"
  - "python.*billing_guard.*--read-only"
```
> **No `git write`, no `git commit`, no `git push`, no `rm`, no pip install.**

**Task 1.3: Create `repair_planner` profile**

Config (`profiles/repair_planner/config.yaml`):
```yaml
display_name: "Rigger 🪢"
system_prompt_file: "C:/Users/micha/carrier_hermes/prompts/repair_planner.md"
provider: anthropic
model: claude-opus-4-5
fallback_chain:
  - provider: anthropic
    model: claude-sonnet-5
  - provider: xai-oauth
    model: grok-4.5
  - provider: openrouter
    model: google/gemini-2.5-flash-lite   # last resort only — cheapest allowlisted
toolsets:
  enabled:
    - file
    - session_search
    - memory
    - skills
    - aipass
  disabled:
    - terminal
    - code_execution
    - browser
    - web
    - computer_use
    - delegation
    - mail
    - mail_send
    - todoist
    - calendar
    - kanban
```

**Task 1.4: Create `patch_writer` profile**

Config (`profiles/patch_writer/config.yaml`):
```yaml
display_name: "Caulker ⚒️"
system_prompt_file: "C:/Users/micha/carrier_hermes/prompts/patch_writer.md"
provider: custom
model: qwen2.5:7b-instruct-q4_K_M
custom_provider:
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
fallback_chain:
  - provider: anthropic
    model: claude-haiku-4-5
  - provider: anthropic
    model: claude-sonnet-5
  - provider: xai-oauth
    model: grok-4.5
toolsets:
  enabled:
    - file
    - terminal
    - code_execution
    - skills
    - aipass
    - session_search
  disabled:
    - browser
    - web
    - computer_use
    - delegation
    - mail
    - mail_send
    - todoist
    - calendar
    - kanban
```

Terminal scope for Caulker (git write IS allowed, but scoped):
```yaml
terminal_allowlist:
  - "git checkout -b"
  - "git add"
  - "git commit"
  - "git push"
  - "ruff"
  - "pytest"
  - "python"
```
> Caulker can write code and commit, but PR creation goes through Yeoman AIPass only.

**Task 1.5: Create `pr_reviewer` profile**

Config (`profiles/pr_reviewer/config.yaml`):
```yaml
display_name: "Surveyor 🧭"
system_prompt_file: "C:/Users/micha/carrier_hermes/prompts/pr_reviewer.md"
provider: anthropic
model: claude-opus-4-5
fallback_chain:
  - provider: anthropic
    model: claude-sonnet-5
  - provider: xai-oauth
    model: grok-4.5
  - provider: openrouter
    model: google/gemini-2.5-flash-lite   # last resort only
toolsets:
  enabled:
    - file
    - terminal
    - skills
    - aipass
    - session_search
  disabled:
    - code_execution
    - browser
    - web
    - computer_use
    - delegation
    - mail
    - mail_send
    - todoist
    - calendar
    - kanban
```

Terminal scope for Surveyor (read-only):
```yaml
terminal_allowlist:
  - "gh pr view"
  - "gh pr diff"
  - "gh pr checks"
  - "python.*billing_guard.*--read-only"
  - "git log"
  - "git diff"
```
> Surveyor NEVER runs `gh pr merge` directly — sends AIPass to Yeoman.

---

### Phase 2 — System Prompts

**Task 2.1: Write `prompts/maintenance_lt.md` (Bosun)**

Key sections:
- Identity: Wing Lead for Shipwright Wing. Route and review. Never write code or execute commands.
- Pre-flight: before dispatching, verify maintenance_preflight.py output shows all-green
- Dispatch protocol: sequential — Diver → review → Rigger → review → Caulker → Surveyor (with iteration loop)
- Review gates: what constitutes a complete audit report, a valid fix plan, a complete implementation
- AIPass format for inter-bot hand-offs: structured YAML frontmatter job packets
- Marshal notification: after merge, write to merge_log.jsonl and AIPass Marshal

**Task 2.2: Write `prompts/code_auditor.md` (Diver)**

Key sections:
- Identity: READ-ONLY code health crawler. Never mutate the repo.
- Scope of crawl:
  - `rg` for TODO/FIXME/HACK/BUG/DEPRECATED markers
  - `ruff check` across all Python files (capture all violations)
  - `pylint` for structural issues (unused imports, unreachable code, etc.)
  - `git log --since="30 days ago" --grep="error\|fix\|fail\|broken"` for recent known-bad commits
  - ALL `profiles/*/logs/agent.log` files: grep for ERROR, EXCEPTION, Traceback, rate_limit, quota
  - ALL `profiles/*/state.db`: query `session_model_usage` for billing_provider != expected pattern
  - `kanban.db` on carrier board: check for tasks with `status='failed'` or `consecutive_failures > 0`
  - `scripts/` and `plugins/` for hardcoded paths, API keys, or deprecated patterns
- Output format: structured `audit_report_<YYYY-MM-DD>.md` with severity tiers (CRITICAL / HIGH / MEDIUM / LOW)

**Task 2.3: Write `prompts/repair_planner.md` (Rigger)**

Key sections:
- Identity: Fix architect. Read Diver's audit report. Design safe, minimal, tested fixes.
- Input: path to `audit_report_<date>.md` (passed via AIPass job packet)
- Planning approach:
  - Group issues by root cause (don't fix the same thing 5 times)
  - For each fix: exact file, exact line range, proposed change, test to verify, risk level
  - Billing-guard-safe: no fix should introduce API keys, frontier OR models, or bypass guards
  - Order fixes: CRITICAL first, then HIGH, then MEDIUM (LOW optional, mark as such)
  - For each fix: define done-criteria (what Caulker must produce to mark it complete)
- Output format: `fix_plan_<date>.md` with numbered fixes, file paths, exact diffs where possible

**Task 2.4: Write `prompts/patch_writer.md` (Caulker)**

Key sections:
- Identity: Code implementer. Work from fix_plan. Local LLM for code. OAuth fallback only.
- Input: path to `fix_plan_<date>.md` (passed via AIPass job packet)
- Workflow per fix:
  1. Read the fix spec (file + line range + approach)
  2. Implement using code_execution / file tools (local LLM thinks through the change)
  3. Run `ruff` on changed file
  4. Run relevant tests if present (`pytest tests/ -k <related_test> -x`)
  5. `git add <file>` + `git commit -m "maint: <fix description> [shipwright]"`
- Branch: `git checkout -b maint/<YYYY-MM-DD>/fixes` before first commit
- PR creation: AIPass to Yeoman with:
  - Branch name
  - PR title: `🛠️ Maintenance: <N> fixes, <date>`
  - PR body: summary of all fixes (one line each with severity and file)
- After PR created: AIPass to Bosun with PR URL
- Iteration: if Surveyor sends fix_requests back via AIPass, apply them on the SAME branch, push, re-notify Bosun

**Task 2.5: Write `prompts/pr_reviewer.md` (Surveyor)**

Key sections:
- Identity: PR gatekeeper. Read the PR diff. Approve or request changes. Never merge directly.
- Input: PR URL or number (from Bosun AIPass)
- Review checklist:
  - [ ] All fixes from fix_plan implemented (none skipped silently)
  - [ ] No new billing guard violations (`gh pr diff` + grep for API keys / OR frontier models)
  - [ ] No `git add -A` sweeping in unrelated worktree files
  - [ ] `ruff` passes on all changed files
  - [ ] Tests pass (check PR CI status via `gh pr checks`)
  - [ ] Commit messages follow `maint:` prefix convention
  - [ ] PR description accurately summarizes changes
- If changes needed: write `fix_requests_<date>.md` with exact file+line corrections → AIPass to Caulker
- If approved: AIPass to Yeoman: "merge PR #<N> — approved by Surveyor 🧭" + PR title + description
- After merge confirmed by Yeoman: AIPass to Bosun with merge summary (title + PR body excerpt + merge SHA)

---

### Phase 3 — Support Scripts

**Task 3.1: `scripts/maintenance_preflight.py`**

Checks:
1. Ollama running + model available (HTTP GET to `:11434/api/tags`)
2. `DISPATCH_LOCK` / `SPEND_HALT` files absent
3. `maintenance_lt` state.db: no `in_progress` Kanban task
4. Subscription OK: last anthropic call in `state.db` was not a rate-limit error
5. Quiet: count active sessions fleet-wide in last 15 min (`SELECT COUNT(*) FROM sessions WHERE started_at > ?`)

Exits 0 = all green (proceed). Exits 1 = suppressed (print single-line reason). Designed to be called as `monitor_script` in the cron so hash suppression works (stable output when suppressed = same "SUPPRESSED: <reason>" line).

**Task 3.2: `scripts/maintenance_dispatch.py`**

Called by Bosun's cron when preflight passes. Orchestrates:
- Inserts Kanban tasks for the pipeline (Diver → Rigger → Caulker → Surveyor) as a dependency chain in the carrier board DB
- Uses `task_links` table so Kanban auto-gates each step on the prior step's completion
- All tasks assigned to correct bot_id, status=ready (Diver first), rest blocked by parent link
- Sets `workspace_path='C:/Users/micha/carrier_hermes'` on Caulker task (needs worktree)

**Task 3.3: `scripts/maintenance_merge_hook.py`**

Called by Surveyor AIPass handler (or Bosun) after Yeoman confirms merge:
- Appends JSON line to `_agent/maintenance/merge_log.jsonl`:
  ```json
  {"ts": 1234567890, "pr": 42, "title": "🛠️ Maintenance: 7 fixes, 2026-08-26", "sha": "abc123", "fixes": 7, "wing": "shipwright"}
  ```
- `fleet_checkin.py` reads `merge_log.jsonl` and includes any unannounced merges in the hourly `#fleet` broadcast

---

### Phase 4 — fleet_checkin.py Extension

**Task 4.1: Add Shipwright merge reporting to `fleet_checkin.py`**

Modify the existing script:
```python
# In fleet_checkin.py, after wing summary block:
merge_log = Path(r"C:\Users\micha\AppData\Local\hermes\profiles\maintenance_lt\home\_agent\maintenance\merge_log.jsonl")
if merge_log.exists():
    entries = [json.loads(l) for l in merge_log.read_text().splitlines() if l.strip()]
    # Find entries not yet announced (no 'announced' field)
    new_merges = [e for e in entries if not e.get("announced")]
    if new_merges:
        for entry in new_merges:
            merge_block = f"🛠️ **Shipwright merged PR #{entry['pr']}** — {entry['title']} ({entry['fixes']} fixes)\n"
            # append to fleet message
            entry["announced"] = True
        merge_log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
```

The merge block appears in `#fleet` (Discord), `#fleet` (Buzz), and Telegram Fleet Command group — all three broadcast targets. Michael gets tagged per normal fleet-checkin tagging rules.

---

### Phase 5 — Kanban + Marshal Setup

**Task 5.1: Register Shipwright Wing with Marshal**

Marshal currently owns the carrier Kanban board. No changes to Marshal's config needed — Marshal already monitors ALL carrier board tasks regardless of wing. The new bot_ids appear as assignees and Marshal's board view shows them automatically.

Verify Marshal can see the new bots:
```bash
hermes kanban --board carrier list --all
```
If Shipwright tasks don't appear: check that the carrier board DB is the one at `kanban/boards/carrier/kanban.db` (not the default `kanban.db`).

**Task 5.2: Verify Yeoman knows about new bots**

Yeoman only needs to receive AIPass messages from Caulker and Surveyor and execute `gh pr create` / `gh pr merge`. No changes to Yeoman's config needed. The AIPass job packet format must match Yeoman's existing intake format (see `templates/job_packet.md`).

---

### Phase 6 — Cron Configuration

**Task 6.1: Create maintenance cron (STAGED — do not activate until fully tested)**

```python
# Run manually first:
hermes cronjob create \
  --name "shipwright-maintenance" \
  --schedule "0 2,10,18 * * *" \
  --profile maintenance_lt \
  --monitor-script "maintenance_preflight.py" \
  --prompt "$(cat carrier_hermes/prompts/maintenance_lt.md)" \
  --enabled-toolsets "kanban,file,session_search,memory,aipass" \
  --no-live  # DO NOT go live until Phase 7 smoke test passes
```

The `monitor_script` is `maintenance_preflight.py` (just the filename — must be copied to `~/.hermes/scripts/` first per cron pitfall). When preflight exits with stable "SUPPRESSED" output, the hash doesn't change and the agent never fires = zero tokens on skip.

**Task 6.2: Smoke-test manually before scheduling**
1. Run `maintenance_preflight.py` manually → confirm all-green
2. Manually trigger: `hermes cronjob run <job_id>` with `--prompt "dry-run: just run preflight and report status, do not dispatch any bots"`
3. Inspect Bosun's session in `state.db` — verify model used was anthropic OAuth ($0 actual)
4. Only after successful dry-run: remove `--no-live` and set cron to active

---

### Phase 7 — Integration Smoke Test

**End-to-end test sequence (run once manually before enabling cron):**

1. Manually dispatch Diver with a known small target: `--limit-scope scripts/maintenance_preflight.py`
2. Verify `audit_report_<date>.md` written to Diver's home
3. Hand to Rigger manually via AIPass with the report path
4. Verify `fix_plan_<date>.md` written
5. Hand to Caulker manually with a single LOW-risk fix only (e.g., a ruff lint fix)
6. Verify: new branch created, one commit, Yeoman AIPass sent
7. Let Yeoman open draft PR (not real PR — use `--draft` flag first time)
8. Hand to Surveyor with draft PR number
9. Verify review written; verify Yeoman AIPass for merge sent
10. Do NOT merge the draft — just verify the message format
11. Check `merge_log.jsonl` path exists and format is correct
12. Check `fleet_checkin.py` picks up the test entry
13. Run billing_guard.py on all 5 new profiles — expect PASS

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Local LLM unavailable at dispatch time | Preflight hard-gates on Ollama health; cron has 3× daily retries |
| 2 | Caulker sweeps in worktree files from other Kanban tasks | Explicit `git add <file>` per fix (never `git add -A`); Surveyor review catches this |
| 3 | Rigger calls OpenRouter frontier model | Billing guard + fallback chain explicitly terminates at `gemini-flash-lite`; OR workspace guardrail blocks frontier models |
| 4 | Pipeline stalls between Caulker and Surveyor | Kanban task_links enforce ordering; Bosun timeout after 24h with DISPATCH_LOCK |
| 5 | Diver report is too large for context | Diver paginates the report into sections; Rigger reads sections via `read_file` with offset |
| 6 | Caulker breaks something with its fix | Each fix is an atomic commit; Surveyor review gates; PR CI catches regressions before merge |
| 7 | Two maintenance runs overlap | Preflight checks `state.db` for in-progress maintenance tasks; DISPATCH_LOCK file written at start |
| 8 | Discord Developer Portal MFA blocks bot creation | Human gate clearly marked — no automation can bypass this |

---

## Files To Create (Summary)

| File | Created by | Notes |
|---|---|---|
| `bots/BOT_MATRIX.md` | Agent (patch) | Add Shipwright Wing section |
| `profiles/maintenance_lt/config.yaml` | Agent | Bosun config |
| `profiles/code_auditor/config.yaml` | Agent | Diver config |
| `profiles/repair_planner/config.yaml` | Agent | Rigger config |
| `profiles/patch_writer/config.yaml` | Agent | Caulker config |
| `profiles/pr_reviewer/config.yaml` | Agent | Surveyor config |
| `profiles/*/. env` | Agent (doppler pull) | Per-bot env (Shipwright token, doppler keys) |
| `prompts/maintenance_lt.md` | Agent | Bosun system prompt |
| `prompts/code_auditor.md` | Agent | Diver system prompt |
| `prompts/repair_planner.md` | Agent | Rigger system prompt |
| `prompts/patch_writer.md` | Agent | Caulker system prompt |
| `prompts/pr_reviewer.md` | Agent | Surveyor system prompt |
| `scripts/maintenance_preflight.py` | Agent | Pre-flight availability check |
| `scripts/maintenance_dispatch.py` | Agent | Kanban pipeline dispatcher |
| `scripts/maintenance_merge_hook.py` | Agent | Merge log writer |
| `scripts/fleet_checkin.py` | Agent (patch) | Add merge reporting section |
| `.hermes/plans/2026-08-26_shipwright-wing.md` | Agent | This file |

---

## Verification Checklist (before go-live)

- [ ] Discord Shipwright app created, token in Doppler, bot in server, `#maintenance` channel exists
- [ ] `ollama pull qwen2.5:7b-instruct-q4_K_M` confirmed present on `:11434`
- [ ] All 5 profiles created and recognized by `hermes profile list`
- [ ] `billing_guard.py` PASS on all 5 new profiles
- [ ] `maintenance_preflight.py` exits 0 in favorable conditions, exits 1 when suppressed
- [ ] End-to-end smoke test (Phase 7) completed with draft PR — no real merge
- [ ] `fleet_checkin.py` merge reporting tested (manually write a test entry to `merge_log.jsonl`, verify broadcast)
- [ ] Cron created but **NOT live** until smoke test passes
- [ ] Michael reviews and approves cron schedule before activation
- [ ] Marshal confirmed seeing Shipwright tasks in `hermes kanban --board carrier list`

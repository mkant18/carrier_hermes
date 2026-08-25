# Approved Skills & MCP Policy — Carrier Hermes

**Status:** FROZEN — Phase B baseline (2026-08-25)
**Owner:** Wrench (coding_lt) — gates all install decisions
**Executor:** Mate (firstmate) — drafts lists and runs smoke tests only under Wrench packet
**Scope:** All 18-bot fleet; all skill installs, skill updates, and MCP server additions

---

## 1. Governing rules (non-negotiable)

1. **No mass install.** No one on the fleet runs `hermes skills install` fleet-wide
   or bulk-installs from any catalog without a Wrench-issued verify packet containing
   the exact list of skill names, target profiles, and expected behavior.

2. **No auto-curators touching pinned skills.** Tools that automatically discover,
   update, or remove skills (SkillClaw in eval mode, any "auto-update" feature) must
   not run against pinned skills. Pinned skills are protected; evaluation tools may
   only read them.

3. **Catalog verification is HEAD-only.** When vetting a skill from any external
   catalog (awesome-hermes-skills, awesome-hermes-agent, optional-skills), Mate reads
   the HEAD commit of the specific SKILL.md only — no cloning entire repos, no running
   install scripts unread.

4. **P0 installs block the fleet; P1 installs block the wing.** Nothing below P1 goes
   to any production profile during Phase B. P2+ is Backlog — propose to Helm first.

5. **Smoke only, worktree-isolated.** Any new skill being evaluated gets a scratch or
   worktree run in an isolated profile — not a production bot home. Pass = one clean
   invocation of the skill's primary action with no side-effects on production memory,
   files, or kanban.

6. **Secrets do not transit skills.** No skill receives API keys, tokens, or
   credentials as SKILL.md literals. Secrets route: Helm → HANDSHAKE_GRANT → LockBox
   → bot at dispatch. Skills reference env-var names only (e.g. `$OPENROUTER_API_KEY`).

7. **Chart (hermes_ai_explorer) install gate.** Chart may propose skill additions from
   Recon missions. Proposals go to `_agent/explorer/proposals-*.md`. Chart does NOT
   install. Wrench reviews, issues a verify packet if approved, Mate installs.

---

## 2. Approved sources (P0/P1 installs only)

### 2.1 Allowed catalogs

| Catalog | Use | Constraint |
|---|---|---|
| **Hermes official optional skills** (built-in `hermes skills list --available`) | Primary source | HEAD read; install only named skills |
| **ZeroPointRepo/awesome-hermes-skills** | Vetted community list | HEAD-only; Wrench approval per entry |
| **0xNyk/awesome-hermes-agent** | Supplemental community list | HEAD-only; Wrench approval per entry |
| **SkillClaw** | Evaluation and search only | Never install directly; eval in scratch profile |
| **carrier_hermes/skills/** (this repo) | Fleet-authored skills | Install as documented in each SKILL.md |

### 2.2 Denied sources

- **Any broad skill marketplace or aggregator** not listed above (e.g. npm-style
  registries, community Discord drops, unreviewed GitHub forks)
- **Auto-curators** that touch pinned skills without a Wrench packet
- **Unfiltered catalog outputs** (i.e., install everything returned by a search query)
- **Skills with `no_agent=true` scripts that make outbound network calls** without
  explicit Helm review

---

## 3. P0 / P1 approved install list

### P0 — Install this pass (Phase B), blocking

These skills unlock core fleet capability that Phase B bots need on day one.

| Skill name | Target profiles | Source | Rationale |
|---|---|---|---|
| `carrier-roster` | `chief_of_staff` | `carrier_hermes/skills/carrier-roster/` | Helm needs fleet roster on every dispatch |
| `signal-lamp-discord` | `coding_lt`, `firstmate`, `git_yeoman` | `carrier_hermes/skills/carrier/signal-lamp-discord/` | Coding wing Discord #fleet posting |
| `boatswain-new-bot` | `coding_lt`, `chief_of_staff` | `carrier_hermes/skills/carrier/boatswain-new-bot/` | New bot provisioning procedure |
| `google-workspace` | `email_reader`, `calendar_manager` | Hermes official optional skills | Gmail + Calendar are core ops tools |

### P1 — Install this pass (Phase B), non-blocking

These unlock secondary capabilities. Mate installs after P0 is green.

| Skill name | Target profiles | Source | Rationale |
|---|---|---|---|
| `github-pr-workflow` | `firstmate` | Hermes official optional skills | Mate's primary code-review loop |
| `github-issue-to-pr` | `firstmate` | Hermes official optional skills | Issue-to-PR sortie standard path |
| `github-code-review` | `coding_lt` | Hermes official optional skills | Wrench review gate for Mate PRs |
| `obsidian` | `vault_librarian`, `obsidian_archivist` | Hermes official optional skills | Vault operations backbone |
| `sdlc-review` | `coding_lt` | Hermes official optional skills | Kanban handoff review protocol |
| `systematic-debugging` | `firstmate` | Hermes official optional skills | Mate debug sorties |

---

## 4. P2+ backlog (propose before install)

The following have been identified as potentially useful but are NOT approved for Phase B
installation. Any fleet member may add a proposal to the backlog; Helm approves
promotion to P1/P0.

| Skill | Interest from | Notes |
|---|---|---|
| `weights-and-biases` | Chart proposals | Only if ML experiment tracking needed |
| `llama-cpp` | Chart proposals | Only if local model inference is added |
| `youtube-content` | Probe/Chart | Research pipeline enhancement |
| `email-inbox-triage` | Helm | Held pending Inbox/Quill Phase B eval |
| `airtable` | Tasker | No confirmed Airtable usage yet |
| SkillClaw-evaluated skills | Chart | Per-proposal basis after SkillClaw eval run |

---

## 5. MCP include / exclude (Phase B baseline)

MCP server grants are per-bot and are governed by `bots/BOT_MATRIX.md`. This section
states the policy; MCP-01 (a sibling ECO task) produces the per-bot filter lists.

### 5.1 MCP grant rules

- **Default is deny.** No bot gets an MCP server unless it appears in that bot's
  BOT_MATRIX row under "MCP tools."
- **Read-only first.** MCP servers that have both read and write operations: grant
  read; hold write until the bot's write root is confirmed.
- **No MCP server for secrets.** MCP servers that return raw credentials (e.g. Doppler
  MCP) route through LockBox only. No other bot gets a Doppler MCP grant.
- **Obsidian Second Brain write exclusion.** `obsidian_save_note`, `obsidian_capture`,
  `obsidian_update_note` are excluded from all bots except `vault_librarian` and
  `obsidian_archivist`.

### 5.2 Currently allowed MCP servers (fleet-wide snapshot)

| Server | Allowed profiles | Notes |
|---|---|---|
| `hugging_face` | `firstmate`, `hermes_ai_explorer` | Research and model discovery |
| `todoist` (template import/export excluded) | `todoist_manager` | Task management ops |
| `obsidian-second-brain` (write ops excluded for non-vault bots) | `vault_librarian`, `obsidian_archivist`, `chief_of_staff` (read only) | Vault access |
| `vercel` | `firstmate` | Deploy ops |

### 5.3 Denied MCP servers (fleet-wide)

- Dropbox MCP (disabled — no confirmed use case)
- Any MCP server not listed in BOT_MATRIX.md
- Doppler MCP to any bot except LockBox's own toolchain

---

## 6. Install procedure (Mate follows this)

1. Wrench issues a verify packet (Kanban card or AIPass message) naming:
   - Exact skill name(s)
   - Target profile(s)
   - Source catalog + HEAD commit (Mate verifies before installing)
   - Smoke test: one command that validates the install
2. Mate reads the SKILL.md at HEAD before installing.
3. Mate installs to the named profile(s) only: `hermes -p <profile> skills install <name>`
4. Mate runs the smoke test in an isolated scratch run.
5. Mate returns a result packet: `status`, `skill_name`, `profile`, `commit_sha`,
   `smoke_result`, `blockers[]`.
6. Wrench reviews and marks done or re-dispatches.

---

## 7. Review cadence

- **Weekly:** Wrench reviews P2+ backlog for promotions.
- **Per-epic:** SKL policy is a living doc — any ECO pass may propose amendments.
  Amendments require Helm approval before merge.
- **On denial:** If a proposed skill is denied, Wrench comments on the Kanban card
  with `DENY: <reason>` and the backlog entry is archived.

---

*Authored by Wrench (coding_lt) — SKL-01 / ECO-20260825 / Phase B baseline.*
*Mate implements install lists; Chart may propose; no one auto-installs.*

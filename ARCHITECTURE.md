# Architecture: Carrier Hermes

> **Phase A freeze (2026-08-25):** identities, channels, and cost pins live in  
> [`docs/INTER_AGENT_PROTOCOL.md`](docs/INTER_AGENT_PROTOCOL.md), [`bots/README.md`](bots/README.md), [`COST_MODEL.md`](COST_MODEL.md).  
> This page still contains **stale** 8-bot / free-rotate diagrams — do not implement from the tier diagram below.  
> 12 bots; Vigil ≠ Sentry; Ledger fleet-wide; Chronos ≠ Tasker; Librarian ≠ Clerk; hybrid AIPass; no `:free` specialists.

## Design philosophy

The original Carrier Ops plan required 8+ separate open-source tools, Docker containers, and a WSL2 machine. This implementation achieves the same fleet using Hermes Agent as the single runtime on macOS, with three key principles:

1. **Subscription-first, pay-per-token only for rote work.** The "smart" tier (chief-of-staff class agents) draws from OAuth subscriptions (SuperGrok, Claude Max) with zero marginal token cost. Cheap OpenRouter models handle bulk/rote work. Per-token spending is minimised.

2. **One runtime, not five.** Hermes natively provides gateway, scheduling, parallel dispatch, memory, and multi-provider routing. No OpenClaw, Podiom, or harness server required.

3. **Governance rules are structural, not advisory.** Tool scoping, vault write restrictions, approval cards, and idempotency are enforced at the Hermes profile and toolset level — not documented and hoped for.

---

## Model tier resolution

```
Inbound request
       │
       ▼
Chief of Staff (grok-4.5 via SuperGrok OAuth, OR claude-opus-4-8/claude-sonnet-4-6 via Claude Max OAuth)
  ├── Simple / rote → delegate_task to specialist profile
  │     └── Specialist uses OpenRouter rotated pool:
  │           deepseek/deepseek-chat-v3-0324  ($0.27/M)
  │           google/gemma-3n-e4b-it:free     ($0.00)
  │           meta-llama/llama-4-scout:free   ($0.00)
  │           microsoft/phi-4-reasoning:free  ($0.00)
  │           [rotated via credential pool / model aliases]
  │
  ├── Hard / multi-perspective → /moa (frontier MoA preset)
  │     └── References: 2-3 cheap OpenRouter models analyse
  │         Aggregator: grok-4.5 (SuperGrok OAuth) synthesises
  │         Auto-reverts to main model after one turn
  │
  └── Parallel work → delegate_task (multiple child agents)
        └── Each child pinned to specialist tier
```

---

## Governance rules (from carrier_ops Section 3, enforced here)

| Rule | Carrier Ops mechanism | Hermes mechanism |
|---|---|---|
| No sends | Email Drafter tool scoping at harness | Email Drafter profile has no send tools; only `file` + `web` |
| No vault edits outside `_agent/` | `--allowedTools` at OpenMausBot | File tool restricted by SOUL.md + approval mode |
| Tool scope per agent | Harness permission broker | Per-profile toolset enablement |
| Idempotency | State file + harness | Each agent writes `_agent/<domain>/state.json`, checks before acting |
| Dual audit | buzz (Nostr) + maka | Hermes `state.db` + Discord webhook hook on every tool call |
| Watcher has kill authority | Harness `/pause` endpoint | Watcher cron posts to Discord alert; manual or automated `hermes pause` |
| Prompt injection defence | Email Reader sandboxed | Email Reader profile has zero outbound tools; cannot call Todoist/calendar |

---

## Agent profiles

### Command tier

**chief_of_staff**
- Model: `xai-oauth/grok-4.5` (primary, SuperGrok sub) | fallback: `anthropic/claude-opus-4-8` or `claude-sonnet-4-6` (Claude Max sub)
- Tools: `delegation`, `cronjob`, `discord`, `memory`, `session_search`, `todo`
- Vault: read-only (no file write tools)
- Role: receives all inbound from Discord/Telegram. Classifies complexity. Routes to specialists or escalates to frontier MoA. Enforces constitution.

**subscription_watcher**
- Model: `openrouter/google/gemma-3n-e4b-it:free` (cheapest available, free tier)
- Tools: `session_search`, `memory` (read-only), `discord` (alert-only)
- Cron: every 5 minutes
- Role: monitors session logs for stalls, rate limit proximity, redundant work. Alerts Discord. No write capability except alert posts.

### Specialist tier (all use OpenRouter rotated pool)

**email_reader**
- Model: `specialist` alias → OpenRouter rotated pool
- Tools: `file` (write `_agent/email/` only), web extract for Spark CLI substitute
- No: Todoist, calendar, send capability of any kind

**email_drafter**
- Model: `chief-of-staff` alias (Sonnet 4.6 via Claude Max OAuth — drafting quality)
- Tools: `file` (read `_agent/email/`, write `_agent/drafts/`), `memory`, `skills` (my-writing-style)
- Approval: every draft posts to Discord `#drafts`; no send capability

**calendar_manager**
- Model: `specialist` alias → OpenRouter rotated pool
- Tools: `todoist` MCP, `file` (write `_agent/calendar/`)
- No: email content access

**vault_librarian**
- Model: `chief-of-staff` alias (Sonnet 4.6 via Claude Max OAuth)
- Tools: `obsidian` skill, OB1 MCP (when available), `file` (read all, write `_agent/` only)
- No: edit/move/delete existing notes

**research_agent**
- Model: `chief-of-staff` alias (Sonnet 4.6 via Claude Max OAuth)
- Tools: `web`, `browser`, `file` (write `_agent/research/`)
- Note: read-only browser use

**hermes_ai_explorer** (Chart / Recon Wing lead)
- Model: quality — `anthropic/claude-sonnet-4-6` via Claude Max OAuth
- Tools: `web` (selective — prefer Sonar digest), `session_search`, `memory`, `file` (write `_agent/explorer/` only), OSB MCP read tools, optional `discord` (short fleet tips only)
- Cron: 2–3× per week (not high-frequency); reads Sonar digests before web scraping
- Role: intelligence synthesis + fleet/AI optimization proposals. Reads `_agent/signal_watch/` from Sonar. Never silent reconfig.
- Boundary: not Sonar (passive signals), not Probe (general research), not Helm

**passive_watch** (Sonar / Recon Wing passive feeder)
- Model: heartbeat `no_agent` bash ($0 LLM); LLM pass `specialist` DeepSeek only on diff detected
- Tools: `terminal` narrow (curl/hash fixed URLs), `file` (`_agent/signal_watch/`), `discord` `#fleet` HIGH signals only
- Cron: daily `no_agent` heartbeat; LLM digest only on diff; forced weekly pass
- Role: passive ecosystem watcher — OpenRouter pricing, Hermes changelog, one AI feed. Writes digest for Chart. Near-zero cost on quiet days.
- Boundary: not Chart (synthesis), not Probe (on-demand research), not Vigil (session stalls)

### Knowledge layer

**Obsidian Second Brain (OSB)** attached to Hermes via:
1. Native skills under `~/.hermes/skills/obsidian-second-brain/`
2. MCP stdio server `obsidian-second-brain` (read/search/health; Inbox writes excluded at Trust Level 0)
3. `OBSIDIAN_VAULT_PATH` → `/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN`
4. Primary consumer: `vault_librarian`; secondary: `hermes_ai_explorer` (Chart), `email_drafter` (contacts read)

See `integrations/obsidian-second-brain.md`.

---

## MoA frontier preset

Name: `frontier`

- Reference 1: `openrouter/deepseek/deepseek-chat-v3-0324` — analytical pass
- Reference 2: `openrouter/meta-llama/llama-4-maverick:free` — alternative framing
- Aggregator: `xai-oauth/grok-4.5` — synthesises references, emits final response

Invocation: `/moa <hard prompt>` — one-shot, auto-reverts.
Persistent switch: `/model frontier --provider moa` for a whole session.

---

## Subscription rate limit awareness

Claude Max (Tier 4, Max 20x):
- Sonnet 4.x: 4,000 RPM / 2M ITPM / 400K OTPM
- Opus 4.x: 4,000 RPM / 10M ITPM / 800K OTPM
- Haiku 4.5: 4,000 RPM / 4M ITPM / 800K OTPM

SuperGrok (xAI):
- Limits vary; Subscription Watcher monitors response headers and flags at 70% / blocks dispatches at 90%.

OpenRouter (pay-per-token):
- No hard rate limits at normal usage; budget cap set via OpenRouter dashboard.

Watcher threshold table (from carrier_ops AGENTS.md):

| Signal | Threshold | Action |
|---|---|---|
| RPM / ITPM / OTPM | >70% tier limit | Alert Discord |
| RPM / ITPM / OTPM | >90% tier limit | Block new dispatches |
| No output events | 10+ min | Flag stalled |
| Confirmed stall | 15 min | Auto-pause, notify Discord |
| Input tokens | >50K on one request | Flag context bloat |
| Two agents on overlapping tasks | any | Flag redundancy |

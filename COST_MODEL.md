# Cost Model — Carrier Hermes

Subscription-first. **No automatic API/per-token fallback.** OpenRouter remains human-gated emergency overflow only; never free-rotate live email / calendar / Todoist.

---

## Local LLM Policy (pending integration — see Kanban task `local-llm-routing`)

Once a local LLM is available on the host, apply this routing hierarchy:

### Decision-making tier — NEVER local LLM
These bots stay on subscription OAuth regardless:
- **Helm** (chief_of_staff): `grok-4.5/xai-oauth` primary
- **Marshal + all LTs** (Wrench, Deck, Stacks, Chart/Bosun): `grok-4.5/xai-oauth` primary → `openai-codex/gpt-5.6-sol` → `anthropic/claude-sonnet-4-6`

Rationale: routing, coordination, and judgment calls need frontier-quality reasoning. Latency and reliability of local LLM are not acceptable for dispatch decisions.

### Worker/watcher tier — local LLM primary, OAuth fallback on tool calls
All remaining bots (Vigil, Ledger, Sonar, Inbox, Chronos, Tasker, Yeoman, Mate, Probe, Quill, Purse, Librarian, Clerk, LockBox) use:
```
local-llm (primary — $0, zero quota)
  → grok-4.5/xai-oauth
  → gpt-5.6-luna/openai-codex (cheap OpenAI OAuth local substitute)
  → claude-haiku-4-5/anthropic
```
**NOT** OpenRouter for the fallback — use subscription OAuth so fallback is still $0 marginal.

LockBox specifically: local LLM for routine Doppler health checks; OAuth fallback for tool calls; **never DeepSeek/PRC even on local** (keep the non-PRC policy at inference time).

### Implementation note (for the wiring session)
Set each affected bot's `config.yaml` provider chain to:
```yaml
provider: local          # ollama / llama.cpp / whatever the integration uses
model: <local-model>
fallback:
  - provider: anthropic  # OAuth subscription
    model: claude-sonnet-5-20251001
    condition: tool_calls  # only when tool calls needed
```
Script: `scripts/apply_local_llm_routing.py` (to be written by that session).
Verify with `billing_guard.py` after — expected PASS (local = $0, fallback = OAuth $0).

---

## Rules

1. Subscription OAuth first (xAI SuperGrok, OpenAI ChatGPT/Codex OAuth, Anthropic Claude Max).
2. OpenRouter **paid** only with explicit human authorization under the emergency policy; never a standing fallback.
3. OpenRouter `:free` only for: aux slots, MoA **references**, throwaway scrapes. Never sole decider on live ops.
4. Watcher heartbeats must be `no_agent` scripts (zero tokens).
5. Never rotate free models on `email_reader`, `calendar_manager`, or `todoist_manager`.
6. Coding defaults to Mate on subscription tiers.
7. Helm classification stays on SuperGrok (do not burn Claude on “what is this request?”).
8. **HARD BILLING LOCK (PERIOD, FULL STOP):** Anthropic/Claude, xAI/Grok, and OpenAI/GPT/Codex are **OAuth/subscription only**.
   - Allowed providers: `anthropic`, `xai-oauth`, `openai-codex`.
   - **OpenRouter / metered aggregators are ALLOWLIST-ONLY** (DeepSeek flash/chat, Gemini Flash/Lite, gpt-oss). Default deny.
   - **Absolute deny** on metered transports for any model slug matching Claude/Anthropic/Sonnet/Opus/Haiku, Grok/x-ai, or OpenAI GPT-4/5/o-series — even if someone edits the allowlist.
   - **Forbidden:** `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `OPENAI_API_KEY`, bare provider `xai`/`openai`/`openai-api`, `base_url` openrouter.ai + Claude/Grok/OpenAI frontier.
   - Enforced by `scripts/or_billing_policy.py` + `scripts/billing_guard.py` + optional `scripts/sync_or_billing_guardrail.py` (OpenRouter workspace allowlist).

---

## Fleet default chain (all profiles)

Every decision bot uses the subscription-only chain; local workers keep local primary and use subscription-only fallbacks.

```text
grok-4.5 (xai-oauth, SuperGrok $0)
  → gpt-5.6-sol (openai-codex, ChatGPT/Codex OAuth $0 marginal)
    → claude-sonnet-4-6 (anthropic, Claude Max $0 marginal)
```

| Tier | Who | Subscription fallback |
|---|---|---|
| `decision` | Helm + Marshal + Lieutenants + planners/reviewers | `openai-codex/gpt-5.6-sol` → `anthropic/claude-sonnet-4-6` (Opus tail for Opus-tier Shipwright bots) |
| `worker-local` | Watchers, readers, drafters, Mate, Probe, Yeoman, LockBox, Shipwright workers | `xai-oauth/grok-4.5` → `openai-codex/gpt-5.6-luna` → `anthropic/claude-haiku-4-5` |

OpenRouter allowlisted models are no longer automatic fallback tails; they are reserved for the existing explicit human-gated OR emergency policy.

Source of truth: `scripts/apply_bot_matrix.sh` (`chain <bot> <tier>`). Editing a
live `~/.hermes/profiles/*/config.yaml` by hand is reverted on the next run.

---

## Work class → pin

| Work class | Billing | Model pin | Never |
|---|---|---|---|
| Helm classify/dispatch | SuperGrok $0 marginal | `xai-oauth/grok-4.5` (`smart`) | Opus/Sonnet for routing |
| Drafts / vault Q&A / research / Clerk judgment | Claude Max $0 marginal | `anthropic/claude-sonnet-5` (`quality`) | Free small models for voice |
| Complex multi-perspective thinking | Claude Max / SuperGrok (or Gemini Flash **only when subs run out**) | `frontier-quality` / `smart` | Free small models |
| Email triage, calendar, Todoist | OpenRouter **paid** stable | `openrouter/deepseek/deepseek-v4-flash-0731` (`specialist` / `rote` / `cheap`) | `:free` rotate |
| Aux (titles, compression) | Cheap paid | DeepSeek V4 Flash | Subscription main model |
| Watcher heartbeats | **$0 LLM** | bash `no_agent` | Gemma every 5m |
| LockBox judgment / redeem | OpenRouter **paid non-China** | `openai/gpt-oss-120b`; then `google/gemini-2.5-flash-lite` | DeepSeek, Moonshot, Qwen CN, PRC-primary, `:free` |
| LockBox high-blast deny | Claude Max rare | short `quality` Sonnet | Cheap PRC models |
| LockBox Doppler health | **$0 LLM** | bash `no_agent` | LLM heartbeat |
| Coding implementer/reviewer | Claude Max (or Grok if limited) | `quality` | Free models writing prod code |
| Coding janitor/docs | Paid DeepSeek **or** Max | `specialist` | Rotating free as merge gate |

---

## Subscription Exhaustion & Fallback Policy

1. **Subscription Tiers First ($0 marginal):** xAI SuperGrok (Grok 4.5) then Claude Max (Sonnet 5). Both tiers are exhausted before any paid token is spent.
2. **Rote / High-Volume Tasks:** paid tail is cheap DeepSeek V4 Flash (`openrouter/deepseek/deepseek-v4-flash-0731`), ~9x cheaper per token than the retired V3 pin.
3. **Gemini Flash Role:** Gemini remains a **reserve overflow** model, last in every chain. It is **never** a default or routine specialist. Once complex synthesis completes, downstream rote work returns to the cheap tail.

---

## Aliases (Phase B applies)

```text
chief-of-staff, smart          → xai-oauth/grok-4.5
quality                        → openai-codex/gpt-5.6-terra
frontier-quality               → openai-codex/gpt-5.6-sol
openai-cheap                   → openai-codex/gpt-5.6-luna
specialist, rote, cheap        → local primary; if remote needed use openai-cheap before Anthropic
specialist-coding              → openai-codex/gpt-5.6-terra
watcher-summary                → no_agent/local first; OR only under explicit emergency authorization
gemini-flash, fallback-flash   → openrouter/google/gemini-2.5-flash-lite (emergency OR only)
lockbox, security-cheap        → openai-codex/gpt-5.6-luna before Anthropic; OR gpt-oss only under explicit emergency authorization
lockbox-fallback               → openrouter/google/gemini-2.5-flash-lite
```

**Remove** any `:free` from specialist/rote/cheap.

**LockBox must not reuse** `specialist`/`rote`/`cheap` while those point at DeepSeek.

**Fallback (human-facing quality path):** Grok 4.5 → Sonnet 5 → paid tail. Never free as last resort for Helm. **Exception:** LockBox tail is `gpt-oss-120b` / `gemini-2.5-flash-lite` only (never DeepSeek).

**MoA frontier:** ref1 paid DeepSeek (or one free if budget-tight); ref2 free maverick/scout as reference only; aggregator Grok 4.5.

---

## Budget ballpark (OpenRouter, excl. subs)

Heavy mail/calendar/Todoist month on DeepSeek V3-class: **~$50–100**.  
Qwen Flash maybe **~$20–45** after shadow A/B — not default.  
Kimi volume lane **$200+** — avoid.

Ledger daily/monthly soft/hard caps live in `_agent/api_watcher/spend-state.json` (defaults set at Phase B script install).

---

## Anti-patterns (reject in review)

- `specialist` alias → `:free` pool
- Watcher cron without `no_agent`
- Helm on Opus for classification
- Probe/Librarian/Clerk final reports on free Llama
- LLM every 5m for Vigil
- Chronos pinned free “because calendar is easy”
- Using bot-chat (P4) when AIPass (P3) or Kanban (P1) suffices
- **DeepSeek (or any PRC-primary / `:free` pool) on LockBox**
- LockBox 5-minute LLM heartbeat
- Secret values in result packets / AIPass / Discord

---

## Ledger API (frozen)

Heartbeat script:

```text
GET https://openrouter.ai/api/v1/key
Authorization: Bearer $OPENROUTER_API_KEY
```

Use `usage_daily`, `usage_monthly`, `limit_remaining`.  
Optional account credits: `GET /api/v1/credits` only if `OPENROUTER_MANAGEMENT_KEY` is set.  
Do not require a management key for the 10–15m tick.

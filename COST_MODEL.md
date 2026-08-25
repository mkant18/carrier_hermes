# Cost Model — Carrier Hermes

Subscription-first. Pay-per-token only for high-volume structured ops. **Never** free-rotate live email / calendar / Todoist.

---

## Rules

1. Subscription OAuth first (xAI SuperGrok, Anthropic Claude Max).
2. OpenRouter **paid** only for high-volume structured ops (Inbox, Chronos, Tasker) and optional watcher narratives.
3. OpenRouter `:free` only for: aux slots, MoA **references**, throwaway scrapes. Never sole decider on live ops.
4. Watcher heartbeats must be `no_agent` scripts (zero tokens).
5. Never rotate free models on `email_reader`, `calendar_manager`, or `todoist_manager`.
6. Coding defaults to Mate on subscription tiers.
7. Helm classification stays on SuperGrok (do not burn Claude on “what is this request?”).

---

## Fleet default chain (all 18 bots)

Every bot boots on the same chain; only the **paid tail** differs.

```text
grok-4.5 (xai-oauth, SuperGrok $0)
  → claude-sonnet-5 (anthropic, Claude Max $0)
    → <paid tail — LAST RESORT ONLY>
```

| Tier | Who | Paid tail | Blended $/M |
|---|---|---|---|
| `command` | Helm + Lieutenants (Wrench, Deck, Stacks) | `deepseek/deepseek-chat-v3-0324` → `google/gemini-3.7-flash` | 0.44 → 0.75 |
| `cheap` | All other subagents (watchers, readers, drafters, Mate) | `deepseek/deepseek-v4-flash-0731` → `google/gemini-2.5-flash-lite` | **0.05 → 0.18** |
| `nocn` | LockBox only (never DeepSeek/PRC) | `openai/gpt-oss-120b` → `google/gemini-2.5-flash-lite` | 0.07 → 0.18 |

Subagent tail is **~9x cheaper** than the old DeepSeek V3 pin (0.4375 → 0.05 blended).
All tail models are **tool-calling verified** — a worker that cannot emit a tool
call exits rc=0 without `kanban_complete`, and the board scores that a crash.

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
quality                        → anthropic/claude-sonnet-5
frontier-quality               → anthropic/claude-opus-4-8
specialist, rote, cheap        → openrouter/deepseek/deepseek-v4-flash-0731
specialist-coding              → anthropic/claude-sonnet-5
watcher-summary                → openrouter/deepseek/deepseek-v4-flash-0731
gemini-flash, fallback-flash   → openrouter/google/gemini-2.5-flash-lite
lockbox, security-cheap        → openrouter/openai/gpt-oss-120b
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

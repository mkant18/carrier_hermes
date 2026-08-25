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

## Work class → pin

| Work class | Billing | Model pin | Never |
|---|---|---|---|
| Helm classify/dispatch | SuperGrok $0 marginal | `xai-oauth/grok-4.5` (`smart`) | Opus/Sonnet for routing |
| Drafts / vault Q&A / research / Clerk judgment | Claude Max $0 marginal | `anthropic/claude-sonnet-4-6` (`quality`) | Free small models for voice |
| Hard multi-view | SuperGrok aggregator + cheap refs | MoA `frontier` | Opus on every research ask |
| Email triage, calendar, Todoist | OpenRouter **paid** stable | `openrouter/deepseek/deepseek-chat-v3-0324` (`specialist` / `rote` / `cheap`) | `:free` rotate |
| Aux (titles, compression) | Free or cheapest paid | one pinned aux + DeepSeek fallback | Subscription main model |
| Vigil / Ledger heartbeat | **$0 LLM** | bash `no_agent` | Gemma every 5m |
| Coding implementer/reviewer | Claude Max (or Grok if limited) | `quality` | Free models writing prod code |
| Coding janitor/docs | Paid DeepSeek **or** Max | `specialist` | Rotating free as merge gate |
| MoA references | Free/cheap OK | 2 refs max | Free ref as sole decider |

---

## Aliases (Phase B applies)

```text
chief-of-staff, smart          → xai-oauth/grok-4.5
quality                        → anthropic/claude-sonnet-4-6
frontier-quality               → anthropic/claude-opus-4-8
specialist, rote, cheap        → openrouter/deepseek/deepseek-chat-v3-0324
specialist-coding              → anthropic/claude-sonnet-4-6
watcher-summary                → openrouter/deepseek/deepseek-chat-v3-0324
```

**Remove** any `:free` from specialist/rote/cheap.

**Fallback (human-facing quality path):** Sonnet Max → paid DeepSeek. Never free as last resort for Helm.

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

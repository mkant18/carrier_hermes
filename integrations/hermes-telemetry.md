# Integration — hermes-telemetry (cost microscope)

**Status:** **ADAPT / DEFER install** — not production-enabled this pass  
**Phase:** ECO TEL-01 (2026-08-25)  
**Candidate:** `nujovich/hermes-telemetry` v0.8.0 (`be844fe`)  
**Eval artifact:** `_agent/coding/cost/EVAL.md`  
**Sibling REJECT:** `42-evey/hermes-plugins` `evey-cost-guard` (soft Langfuse only)

## Decision

| Item | Verdict |
|---|---|
| hermes-telemetry | ADAPT design; **defer fleet install** until adapter + multi-home strategy approved |
| evey-cost-guard | **REJECT** — do not install |
| Fleet hard stop | Still **Ledger** `SPEND_HALT` + **Vigil** `DISPATCH_LOCK` + Helm `dispatch_preflight.sh` |

## Why not install yet

1. Hermes hooks cannot abort the next LLM call (`pre_llm_call` soft only). Hard plugin brake is **tool-gate** only.
2. No native write to `~/.hermes/carrier/SPEND_HALT`.
3. Dual accounting risk vs Ledger OpenRouter `usage_daily`.
4. Multi-profile fleet needs explicit `HERMES_TELEMETRY_HOME` / sync strategy.

## If Helm later pilots

- One home only (prefer Mate scratch or a non-alert bot) — never replace Ledger/Vigil.
- Map `budget.yaml` soft/hard to spend-state (observed soft **$8** / hard **$15**).
- Mark subscription models $0 / `_subscription: true` so SuperGrok/Claude Max do not false-burn local budgets.
- Optional later: **no_agent** script reads telemetry export and calls `spend_halt.sh set` — Ledger still owns clear and `#alerts`.
- Draft budget sample: `_agent/coding/cost/draft_budget.yaml` (local eval tree).

## Explicit non-goals

- Do not give specialists new cost tools that encourage agent self-policing as authority.
- Do not post `#alerts` from the plugin.
- Do not install Langfuse for evey-cost-guard.

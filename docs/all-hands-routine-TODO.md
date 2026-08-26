# ALL-HANDS Routine — Design TODO (to implement later)

> **Status:** SPEC ONLY — captured 2026-08-26 from Michael. Not yet built.
> Formalize as a reusable skill/command (candidate name: `carrier-all-hands`).

## What it is

A fleet-wide emergency mobilization. When invoked, **Helm immediately puts the
ENTIRE fleet on one task** — all available and relevant bots and teams, each doing
their normal role, delegated and coordinated by Helm. Not a single bot, not one
wing — everyone who can meaningfully contribute.

## Triggers (when Helm may/should call all-hands)

1. Something needs to **go LIVE ASAP** (ship a feature/fix under time pressure).
2. The system has a **CRITICAL bug** that must be fixed ASAP (e.g. a crash-loop,
   a billing leak, a broken gateway, a dispatch deadlock).

## Authority granted during all-hands

- Helm gets **full permission to use everything** in the fleet — all wings, all
  bots, all tools, parallel dispatch — to resolve the emergency fast.
- **Subagents/heavy reasoning run on Opus + Sonnet (OAuth).**
- **Billing constraints STILL APPLY (non-negotiable):**
  - Subscription **OAuth only** — Claude Max / SuperGrok. NEVER an Anthropic (or
    any) **API key**.
  - **NO OpenRouter frontier models.** The only OpenRouter models allowed are the
    cheap allowlist: DeepSeek flash/chat, Google Gemini Flash / Flash-Lite, gpt-oss.
  - `billing_guard.py` must still PASS after any change.

## Shape (proposed — refine on build)

1. Helm classifies the emergency and decomposes it into parallel work units.
2. Helm delegates each unit to the right bot/wing in its normal role
   (coding wing fixes code, research wing investigates, maintenance wing audits,
   Marshal tracks on the Kanban, Yeoman handles git/PR, etc.).
3. Partition work by file/area so parallel workers don't conflict.
4. Investigate → confirm root cause → fix → VERIFY (never a plausible-looking fix;
   real reproduction + real verification).
5. Helm synthesizes, confirms resolution, broadcasts status to the fleet.
6. Stand down; log what was done.

## Open design questions (for implementation)

- Invocation surface: a `carrier-all-hands` skill Helm loads, a CLI, a control
  file, or a Kanban priority flag?
- How to pin subagent models to Opus/Sonnet explicitly (delegate_task children
  inherit the parent chain today).
- Interaction with Silent Running (all-hands should preempt / override the ladder).
- Rate/spend guardrails so a runaway all-hands can't burn subscription quota.
- Auto-stand-down criteria + a hard timeout.

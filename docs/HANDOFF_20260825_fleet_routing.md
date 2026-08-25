# Handoff — 2026-08-25 — fleet model routing

Session paused at Michael's request. Everything below is **verified by live
execution**, not inferred. Commit `0e18345` is pushed to `origin/main`.

---

## What was wrong

Two kanban cards (`t_ebc8a180` Vigil, `t_e891c6af` Ledger) were `blocked` with:

```
Agent crash x2: worker exited cleanly (rc=0) without calling
kanban_complete or kanban_block — protocol violation.
```

**That diagnostic is a red herring.** The workers never got a model. Their whole
log was 558 bytes:

```
Query: work kanban task t_ebc8a180
⚠️  No API key found for provider 'openrouter'.
Goodbye! ⚕
```

Two root causes, stacked:

1. **Profiles do not inherit the root `.env`.** When a worker spawns with
   `HERMES_HOME=~/.hermes/profiles/<bot>/`, that profile `.env` is the only one
   read — and all 18 contain Discord tokens only. `OPENROUTER_API_KEY` lives in
   `~/.hermes/.env` and was invisible to every bot.
2. **The OpenRouter credential is dead anyway** — `402`, `last_status:
   exhausted`, `failure_reason: billing`. Seeding the key into profiles would
   have failed too, just with a different error.

The agent then exits `0`, the board sees a clean exit with no terminal kanban
call, scores it a protocol violation, and blocks at the retry limit. Chasing the
"protocol violation" leads nowhere.

## Why the fix needs no secrets

Profiles **do** read the root `auth.json` read-only for OAuth
(`hermes_cli/auth.py:_global_auth_file_path` — "providers authed at the root are
visible to profile processes"). The SuperGrok and Claude Max subscriptions were
reachable the entire time. Routing there first costs $0 marginal and copies no
credential into any profile home. LockBox handshake model is preserved.

---

## The chain (all 18 bots)

```text
grok-4.5 (xai-oauth, SuperGrok $0)
  → claude-sonnet-5 (anthropic, Claude Max $0)
    → paid tail — LAST RESORT ONLY
```

| Tier | Who | Paid tail | Blended $/M |
|---|---|---|---|
| `command` | Helm + Lts (Wrench, Deck, Stacks) | deepseek-chat-v3-0324 → gemini-3.7-flash | 0.44 |
| `cheap` | 14 subagents | deepseek-v4-flash-0731 → gemini-2.5-flash-lite | **0.05** |
| `nocn` | LockBox only | gpt-oss-120b → gemini-2.5-flash-lite | 0.07 |

Subagent tail is **~8.8x cheaper** (0.4375 → 0.0500 blended $/M). LockBox is
**12x cheaper** and keeps its non-China constraint; `gpt-4o-mini` is retired.

**All three tails were tool-call tested** against a `kanban_complete` schema
before commit. This is not optional: a model that cannot emit a tool call
reproduces the exact rc=0 protocol violation this work fixed. Any future model
swap must repeat that test.

## Source of truth

`scripts/apply_bot_matrix.sh` hardcoded the old per-bot pins and would have
**silently reverted** any hand-edited `~/.hermes/profiles/*/config.yaml` on its
next run. 17 hardcoded `pin` lines are now `pin <bot> grok-4.5 xai-oauth` +
`chain <bot> <tier>`; `chief_of_staff` is handled by its inline python block.

Edit the script, not the live configs.

Also removed: `lockbox`'s scalar `model.fallback` key, which shadows the
`fallback_providers` list form.

---

## Verified live

| Check | Result |
|---|---|
| 18/18 profiles resolve the chain | PASS |
| Live model call, `OPENROUTER_API_KEY` unset | PASS — CoS, Vigil, Ledger, LockBox, Deck, Mate |
| `grok-4.5` / `claude-sonnet-5` reachable from a profile | PASS (`GROK_OK` / `SONNET_OK`) |
| Cheap + nocn tails emit real `tool_calls` | PASS (all 3) |
| CoS keeps 13 aliases, `hermes-cli`, OSB writes | PASS |
| `hermes-cli` super-user is Helm **only** | PASS (audited all 18) |
| Lts still stripped of execution tools | PASS |
| `t_ebc8a180` Vigil | **done** — #command msg `1541905969439834113` |
| `t_e891c6af` Ledger | **done** — #command msg `1541905776145211472` |

Ledger: daily **$8.77**, over soft $8, under hard $15; SPEND_HALT clear.
Vigil: DISPATCH_LOCK/SPEND_HALT open; correctly declined to invent quota
percentages it could not measure.

Note: `grep` still finds "No API key found" in those two logs. Kanban logs
**append** — those are lines 3–15 from the archived failed runs. The successful
run starts at line 19 and is clean.

---

## Open / next

1. **`t_be2d9b8a` (lockbox) is marked `done` but never ran.** Its log is the same
   558-byte missing-key exit. That `done` is false — any LockBox Phase-B state
   believed to come from it is **unverified**. Reopen and re-run.
2. **OpenRouter is at its credit cap.** The tails are last-resort, so the fleet
   runs fine on subscriptions, but the paid safety net is currently non-functional
   until the limit is raised.
3. **`bots/BOT_MATRIX.md` left uncommitted on purpose.** A sibling agent has an
   in-flight Lieutenants section in that file. My one-line alias edit
   (`deepseek-chat-v3-0324` → `deepseek-v4-flash-0731`, line 84) is on disk,
   unstaged, for whoever owns that change to fold in.
4. **15 other files were already modified before this session** and were
   deliberately not committed. Only `scripts/apply_bot_matrix.sh` and
   `COST_MODEL.md` are in `0e18345`.
5. Consider `hermes secrets` (Bitwarden/1Password) if profiles ever need real
   API keys — it injects at startup with nothing on disk, matching the LockBox
   pattern. Not needed while the chain stays on OAuth.

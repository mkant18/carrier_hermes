# HANDOFF — Fleet Standup Session (2026-08-25)

**Status:** PARTIAL — structural work complete and verified; **model pinning is BLOCKED
by an unresolved bug.** Read §3 before touching `apply_bot_matrix.sh`.

Session: autonomous engineering standup on Claude Opus 5. Paused at Michael's request.

---

## 1. What is DONE and verified

### Lieutenant layer built out (the main gap)
The 3 Lt bots existed as directories with **empty scaffold stubs** (`<!-- TODO: fill in
purpose -->`) and placeholder smoke tests that only echoed "no smoke tests defined yet."
They were never wired into any automation. Now:

- **`bots/coding_lt/SOUL.md`** — Wrench 🔧, Coding Wing lead over Mate
- **`bots/ops_lt/SOUL.md`** — Deck 🗂️, Ops Wing lead over Inbox/Quill/Chronos/Tasker/Purse
- **`bots/knowledge_lt/SOUL.md`** — Stacks 📚, Knowledge Wing lead over Librarian/Clerk

Each carries authority, explicit "must never do the squadron's work", routing table,
model, tools ON/OFF, write roots, return contract, voice, never-be. Written from
`_agent/explorer/proposals-2026-08-25-lt-layer.md` (Chart's spec) so they match the
approved design.

- **Real Lt smoke tests** (9 checks each, replacing the stubs): soul synced repo→home,
  soul not a stub, model pin, no free-tier, **execution tools barred**, squadron declared,
  never-be clause, mailbox dirs, AIPass dispatch round-trip. All 3 pass, `fail=0`.

### Scripts wired 15 → 18 bots
- `install_bot_homes.sh` — 3 Lts added; **all 18 homes provisioned with correct
  descriptions, verified `missing=0`**. Also fixed a real bug: the script used
  `hermes -p <id> profile describe --text`, which fails with "profile name is required".
  Every description had been silently skipped for the whole roster. Correct form is
  `hermes profile describe <id> --text`. Descriptions live in `profile.yaml`, not `config.yaml`.
- `smoke_fleet.sh` — `fifteen_souls`/`fifteen_bot_homes` → `eighteen_*`; added
  `no_stub_souls` (catches unfilled scaffolds), `lt_model_*`, `lt_squadrons_declared`,
  and missing-home names in the failure message.
- `apply_bot_matrix.sh` — Lt lockdown block added (see §3 for the blocker).

### Classification 36/36 PASS
6 Lt rows added to `docs/CLASSIFICATION_GOLDEN.md` (33–38) + Lt rules placed **first** in
`classify_golden.py` so "route/sequence/coordinate/review a wing" hits the Lt while
do-the-work prompts still hit the specialist. Was 30 prompts, now 36, all passing.

### Discord verified live via REST API
- Guild Carrier Ops `1541154515841974294`; all 4 core channels confirmed present with the
  IDs already in the docs (`#command` `#fleet` `#alerts` `#drafts`). Nothing invented.
- **Single-gateway rule intact:** Carrier Ops token (identity `Carrier Ops`) is on the
  `chief_of_staff` home only; First Watch (identity `FirstWatch`) is on the default home.
  Tokens confirmed **distinct** — no double-poll.
- **First Watch outbound smoke-tested green:** `GET` 200 on all 4 channels and a live
  `POST` to `#fleet` returned **200**, message id `1541903986498736178`.
- Documented a naming discrepancy: runtime vars are `DISCORD_BOT_TOKEN` /
  `DISCORD_FLEET_BOT_TOKEN`, not the `CARRIER_OPS_DISCORD_TOKEN` /
  `FIRST_WATCH_DISCORD_TOKEN` names in the identity matrix's Doppler table.

### Docs reconciled
`README.md` roster 12 → 18 with wings/emoji; `BOT_MATRIX.md` Lieutenants section;
`INTER_AGENT_PROTOCOL.md` relationship graph redrawn with the Lt tier + "command tier is
co-equal beside Helm, never under a Lt"; identity matrix §9 Lt Discord posture; stale
counts fixed (15→18 identities, 12→18 mailboxes, golden 26→38).
`skills/carrier-roster/SKILL.md` got Lt routing + 2 new pitfalls, synced to the Helm home
and user-global so Helm actually routes to the Lts.

`.gitignore` now excludes `_agent/` and `.tmp_*` (bot runtime output, not fleet source).

---

## 2. Smoke state — HONEST

```
PASS  classify_golden (36 prompts)   PASS  eighteen_souls
PASS  preflight_open                 PASS  no_stub_souls
PASS  lock_refuse                    PASS  eighteen_bot_homes
PASS  halt_refuse                    FAIL  lt_model_coding_lt      — got grok-4.5
PASS  aipass_send                    FAIL  lt_model_ops_lt         — got grok-4.5
PASS  osb_vault_readable             FAIL  lt_model_knowledge_lt   — got grok-4.5
PASS  ping_grok                      PASS  lt_squadrons_declared
PASS  ping_claude                    PASS  lockbox_verify_help
FAIL  ping_deepseek — timed out
=== fail=1 ===
```

Per-bot smokes: all 3 Lt smokes and `finance_reader` pass **except** their
`model_pinned` check, which fails for the same reason as §3.

`ping_deepseek` timed out on the final run (it passed earlier in the session) — flaky
DeepSeek reachability, not a config regression. Not papering over it.

**Structural work is green. The only red is model pins.**

---

## 3. ⚠️ BLOCKER — model pins will not hold (UNRESOLVED)

**Symptom:** after `apply_bot_matrix.sh` reports success, **all 18 bots read back
`grok-4.5`** (the global `fallback_providers` entry) instead of their intended pins.

**What I proved:**
- `hermes -p <id> config get` is **read-only** — verified by mtime, it is not the writer.
- `config set model`, `config set model.provider`, `tools disable`, and `mcp_off` are each
  individually clean — pins survive all of them.
- A single bot pinned in isolation **holds for 25s+** even with its `serve` respawned.
- But across the full script run, pins that were confirmed written come back reverted.
- Final state showed 17/18 at `grok-4.5` with `research_agent` (last one I touched
  manually) correct — i.e. a **bulk rewrite**, not per-bot drift.

**Partial mitigation already committed** (keep it, it is sound):
- `quiesce_serves()` stops roster `serve` processes before pinning.
- `pin()` retries up to 3× with a per-bot `pkill` and verifies the write landed.
- A final `verify_pin` pass reads all 18 back and **exits 1** on drift, so this can never
  silently pass again. This is what caught the problem honestly.

**Leading hypothesis (untested):** something holds the whole roster's config in memory and
flushes it — most likely the Desktop app or the `-p default dashboard` / `serve` supervisor
(PID `11614` `serve --host 127.0.0.1`, PID `97531` dashboard). Desktop is known to
auto-respawn Bot Mode serves.

**Next steps:**
1. Quit Hermes **Desktop** entirely, then run `apply_bot_matrix.sh` from a bare terminal
   and re-check. This is the highest-value single experiment.
2. If that fixes it, the script needs a Desktop-running guard that refuses to pin (or
   warns loudly) rather than reporting false success.
3. Consider whether pins belong in `profile.yaml`/an override the supervisor won't stomp.
4. Do **not** just re-run the script — the second run gets clobbered identically.

**Nothing about the Lt design or SOULs is implicated.** The Lts are correctly configured
in every other respect: tool surface verified as exactly
`[clarify, file, kanban, memory, session_search, skills, todo]` — no terminal,
code_execution, browser, computer_use, delegation, or web. Stacks' OSB is read-only with
save/capture/update excluded. Helm's SUPER-USER surface (`hermes-cli`, top-level
`fallback_providers`, OSB writes) was checked and **not** stripped.

---

## 4. Not done

- **Commit does not include working model pins** — §3.
- `#ready-room`, `#catapult`, `#hangar-deck`, `#lso-notes` still do not exist on the server
  (Michael must create them; docs correctly leave IDs blank).
- No cron jobs created for the Lts.
- No shadow-mode flags changed, no TL raised, no `unshadow` phrases acted on. Untouched.
- `COST_MODEL.md` / `GOVERNANCE.md` not given explicit Lt rows (policy already covers them
  via `quality` tier).

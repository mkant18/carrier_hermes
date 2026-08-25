# HANDOFF — Fleet Discord + Model Pin Session (2026-08-25 Session 3)

**Status:** CLEAN — model pin bug resolved, Discord wiring complete, smoke `fail=0`.

---

## What was done this session

### 1. Model pin bug — RESOLVED

**Root cause (confirmed):** `hermes -p <id> config set` routes through the in-memory serve
process. The serve holds a full copy of the bot's config in RAM and writes it back on its
own cadence, overwriting disk writes. Per-bot pkill between writes was insufficient because
Desktop respawned the serve fast enough to read the pre-write disk state and then flush it.

**Fix in `apply_bot_matrix.sh`:**
- `pin()` now writes YAML **directly** (Python, bypassing the serve entirely) — never calls
  `hermes config set` for model pins.
- `chain()` now accepts `primary_model` / `primary_provider` args so Lts get their correct
  primary model without chain overwriting it back to `grok-4.5`.
- After **all** writes are done, a **mass kill** of all roster serves lets Desktop respawn
  them from the freshly-written disk state. Single-pass, no per-bot races.
- `verify_pin` reads YAML directly — confirms all 18 held.

**Result:** `apply_bot_matrix.sh` exits 0 with `all 18 pins verified on disk`.

### 2. Lt model pins — ALIGNED to BOT_MATRIX spec

`coding_lt` / `ops_lt` / `knowledge_lt` now correctly pin to:
- **Primary:** `anthropic/claude-sonnet-4-6` (Claude Max subscription, $0 marginal)
- **Fallback 1:** `anthropic/claude-sonnet-5` (Claude Max subscription, $0 marginal)
- **Fallback 2+:** OpenRouter cheap non-frontier (DeepSeek V3, Gemini Flash)

The previous session incorrectly pinned Lts to `xai-oauth/grok-4.5`. The BOT_MATRIX spec
has always said "quality Sonnet Max" for Lts. Fixed in both apply script and smoke.

**Policy reconfirmed:** Frontier models (`grok-4.5`, Opus, `claude-sonnet-4-6`, Sonnet Max)
are SUBSCRIPTION-ONLY via `xai-oauth` or `anthropic` providers. OpenRouter is ONLY for
cheap non-frontier models in the fallback tail. This guard is enforced in `chain()`.

### 3. Discord infrastructure built

#### `scripts/fleet_signal.sh` — DISPATCH/ACK/TRAP poster
Standard DISPATCH / ACK / TRAP lines to `#fleet` via First Watch REST. All bots call this
for the fleet-wide handoff board instead of posting ad hoc. Smoke-tested live: `200`.

Usage:
```bash
fleet_signal.sh DISPATCH Helm ⚓ JOB-001 "routing auth refactor to Mate"
fleet_signal.sh ACK      Mate 🔧 JOB-001 "on station — beginning work"
fleet_signal.sh TRAP     Mate 🔧 JOB-001 "complete — PR #42 opened"
fleet_signal.sh RAW      "freeform message to #fleet"
```

#### `scripts/alert_signal.sh` — #alerts poster
Structured embed alerts to `#alerts`. Prefers `CARRIER_ALERTS_WEBHOOK` (zero token
exposure); falls back to First Watch REST. Used by Vigil, Ledger, LockBox.

Usage:
```bash
alert_signal.sh Vigil WARN "Subscription quota at 90%"
alert_signal.sh Ledger HARD "OpenRouter spend exceeded $10"
alert_signal.sh LockBox INFO "Grant issued to ops_lt for vault_key"
# Levels: SOFT WARN HARD INFO OK
```

#### `scripts/install_bot_homes.sh` — Discord channel posture wired for all 18 bots
`wire_discord_env()` writes `DISCORD_HOME_CHANNEL` and `DISCORD_ALLOWED_CHANNELS` to each
bot's `.env`. Channels per bot:

| Tier | Home | Allowed |
|---|---|---|
| Helm | `#command` | `#command`, `#fleet`, `#alerts`, `#drafts` |
| Vigil, Ledger | **`#fleet`** via First Watch | `#alerts` (hard breaches). **Never `#command` via First Watch.** |
| LockBox | `#alerts` | `#alerts` only |
| Lts (Wrench, Stacks) | `#fleet` | `#fleet` |
| Deck (Ops Lt) | `#fleet` | `#fleet`, `#drafts` |
| Quill (email_drafter) | `#fleet` | `#fleet`, `#drafts` |
| All other specialists | `#fleet` | `#fleet` |

### 4. Smoke suite expanded

`smoke_fleet.sh` now runs 23 checks (was 18):

| New check | What it verifies |
|---|---|
| `fleet_signal_post` | First Watch REST POST to `#fleet` → 200 (live) |
| `lt_pin_disk_coding_lt` | YAML direct read: `anthropic/claude-sonnet-4-6` |
| `lt_pin_disk_ops_lt` | YAML direct read: `anthropic/claude-sonnet-4-6` |
| `lt_pin_disk_knowledge_lt` | YAML direct read: `anthropic/claude-sonnet-4-6` |
| `lt_model_*` (updated) | Note that disk reads (#11) are authoritative; serve-based is secondary |

**Smoke result:** `fail=0` — all 23 checks passing.

---

## Current smoke state

```
PASS  classify_golden (36 prompts)   PASS  eighteen_souls
PASS  preflight_open                 PASS  no_stub_souls
PASS  lock_refuse                    PASS  eighteen_bot_homes
PASS  halt_refuse                    PASS  lt_model_coding_lt
PASS  aipass_send                    PASS  lt_model_ops_lt
PASS  osb_vault_readable             PASS  lt_model_knowledge_lt
PASS  ping_grok                      PASS  lt_squadrons_declared
PASS  ping_claude                    PASS  lockbox_verify_help
PASS  ping_deepseek                  PASS  fleet_signal_post
PASS  chronos_handoff_tasker         PASS  lt_pin_disk_coding_lt
                                     PASS  lt_pin_disk_ops_lt
                                     PASS  lt_pin_disk_knowledge_lt
=== fail=0 ===
```

---

## What is NOT done (scope for next session)

- `#ready-room`, `#catapult`, `#hangar-deck`, `#lso-notes` channels: Michael must create
  on the Discord server; IDs remain blank in docs. No bot work blocked on this.
- `CARRIER_ALERTS_WEBHOOK`: Michael should create a Discord webhook for `#alerts` and set
  `CARRIER_ALERTS_WEBHOOK=<url>` in `~/.hermes/.env`. Until then, `alert_signal.sh` falls
  back to First Watch REST (works, just less isolated).
- Lt cron jobs: not created this session.
- Shadow mode / TL unchanged. Clerk intake still `trust_override:intake_enabled` only.
- `COST_MODEL.md` / `GOVERNANCE.md` Lt rows: policy already covers Lts via `quality` tier;
  explicit rows would be cosmetic.

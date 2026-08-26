# Fleet Model Routing Override — Grok Disable / Claude Sonnet Swap

> **Status:** Tool available. Apply on demand; restore when done.  
> **Script:** `scripts/disable_grok_use_sonnet.py`  
> **Scope:** All 25 Hermes bot profiles (primary + fallback slots)

---

## What this does

Temporarily replaces every `xai-oauth/grok-4.5` reference across all bot `config.yaml` files with `anthropic/claude-sonnet-4-6`. Covers both **primary** provider slots (decision-tier bots) and **fallback[0]** slots (worker-tier bots). The rest of each bot's provider chain (OpenAI Codex, Haiku tail, etc.) is untouched.

| Bot tier | Before | After |
|---|---|---|
| Decision bots (Helm, Marshal, LTs, pr_reviewer, repair_planner, hermes_ai_explorer) | Primary: `xai-oauth/grok-4.5` | Primary: `anthropic/claude-sonnet-4-6` |
| Worker bots (firstmate, lockbox, git_yeoman, watchers, …) | Fallback[0]: `xai-oauth/grok-4.5` | Fallback[0]: `anthropic/claude-sonnet-4-6` |

billing_guard continues to pass — all routes remain subscription-OAuth, no API keys, no OpenRouter frontier.

---

## Apply (disable Grok, use Sonnet)

```bash
HPY="C:/Users/micha/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
"$HPY" "C:/Users/micha/carrier_hermes/scripts/disable_grok_use_sonnet.py"
```

Expected output: `Made 25 substitution(s) across 26 config(s). ⚡ GROK DISABLED`

Backups are written automatically:
- Each profile: `config.yaml.grok_bak` (next to the original)
- Manifest: `C:\Users\micha\AppData\Local\hermes\carrier\grok_disable_backup.json`

---

## Dry-run (preview only, no writes)

```bash
"$HPY" "C:/Users/micha/carrier_hermes/scripts/disable_grok_use_sonnet.py" --dry-run
```

---

## Restore (re-enable Grok)

```bash
"$HPY" "C:/Users/micha/carrier_hermes/scripts/disable_grok_use_sonnet.py" --restore
```

Reads every `.yaml.grok_bak` file back over the live config, then deletes the backup. Run billing_guard after to confirm clean state.

---

## Verify after either operation

```bash
# No xai-oauth/grok should remain after disable:
grep -rl "grok\|xai-oauth" "C:/Users/micha/AppData/Local/hermes" --include="config.yaml"

# Billing guard must pass:
"$HPY" "C:/Users/micha/carrier_hermes/scripts/billing_guard.py" \
  --hermes-home "C:/Users/micha/AppData/Local/hermes"
```

---

## Notes

- The script is **idempotent** — running disable twice is safe (second run finds no grok slots to swap; backup is already present from the first run).
- The script does **not** restart any running bots. Config changes take effect on next bot session spawn or gateway restart. Helm (chief_of_staff) picks up the new primary on its next agent turn.
- **Do not commit the `.grok_bak` files** — they are local-only backups, already in `.gitignore` coverage via the `*.bak` pattern.
- This doc lives alongside the billing policy (`BILLING_HARD_DENY.md`). The disable/restore toggle is an operational procedure, not a permanent routing change.

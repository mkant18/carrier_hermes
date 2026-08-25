# RESULT PACKET
- job_id: ledger-halt-example
- from: api_watcher
- status: completed
- finished_at: 2026-08-25T16:10:00Z
- shadow_mode: true

## Summary for Michael (≤5 bullets)

- OpenRouter `usage_daily` exceeded hard cap
- Wrote `~/.hermes/carrier/SPEND_HALT`
- Helm must refuse new metered dispatches

## Artifacts

- path: $HOME/.hermes/carrier/SPEND_HALT
- path: $OBSIDIAN_VAULT_PATH/_agent/api_watcher/spend-state.json

## Structured

```json
{
  "halt": true,
  "reason": "openrouter_daily_hard_cap",
  "usage_daily": 12.5,
  "hard_cap_daily": 10.0
}
```

## Idempotency

- state_file_updated: true
- keys_processed: ["daily_hard"]

## Issues

- blockers: ["new metered dispatches halted"]
- confidence: high

## Follow-ups

- aipass_sent_to: chief_of_staff / spend-halt
- clerk_candidates: []
- tasker_actions: []

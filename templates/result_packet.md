# RESULT PACKET
- job_id: {{same as job}}
- from: {{bot_id}}
- status: {{completed|partial|blocked|failed}}
- finished_at: {{iso8601}}
- shadow_mode: {{true|false}}

## Summary for Michael (≤5 bullets)

- {{...}}

## Artifacts

- path: {{absolute or vault-relative}}

## Structured

```json
{ }
```

## Idempotency

- state_file_updated: {{true|false}}
- keys_processed: []

## Issues

- blockers: []
- confidence: {{high|medium|low}}

## Follow-ups

- aipass_sent_to: {{none | bot_id + mission}}
- clerk_candidates: []
- tasker_actions: []

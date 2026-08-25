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

## Model Footprint

- model: {{model_id — e.g. deepseek/deepseek-chat-v3-0324 | grok-4.5 | claude-sonnet-4-6}}
- provider: {{openrouter | anthropic | xai-oauth | no_agent}}
- via_openrouter: {{true | false}}
- tokens_in: {{~N}}
- tokens_out: {{~N}}
- cost_estimate: {{~$X.XXXX | subscription — $0 marginal | $0 no-LLM heartbeat}}

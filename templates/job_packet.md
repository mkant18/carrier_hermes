# JOB PACKET
- job_id: {{job_id}}
- from: chief_of_staff
- to: {{bot_id}}
- created_at: {{iso8601}}
- priority: {{low|normal|high|critical}}
- shadow_mode: {{true|false}}
- michael_visible_summary: {{one line Helm will tell Michael}}

## Goal

{{one paragraph, self-contained}}

## Context (self-contained)

- facts:
  - {{...}}
- constraints:
  - {{constitution; TL0; no send}}
- untrusted_input: {{true|false}}
- related_paths:
  - {{only paths this bot may read}}
- state_file: {{$OBSIDIAN_VAULT_PATH/_agent/<domain>/state.json}}
- aipass: {{none | send result to <bot_id>}}

## Acceptance criteria

- [ ] {{checkable}}
- [ ] Result packet written
- [ ] No tools outside BOT_MATRIX for this bot

## Return contract

Use `templates/result_packet.md`. Write artifacts under your write root.
Do not contact other bots except AIPass if `aipass:` is set.

## Escalation

If blocked: `status=blocked`, stop. Do not invent credentials or expand scope.
If `DISPATCH_LOCK` or `SPEND_HALT` appears mid-run: stop new metered calls; report.

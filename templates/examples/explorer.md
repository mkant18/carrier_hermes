# JOB PACKET
- job_id: cron-scout-example
- from: chief_of_staff
- to: hermes_ai_explorer
- created_at: 2026-08-25T16:00:00Z
- priority: low
- shadow_mode: true
- michael_visible_summary: Periodic fleet/cost/connector proposals

## Goal

Produce explorer report + top 5 proposals. Do not apply config.

## Context (self-contained)

- facts:
  - Constitution forbids :free on Inbox/Chronos/Tasker
- constraints:
  - Advisory only
  - Write `_agent/explorer/` only
- untrusted_input: false
- related_paths:
  - ~/carrier_hermes
  - $OBSIDIAN_VAULT_PATH/_agent/
- state_file: $OBSIDIAN_VAULT_PATH/_agent/explorer/state.json
- aipass: none

## Acceptance criteria

- [ ] report-*.md and proposals-*.md written
- [ ] Claims cited (session, path, or URL)

## Return contract

Report path + proposals table (problem, fix, effort, $ impact, risk).

## Escalation

If quota-tight: shorten to cost lane only.

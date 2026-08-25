# JOB PACKET
- job_id: kanban-todoist-example
- from: chief_of_staff
- to: todoist_manager
- created_at: 2026-08-25T16:00:00Z
- priority: normal
- shadow_mode: true
- michael_visible_summary: Propose Todoist upserts from Chronos handoff

## Goal

Apply (or propose, if shadow) the `todoist_actions[]` from the calendar summary.

## Context (self-contained)

- facts:
  - Chronos does not own Todoist
- constraints:
  - shadow_mode true → proposals file only
  - No calendar mutate, no email
- untrusted_input: false
- related_paths:
  - $OBSIDIAN_VAULT_PATH/_agent/calendar/summary-example.md
- state_file: $OBSIDIAN_VAULT_PATH/_agent/todoist/state.json
- aipass: none

## Acceptance criteria

- [ ] Idempotent keys respected
- [ ] No live API write while shadow

## Return contract

Proposal path or todoist ids + state.json.

## Escalation

Missing MCP: `status=blocked` `todoist_unwired`.

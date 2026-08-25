# JOB PACKET
- job_id: kanban-coding-example
- from: chief_of_staff
- to: firstmate
- created_at: 2026-08-25T16:00:00Z
- priority: high
- shadow_mode: true
- michael_visible_summary: Implement the listed acceptance tests on a branch

## Goal

In repo `{{repo}}`, implement `{{change}}` on branch `hermes/<project>/<short>`. Do not push main.

## Context (self-contained)

- facts:
  - Backend order: claude-code → codex → opencode → native workers
- constraints:
  - Never push main/master
  - No overlapping path claims
- untrusted_input: false
- related_paths:
  - {{repo}}
- state_file: $OBSIDIAN_VAULT_PATH/_agent/state/firstmate-fleet.json
- aipass: none

## Acceptance criteria

- [ ] Tests run; result recorded
- [ ] Branch name reported
- [ ] Credential scan before commit

## Return contract

status, branch, paths_touched[], tests_run, blockers[], summary ≤40 lines.

## Escalation

One retry with adjusted brief, then block.

# JOB PACKET
- job_id: kanban-intake-example
- from: chief_of_staff
- to: obsidian_archivist
- created_at: 2026-08-25T16:00:00Z
- priority: normal
- shadow_mode: true
- michael_visible_summary: Triage research artifacts for keep/discard

## Goal

Triage candidates. At TL0 stage only. Do not file permanently unless `trust_override: intake_enabled`.

## Context (self-contained)

- facts:
  - candidates[] listed below
- constraints:
  - Helm keep/discard unless cos_pre_approved
  - Redact secrets
- untrusted_input: false
- related_paths:
  - $OBSIDIAN_VAULT_PATH/_agent/research/report-2026-08-25-example.md
- state_file: $OBSIDIAN_VAULT_PATH/_agent/archivist/state.json
- aipass: none
- candidates:
  - $OBSIDIAN_VAULT_PATH/_agent/research/report-2026-08-25-example.md
- cos_pre_approved: false
- trust_override: none

## Acceptance criteria

- [ ] `_agent/archivist/triage-*.md` keep/discard table
- [ ] No permanent vault write at TL0

## Return contract

Triage table + staging paths.

## Escalation

Credential-looking strings → `_agent/archivist/quarantine/`.

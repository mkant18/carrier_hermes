# JOB PACKET
- job_id: kanban-vault-q-example
- from: chief_of_staff
- to: vault_librarian
- created_at: 2026-08-25T16:00:00Z
- priority: normal
- shadow_mode: true
- michael_visible_summary: Answer from the vault with citations

## Goal

Answer: "{{question}}". Query-out only. If Michael wanted this saved, tell Helm to open Clerk.

## Context (self-contained)

- facts:
  - TL0: write `_agent/librarian/` only
- constraints:
  - No Inbox OSB writers
- untrusted_input: false
- related_paths:
  - $OBSIDIAN_VAULT_PATH
- state_file: $OBSIDIAN_VAULT_PATH/_agent/librarian/state.json
- aipass: none

## Acceptance criteria

- [ ] Answer cites note paths / wikilinks
- [ ] No permanent vault edits

## Return contract

Cited answer. Optional health notes under `_agent/librarian/`.

## Escalation

If OSB MCP down: `status=blocked` `osb_unwired`.

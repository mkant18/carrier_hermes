# Shadow mode — live mutation policy

**Default: ON** for side-effecting ops until Michael exits.

## Still shadowed (no live mutation)

- Tasker → Todoist API writes (proposals under `_agent/todoist/proposals-*.md` only)
- Chronos → calendar writes (summaries only)
- Clerk → permanent vault notes outside `_agent/` (stage under `_agent/archivist/`)

## Not shadowed (allowed)

- Reads (mail, calendar, vault, Todoist GET)
- `_agent/**` writes
- AIPass mailbox
- Vigil / Ledger lock files
- Mate git **branches** (still never push main)
- Quill drafts + `#drafts` posts
- Helm classify / Kanban create

## Exit criteria (all required)

1. Phase A freeze committed.  
2. Phase B smokes PASS (`docs/CLASSIFICATION_GOLDEN.md`, lock+halt refuse, aipass round-trip, OSB read, model pings, Chronos ≠ Tasker).  
3. Michael explicitly raises Trust Level **or** says “unshadow Todoist/calendar/intake”.  
4. Standing override logged in `_agent/audit/events.jsonl`.

No automatic end date. Absence of protest ≠ exit.

# Shadow mode — live mutation policy

**Updated: 2026-08-25** — Michael exited shadow for named surfaces and raised vault TL to **2**.

## Live (unshadowed 2026-08-25)

| Surface | Bot | Authority | Gate |
|---|---|---|---|
| **Todoist API writes** | Tasker (`todoist_manager`) | `unshadow Todoist` | Job/idempotency via `_agent/todoist/state.json`; no bulk destructive without packet flags |
| **Calendar writes** | Chronos (`calendar_manager`) | `unshadow calendar` | Calendar MCP when wired; Todoist still → Tasker |
| **Clerk permanent intake** | Clerk (`obsidian_archivist`) | `unshadow intake` + **vault TL2** | Job packet `trust_override: intake_enabled` (or CoS grant). File new notes to **`Inbox/`** (TL2). Stage under `_agent/archivist/` without grant. |

Audit: `_agent/audit/events.jsonl` (helm `unshadow` + `raise_tl`).

## Vault Trust Level (constitution)

- **Current: TL2** (vault `CLAUDE.md`, Michael `raise TL` 2026-08-25).
- Allowed beyond `_agent/`: **create in `Inbox/`**; **append** under `## Agent Notes` on existing notes.
- Not yet: create/move/delete in arbitrary non-inbox folders (that’s TL3 + scoped list).

## Still gated / not open season

- OSB Inbox **write** tools stay **excluded** on default MCP and on Librarian / Helm / Scout / non-Clerk homes.
- Clerk without `trust_override: intake_enabled` → stage only under `_agent/archivist/`.
- Mate: never push `main`; branches OK.
- No mail **send** tools.
- LockBox: live only under Helm `HANDSHAKE_GRANT` (see below).

## Always allowed (unchanged)

- Reads (mail, calendar, vault, Todoist GET)
- `_agent/**` writes
- AIPass mailbox
- Vigil / Ledger lock files
- Mate git **branches** (still never push main)
- Quill drafts + `#drafts` posts
- Helm classify / Kanban create

## Exit criteria (reference)

1. Phase A freeze committed.  
2. Phase B smokes (structural); note DeepSeek ping may flake independently.  
3. Michael says exact go phrases per surface / `raise TL`.  
4. Standing override logged in `_agent/audit/events.jsonl`.

No automatic end date. Absence of protest ≠ exit.

## LockBox go-live (2026-08-25)

- **Live** Doppler redeem/rotate under Helm `HANDSHAKE_GRANT` only.
- Bot home: `LOCKBOX_SHADOW_MODE=false` in `~/.hermes/profiles/lockbox/.env`.
- Project/config: `carrier-ops` / `prd` (dev token read-only available).
- Still forbidden: secret values in Discord, AIPass bodies, result packets, Clerk intake.
- Structural gate: `scripts/lockbox_verify_grant.py` before any `doppler secrets get/set`.

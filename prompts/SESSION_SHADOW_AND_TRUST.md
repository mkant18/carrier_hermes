# Session 2 — Shadow exit + Trust Level (walkthrough)

Paste this whole file into a **new** Hermes chat (default bot / this Mac). Product language is **bot**. This session is a **decision walk** with Michael. Do **not** raise TL or unshadow anything unless he says the exact go words below.

## Goal

The third fleet todo: decide **when** (or whether) to leave shadow mode and/or raise vault Trust Level.

Default today: **shadow ON**. Todoist writes, calendar writes, and Clerk permanent vault notes are proposals/staging only.

## Authority (read first, then talk)

- `~/carrier_hermes/prompts/SHADOW_MODE.md`
- `~/carrier_hermes/GOVERNANCE.md` (TL0 table)
- `~/carrier_hermes/docs/PHASE_B_STATUS.md`
- Vault constitution: `/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN/CLAUDE.md`
- OSB wiring: `~/carrier_hermes/integrations/obsidian-second-brain.md`

## Current fact check (do this, do not guess)

1. Confirm Phase A + B commits exist (`git -C ~/carrier_hermes log -3 --oneline`).
2. Re-run `bash ~/carrier_hermes/scripts/smoke_fleet.sh` and paste the PASS/FAIL block.
3. Confirm Clerk OSB write tools are still excluded at TL0 (`obsidian_save_note`, `obsidian_capture`, `obsidian_update_note` on default MCP).
4. Tell Michael honestly what is still shadowed vs already live (reads, `_agent/`, AIPass, Quill drafts, Mate branches, Helm/Kanban).

## Walk Michael through these choices (one at a time)

Do **not** bundle them. After each answer, stop and confirm.

**Q1 — Todoist (Tasker)**  
Keep proposing only, or allow live create/update/complete?

**Q2 — Calendar (Chronos)**  
Keep summaries only, or allow live calendar writes? (Todoist still goes to Tasker via job/AIPass.)

**Q3 — Vault intake (Clerk)**  
Stay TL0 (`_agent/archivist/` staging + Helm keep/discard), or raise TL and allow permanent filing when a job has `trust_override: intake_enabled`?

If he wants TL raised, he must **edit the vault `CLAUDE.md` himself** or explicitly tell you to change the Trust Level sentence in that file. Quote the new level back before writing.

## If he says go

Exact go phrases you may accept:

- `unshadow Todoist`
- `unshadow calendar`
- `unshadow intake` / `raise TL`

Then, and only then:

1. Update `prompts/SHADOW_MODE.md` to record what left shadow and the date.
2. Append one audit line:

```bash
bash ~/carrier_hermes/scripts/audit_append.sh helm unshadow "what=...; by=Michael"
```

3. If intake enabled: document Clerk grant; do **not** globally enable OSB Inbox writers on Librarian/Helm/Scout.
4. Commit + push only the docs he approved (SHADOW_MODE, maybe GOVERNANCE / OSB note). Never commit vault notes.

If he is not ready: write a short “stay shadowed” note in the session and stop. Absence of protest ≠ exit.

## Done when

- [ ] Smoke results shown
- [ ] Three questions answered (or deferred)
- [ ] Either shadow still ON with that recorded, **or** only the named surfaces unshadowed + audit line
- [ ] Vault TL changed only with explicit Michael go

## Report back

What stayed shadowed, what (if anything) unshadowed, TL number, smoke PASS/FAIL, commit SHA if any.

# JOB PACKET
- job_id: lockbox-rotate-example-001
- from: chief_of_staff
- to: lockbox
- created_at: 2026-08-25T18:05:00Z
- priority: high
- shadow_mode: true
- michael_visible_summary: Rotate OpenRouter key in Doppler under Helm rotate grant (dry-run)

## Goal

On-demand rotate of secret ref `carrier/prd/OPENROUTER_API_KEY` after HANDSHAKE_GRANT with actions_allowed including `rotate`. Write new value to Doppler SoT before retiring old (live path Phase B only).

## Context (self-contained)

- facts:
  - subject_bot: lockbox (rotation operator is LockBox itself under Helm grant)
  - grant must include actions_allowed: [rotate] and secret_refs_allowed covering the key
  - order: create new → verify → Doppler set → readback → disable old if allowed
- constraints:
  - no rotation policy engine / no calendar nags
  - no secret values in result packet
  - shadow_mode: simulate steps; blocked if Doppler token absent
- untrusted_input: false
- related_paths:
  - $OBSIDIAN_VAULT_PATH/_agent/lockbox/grants/active/grn_rotate001.json
- state_file: $OBSIDIAN_VAULT_PATH/_agent/lockbox/state.json

## Acceptance criteria

- [ ] Grant verified; rotate action present
- [ ] Result rotation block redacted (status, refs, timestamps only)
- [ ] Audit line appended without values

## Return contract

```json
{
  "grant_id": "grn_rotate001",
  "status": "fulfilled",
  "secret_refs": ["carrier/prd/OPENROUTER_API_KEY"],
  "delivery": null,
  "delivery_path": null,
  "expires_at": null,
  "rotation": {
    "ref": "carrier/prd/OPENROUTER_API_KEY",
    "doppler_updated": true,
    "old_retired": false,
    "shadow": true
  }
}
```

## Escalation

Missing grant rotate scope → denied. Doppler auth failure → error + mail Helm.

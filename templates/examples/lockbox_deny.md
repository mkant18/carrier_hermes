# RESULT PACKET
- job_id: lockbox-deny-example-001
- from: lockbox
- status: completed
- finished_at: 2026-08-25T18:10:00Z
- shadow_mode: true

## Summary for Michael (≤5 bullets)

- Redeem denied: no valid Helm HANDSHAKE_GRANT (direct peer ask)
- subject claimed: email_reader
- secret_refs requested (names only): mail provider password ref
- Action: educate via Helm — ACCESS_REQUEST required; never bypass
- No Doppler call made

## Artifacts

- path: $OBSIDIAN_VAULT_PATH/_agent/lockbox/audit.jsonl

## Structured

```json
{
  "grant_id": "grn_missing",
  "status": "denied",
  "secret_refs": ["carrier/prd/MAIL_PASSWORD"],
  "delivery": null,
  "delivery_path": null,
  "expires_at": null,
  "rotation": null,
  "reason": "missing_or_invalid_grant"
}
```

## Idempotency

- state_file_updated: true
- keys_processed: ["deny:missing_grant"]

## Issues

- blockers: ["present HANDSHAKE_GRANT path from Helm"]
- confidence: high

## Follow-ups

- aipass_sent_to: chief_of_staff / lockbox-deny-educate
- clerk_candidates: []
- tasker_actions: []

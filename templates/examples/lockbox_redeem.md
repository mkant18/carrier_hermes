# JOB PACKET
- job_id: lockbox-redeem-example-001
- from: chief_of_staff
- to: lockbox
- created_at: 2026-08-25T18:00:00Z
- priority: high
- shadow_mode: true
- michael_visible_summary: Mate redeem of GH_TOKEN under Helm grant (dry-run)

## Goal

Verify HANDSHAKE_GRANT and fulfill short-lived delivery of secret ref names only in shadow mode (no live Doppler until Phase B + Michael go).

## Context (self-contained)

- facts:
  - subject_bot: firstmate
  - grant_path: $OBSIDIAN_VAULT_PATH/_agent/lockbox/grants/active/grn_example001.json
  - request_id: arq_example001
- constraints:
  - no raw secret in result packet
  - shadow_mode: do not call live Doppler if credentials absent; report blocked
  - verify HMAC before any fetch
- untrusted_input: false
- related_paths:
  - $OBSIDIAN_VAULT_PATH/_agent/lockbox/grants/active/grn_example001.json
- state_file: $OBSIDIAN_VAULT_PATH/_agent/lockbox/state.json
- aipass: none

## Acceptance criteria

- [ ] Grant integrity verified via scripts/lockbox_verify_grant.py
- [ ] jti single-redeem enforced
- [ ] Result status fulfilled|denied|expired|replay|error with redacted structured block
- [ ] No secret values in packet, Discord, or AIPass

## Return contract

Use templates/result_packet.md + schemas/lockbox_redeem_result.schema.json.

## Escalation

If grant missing/invalid: status=denied or error. Do not invent credentials.

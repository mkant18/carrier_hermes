# HANDSHAKE_GRANT

Issued **ONLY** by Helm (`chief_of_staff`). This is a capability ticket — **NOT** the secret.

- grant_id: grn_{{ulid}}
- jti: {{unique id, single redeem}}
- request_id: arq_{{ulid}}
- from: chief_of_staff
- to_lockbox: lockbox
- subject_bot: {{requesting bot_id}}
- decided_at: {{iso8601}}
- decision: {{approve | deny | narrow}}
- expires_at: {{iso8601}}
- secret_refs_allowed:
  - {{subset of request refs}}
- actions_allowed:
  - {{read_once | read_ttl | rotate | create | delete_meta}}
- ttl_seconds: {{int}}
- delivery: {{env_file | stdout_to_caller_job_only | doppler_inject | path_under_write_root}}
- write_paths_allowed: []
- break_glass: {{true|false}}
- constraints:
  - max_redeems: 1
  - no_log_values: true
  - no_discord: true
  - no_aipass_body_secrets: true
- decision_rationale: {{why approve/deny/narrow — no secrets}}
- integrity:
  - alg: HMAC-SHA256
  - key_id: helm-grant-v1
  - signature: {{hex over canonical body excluding signature field}}

## Storage

- Active (Helm writes, redacted — never secret values):  
  `$OBSIDIAN_VAULT_PATH/_agent/lockbox/grants/active/<grant_id>.json`
- After redeem or expiry: move/archive under `grants/archived/`.
- Integrity HMAC key material: `~/.hermes/carrier/lockbox/keys/helm-grant-v1` (Phase B; not in git).

## Defaults

- Short TTL: **15–60 minutes** expires_at unless Michael/Helm records longer for break_glass.
- `decision: deny` → no redeemable ticket (or DENY receipt only); LockBox no-ops.
- `narrow` → allowed refs/actions are a **strict subset** of the ACCESS_REQUEST.

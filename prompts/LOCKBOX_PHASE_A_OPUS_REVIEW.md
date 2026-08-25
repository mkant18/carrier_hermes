TOKEN EFFICIENCY (hard): Minimal tool calls. No exploration tours. No restating files. No preamble. Prefer 1–3 targeted reads then one short report. Cap output ≤40 lines. No code rewrites unless a blocker is a 1-line schema fix description.

ROLE: Security/protocol reviewer for Carrier Hermes bot LockBox Phase A freeze.

WORKDIR: ~/carrier_hermes
READ ONLY. Do not install bot homes, Doppler, keys, or run Phase B.

SCOPE (only these):
1. bots/lockbox/SOUL.md
2. templates/access_request.md + schemas/access_request.schema.json
3. templates/handshake_grant.md + schemas/handshake_grant.schema.json
4. schemas/lockbox_redeem_result.schema.json
5. scripts/lockbox_verify_grant.py (skim)
6. docs/INTER_AGENT_PROTOCOL.md section "7b. LockBox handshake" only if needed for consistency

REVIEW FOR:
- Protocol holes (bypass, replay, scope expansion, subject confusion)
- Schema/template mismatches
- Secret leakage vectors in packets/return contract
- Integrity design gaps (HMAC canonicalization, jti)
- SOUL vs schema contradictions
- Missing Phase B blockers Michael must decide

OUTPUT: Write ONLY to docs/reviews/LOCKBOX_PHASE_A_OPUS_REVIEW.md

Format exactly:
# LockBox Phase A review (Opus)
## Verdict: APPROVE | APPROVE_WITH_NITS | BLOCK
## Blockers (must fix before Phase B)
- ...
## Nits (optional)
- ...
## Phase B go/no-go note (1–2 sentences)

Then end your chat reply with the single line:
REVIEW_DONE path=docs/reviews/LOCKBOX_PHASE_A_OPUS_REVIEW.md verdict=<VERDICT>

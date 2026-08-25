# LockBox Phase A review (Opus)

## Verdict: APPROVE_WITH_NITS

## Blockers (must fix before Phase B)

- key_id path traversal: `load_key()` builds `keys/<key_id>` from attacker-influenceable `integrity.key_id` with no sanitization. A crafted grant with `key_id: "../../<known-bytes-file>"` lets an attacker choose the HMAC key file, enabling forgery. Pin key_id to an allowlist (e.g. `helm-grant-v1`) and reject path separators.
- Symmetric HMAC collapses issuer/verifier: the same secret verifies AND signs, so LockBox (which must hold the key to verify) can mint its own Helm grants. SOUL invariant "only Helm-issued grant" is not cryptographically enforceable under HMAC. Decide ed25519 (Helm private key, LockBox holds public only) before Phase B, or accept that LockBox can self-grant and document it.
- `--sign` lives in the production verifier. Any invocation with the key present forges valid grants. Remove signing from the redeem/verify path; keep it in a separate Helm-only tool.
- Subject + expiry checks are opt-in flags (`--expect-subject`, `--check-expiry`). SOUL steps 4/5 make both mandatory. The redeem path must ALWAYS pass expected subject and enforce expiry; a caller omitting flags silently bypasses subject-confusion and replay-window defenses.
- jti replay is non-atomic: `jti_seen()` then `mark_jti()` are separate reads/appends with no lock. Concurrent redeems of one jti both pass. SOUL step 6 demands atomic consume-before-fetch. Needs O_EXCL/lockfile or DB unique constraint, done before any Doppler fetch.
- No mechanical subset enforcement: script never checks grant `secret_refs_allowed`/`actions_allowed` ⊆ the ACCESS_REQUEST, nor that the redeem job's requested refs ⊆ grant. Scope expansion / narrow-violation rely entirely on Helm being honest. Add a subset check keyed on `request_id`.

## Nits (optional)

- `expires_at` vs `ttl_seconds` are dual, unreconciled sources of lifetime; define which governs and validate `expires_at <= decided_at + ttl_seconds`.
- access_request `secret_refs.minItems:0` allows an empty request that still passes schema; require at least one of secret_refs/permission_refs.
- grant schema `additionalProperties:true` at root — signed (good) but consider tightening to prevent confusing unsigned-looking extras.
- redeem_result `additionalProperties:false` has no channel for the secret (correct), but confirm `stdout_to_caller_job_only` output channel is not persisted in job logs.
- `write_paths_allowed` not in `constraints.required`; `path_under_write_root` delivery with empty list is undefined — reject that combination.

## Phase B go/no-go note (1–2 sentences)

Structure, templates, and redaction contract are sound and internally consistent; GO for Phase B contingent on Michael deciding the HMAC-vs-ed25519 issuer-separation question and fixing the key_id traversal, mandatory subject/expiry enforcement, atomic jti consume, and subset check. Do not wire Doppler until those six blockers land.

---

## Remediation (Phase B start — same day)

Addressed in tree before bot-home wiring:
1. key_id allowlist + path reject in `lockbox_verify_grant.py`
2. HMAC residual **accepted V1** + documented; signer split to `lockbox_sign_grant.py` (Helm-only)
3. `--sign` removed from verifier
4. `--expect-subject` required; expiry always on
5. Atomic jti via O_EXCL + flock under `~/.hermes/carrier/lockbox/jti/`
6. Subset checks via `--access-request` + `--redeem-refs`

Phase B: lockbox home installed; model Gemini 2.5 Flash / fallback GPT-4o-mini; **no Doppler token**; shadow dry-run PASS; smoke fail=0.

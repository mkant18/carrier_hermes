# Residual risks — Carrier Hermes

See `GOVERNANCE.md`, `COST_MODEL.md`, `prompts/SHADOW_MODE.md`.

| Risk | Mitigation | Residual |
|---|---|---|
| Hermes process dead ⇒ watcher cron dead | External LaunchAgent (`scripts/external_hermes_watchdog.sh`) in Phase B | Until plist installed |
| OpenRouter key missing | Ledger heartbeat fails closed (no false OPEN); Helm still needs halt on 402 | Manual credit check |
| Discord IDs unknown | Names frozen; scripts use webhook env if set | No channel ping until Michael fills IDs |
| Kanban dispatcher off | Phase B enables `kanban.dispatch_in_gateway` | Jobs sit in todo |
| OSB write tools leak to Librarian | MCP exclude on default + Clerk-only grant | Misconfig |
| Bot Mode group chat used as queue | Protocol forbids | Social |
| **Grant forgery** | HMAC-SHA256 allowlisted `helm-grant-v1`; path-safe key load; separate `lockbox_sign_grant.py` (Helm) vs verify (LockBox); key not in git | **V1 residual:** shared HMAC secret means LockBox *could* self-sign if key+signer present — mitigate by not installing signer on lockbox home; prefer ed25519 later |
| **Doppler token theft** | Token only on `lockbox` bot home; least privilege service token; no token in Helm/Mate | Compromised lockbox home |
| **Secret leakage via result packets / AIPass / Discord** | Redacted result schema; constraints `no_log_values` / `no_discord` / `no_aipass_body_secrets`; delivery path modes | LLM echo bug — SOUL + schema not perfect |
| **jti replay** | Atomic O_EXCL + flock under `~/.hermes/carrier/lockbox/jti/`; consume before Doppler; `#alerts` on replay | NFS/odd FS exclusivity edge cases |
| **Prompt-injection in use_case** | Untrusted text; scope never expanded from prose; structural grant subset vs ACCESS_REQUEST + redeem refs | Social engineering of Helm approver |
| **PRC / DeepSeek on LockBox** | COST_MODEL + SOUL hard ban; separate aliases | Mis-set model at install |
| **Subject/expiry bypass** | verify requires `--expect-subject`; expiry always on | Miswired caller still possible if script skipped |

Go/no-go: Phase B smoke checklist in `scripts/smoke_fleet.sh` + IMPLEMENT_PROMPT B8. LockBox Phase B gated on Michael review of SOUL + handshake schemas.

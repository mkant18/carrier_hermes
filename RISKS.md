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
| **Grant forgery** | HMAC-SHA256 (`helm-grant-v1`) + canonical body; LockBox re-verify; key not in git | Key theft / weak key gen at Phase B |
| **Doppler token theft** | Token only on `lockbox` bot home; least privilege service token; no token in Helm/Mate | Compromised lockbox home |
| **Secret leakage via result packets / AIPass / Discord** | Redacted result schema; constraints `no_log_values` / `no_discord` / `no_aipass_body_secrets`; delivery path modes | LLM echo bug — SOUL + schema not perfect |
| **jti replay** | Append-only jti log; consume before Doppler; `#alerts` on replay | Race without file lock at Phase B |
| **Prompt-injection in use_case** | Untrusted text; scope never expanded from prose; structural grant subset | Social engineering of Helm approver |
| **PRC / DeepSeek on LockBox** | COST_MODEL + SOUL hard ban; separate aliases | Mis-set model at install |

Go/no-go: Phase B smoke checklist in `scripts/smoke_fleet.sh` + IMPLEMENT_PROMPT B8. LockBox Phase B gated on Michael review of SOUL + handshake schemas.

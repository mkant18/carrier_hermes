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

Go/no-go: Phase B smoke checklist in `scripts/smoke_fleet.sh` + IMPLEMENT_PROMPT B8.

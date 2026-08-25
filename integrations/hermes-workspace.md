# Integration — hermes-workspace (operator UI)

**Status:** ADOPT for zero-fork install · **DEFER** daily-drive until read-only hardening  
**Phase:** ECO WS-01 (2026-08-25)  
**Package:** `outsourc-e/hermes-workspace` v2.3.0 (`c631425`)  
**Hermes:** vanilla 0.20.5 — **no core fork**  
**Eval artifacts:** `_agent/coding/workspace/INSTALL.md`, `SMOKE.md`

## What it is

Browser/PWA operator surface for Hermes multi-profile fleets. Talks to:

- Gateway OpenAI-compatible HTTP API (default `http://127.0.0.1:8642`)
- Hermes dashboard (carrier: `http://127.0.0.1:9119`)

It does **not** replace AIPass, Kanban, or bot gateways.

## Carrier posture

| Requirement | Result (smoke) |
|---|---|
| No Hermes core fork | PASS (`mode=zero-fork`) |
| Full BOT_MATRIX roster visible | PASS when `HERMES_HOME=$HOME/.hermes` (not a single profile path) |
| Sessions / skills / jobs visible | PASS |
| Agent View read-only | **FAIL** — loopback can create/update kanban tasks |
| No domain MCP write surface on workspace process | **FAIL** — todoist + OSB appear enabled in MCP catalog |

**Interpretation:** upstream product is an operator **control plane**. Carrier needs an extra hardening pass before treating it as a read-only fleet HUD.

## Install (summary)

Full commands: `_agent/coding/workspace/INSTALL.md`.

```bash
git clone https://github.com/outsourc-e/hermes-workspace.git ~/hermes-workspace
cd ~/hermes-workspace && pnpm install
# .env: HERMES_API_URL, HERMES_DASHBOARD_URL, HERMES_AGENT_PATH, HOST=127.0.0.1, PORT=3000
export HERMES_HOME="$HOME/.hermes"   # required for full roster
# Gateway api_server + API key via LockBox ACCESS_REQUEST — never commit keys
pnpm dev   # http://127.0.0.1:3000
```

## Secrets

| Secret | Path |
|---|---|
| `API_SERVER_KEY` / `HERMES_API_TOKEN` | LockBox ACCESS_REQUEST only |
| Optional workspace remote password | LockBox if used |

## Follow-ons

1. Viewer/RO mode (GET allowlist or dedicated profile).
2. Hide or disable domain MCP servers on the workspace process.
3. Permanent `:8642` on chosen gateway with LockBox-managed key.
4. Optional Tailscale expose of `:3000` only after RO hardening.

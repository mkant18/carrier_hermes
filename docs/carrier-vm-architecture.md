# Carrier VM Architecture

## Overview

The carrier fleet uses a **VM-per-bot** pattern, where each autonomous bot
runs in its own isolated Docker container. This mirrors the OpenMausBot
design (see `server/drivers/claude.ts` — `containerProxyEnv`, `brokerSocketPath`)
and provides safety, resource isolation, and reproducible environments.

```
┌─────────────────────────────────────────────────────────┐
│                     Host: Windows 11                    │
│  C:/Users/micha/carrier_hermes  (shared repo, read-only)│
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ carrier-bot │  │ carrier-bot │  │ carrier-bot │    │
│  │  coding_lt  │  │ research_lt │  │     helm    │    │
│  │  port: N/A  │  │  port: N/A  │  │  port: N/A  │    │
│  │  2CPU / 4GB │  │  2CPU / 4GB │  │  2CPU / 4GB │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │             │
│         └────────────────┼────────────────┘             │
│                          │                              │
│              carrier-fleet Docker bridge network        │
└──────────────────────────┼──────────────────────────────┘
                           │
                    (future: mTLS / WireGuard)
```

## Design Principles

### 1. Isolation
Each bot gets its own container with:
- **Read-only** mount of `carrier_hermes` repo (prevents bots from modifying shared code)
- **Read-write** mount of its own profile directory (`hermes/profiles/<bot_id>`)
- Fixed resource ceiling (2 CPU, 4 GB RAM) — one bot can't starve others

### 2. Fallback Mode
When Docker is unavailable (dev machine, Windows without WSL2 Docker), `BotVM`
automatically falls back to a **temp directory workspace**. All exec commands
run as local subprocesses. This keeps the code path identical in both modes.

```python
vm = get_bot_vm("coding_lt")
vm.start()              # Docker container OR temp dir
vm.exec_cmd("ls")       # docker exec OR subprocess.run in temp dir
vm.status()             # container inspect OR dict with workspace path
vm.stop()               # docker stop/rm OR no-op
```

### 3. Factory / Registry
`get_bot_vm(bot_id)` returns a singleton per bot_id within a process.
This prevents duplicate container names from racing starts.

### 4. Fleet Operations
`carrier_vm_manager.py` orchestrates the entire fleet:

```bash
python scripts/carrier_vm_manager.py status --openmaus  # see who's running
python scripts/carrier_vm_manager.py start    # start all VMs
python scripts/carrier_vm_manager.py stop     # graceful shutdown
python scripts/carrier_vm_manager.py exec "python scripts/smoke_fleet.sh"
```

All fleet operations are **parallelized** with `ThreadPoolExecutor` so
starting 6 bots takes the time of one start, not six.

## File Layout

```
docker/
  carrier-bot-vm.yml        # Docker Compose definition for all bot VMs
scripts/
  carrier_bot_vm.py         # BotVM class + get_bot_vm() factory
  carrier_vm_manager.py     # start_fleet_vms(), stop_fleet_vms(), vm_status()
```

## Container Spec

| Property     | Value                        |
|-------------|------------------------------|
| Base image  | `python:3.11-slim`           |
| Network     | `carrier-fleet` (bridge)     |
| CPU limit   | 2 cores                      |
| Memory limit| 4 GB                         |
| Restart     | `unless-stopped`             |
| Repo mount  | `/app/carrier_hermes` (ro)   |
| Profile     | `/app/bot-profile` (rw)      |
| PYTHONPATH  | `/app/carrier_hermes`        |

## Volumes

### `/app/carrier_hermes` (read-only)
The carrier_hermes repository. Mounted read-only so bots can import scripts
and read configs, but cannot push changes from inside their container.

### `/app/bot-profile` (read-write)
The bot's `hermes` profile directory on the host:
`C:/Users/micha/AppData/Local/hermes/profiles/<bot_id>/`

This persists the bot's memory, skills, session history, and Kanban state
across container restarts.

## Network

All bot containers join the `carrier-fleet` Docker bridge network. This
enables:
- Container-to-container communication (future: peer broker IPC)
- Isolation from the host network by default
- Future WireGuard overlay for multi-host fleets

The webhook receiver (`carrier_webhook_receiver.py`) on the host posts
tasks to the Kanban DB, which is read by bots via volume mounts — no
direct network call needed between receiver and bots.

## Starting in Production

```bash
# Start all bots:
docker compose -f docker/carrier-bot-vm.yml --profile all up -d

# Start a specific bot:
docker compose -f docker/carrier-bot-vm.yml --profile coding_lt up -d

# Tail logs:
docker logs -f carrier-bot-coding_lt

# Execute a command in a running bot:
docker exec carrier-bot-coding_lt python scripts/fleet_checkin.py
```

## Approval Gate Integration

Before a bot executes an irreversible action, it calls `request_approval()`
from `carrier_approval_gate.py`. This:
1. Inserts a pending record in `approvals.db`
2. Posts a Discord embed with Approve/Deny buttons to channel `#fleet-ops`
3. Polls the DB (every 5s) until a human responds or the timeout expires

Bots running inside containers call the gate through the shared volume:
```python
# Inside the container, /app/carrier_hermes is the repo
import sys; sys.path.insert(0, '/app/carrier_hermes')
from scripts.carrier_approval_gate import request_approval, is_irreversible
```

## Future Work

- [ ] Switch from `sleep infinity` to a real carrier task runner entrypoint
- [ ] Health dashboard pulling from all container healthchecks
- [ ] WireGuard mesh for multi-host fleets
- [ ] GPU passthrough profile for local LLM bots
- [ ] Auto-scaling: spin up containers on demand from webhook events

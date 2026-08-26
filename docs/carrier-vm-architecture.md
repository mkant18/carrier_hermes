# Carrier Fleet VM Architecture

## Overview

Each carrier bot runs in its own Docker container — the VM-per-bot pattern.
This provides full isolation, independent resource limits, and crash containment.
A bot's container failing never affects other bots.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CARRIER FLEET ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────────┘

  Windows Host (C:\Users\micha)
  ┌───────────────────────────────────────────────────────────────────────┐
  │                                                                       │
  │  Hermes GUI (port 9119)          Discord Fleet Channel                │
  │  Kanban DB (SQLite)              ← #fleet-ops 1541866378255011980     │
  │  Approval Gate DB (SQLite)                     ↑                     │
  │                                                │                     │
  │  ┌─────────────────────────────────────────────┴────────────────┐    │
  │  │              CARRIER INFRASTRUCTURE NETWORK                  │    │
  │  │                  (carrier-fleet bridge)                      │    │
  │  │                  172.28.0.0/16                               │    │
  │  │                                                              │    │
  │  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │    │
  │  │  │carrier-peers │  │carrier-viking│  │carrier-webhook     │ │    │
  │  │  │broker :9876  │  │server  :1933 │  │(Discord) :8800     │ │    │
  │  │  │              │  │              │  │                    │ │    │
  │  │  │ Pub/Sub bus  │  │ Vector store │  │ Button interactions│ │    │
  │  │  │ Registration │  │ Memory layer │  │ → resolve_approval │ │    │
  │  │  └──────────────┘  └──────────────┘  └────────────────────┘ │    │
  │  │           │                                                   │    │
  │  │  ┌────────┴────────────────────────────────────────────┐      │    │
  │  │  │            BOT CONTAINER LAYER (20 bots)            │      │    │
  │  │  │                                                     │      │    │
  │  │  │  carrier-chief_of_staff   (grok-4.5, 2cpu/4G)      │      │    │
  │  │  │  carrier-marshal          (sonnet-4-6, 2cpu/4G)    │      │    │
  │  │  │  carrier-coding_lt        (sonnet-4-6, 2cpu/4G)    │      │    │
  │  │  │  carrier-ops_lt           (sonnet-4-6, 2cpu/4G)    │      │    │
  │  │  │  carrier-knowledge_lt     (sonnet-4-6, 2cpu/4G)    │      │    │
  │  │  │  carrier-maintenance_lt   (ollama/qwen2.5, 2/4G)   │      │    │
  │  │  │  carrier-firstmate        (ollama/qwen2.5, 2/4G)   │      │    │
  │  │  │  carrier-git_yeoman       (ollama/qwen2.5, 2/4G)   │      │    │
  │  │  │  carrier-subscription_watcher  (ollama, 2/4G)      │      │    │
  │  │  │  carrier-api_watcher      (ollama, 2/4G)           │      │    │
  │  │  │  carrier-lockbox          (ollama, 2/4G)           │      │    │
  │  │  │  carrier-passive_watch    (ollama, 2/4G)           │      │    │
  │  │  │  carrier-research_agent   (ollama, 2/4G)           │      │    │
  │  │  │  carrier-hermes_ai_explorer (ollama, 2/4G)         │      │    │
  │  │  │  carrier-todoist_manager  (ollama, 2/4G)           │      │    │
  │  │  │  carrier-email_reader     (ollama, 2/4G)           │      │    │
  │  │  │  carrier-email_drafter    (ollama, 2/4G)           │      │    │
  │  │  │  carrier-calendar_manager (ollama, 2/4G)           │      │    │
  │  │  │  carrier-finance_reader   (ollama, 2/4G)           │      │    │
  │  │  │  carrier-obsidian_archivist (ollama, 2/4G)         │      │    │
  │  │  └─────────────────────────────────────────────────────┘      │    │
  │  └──────────────────────────────────────────────────────────────┘    │
  │                                                                       │
  │  VOLUME MOUNTS PER BOT:                                               │
  │    /repo  ← C:\Users\micha\carrier_hermes  (READ-ONLY)               │
  │    /profile ← C:\...\profiles\<bot_id>\_agent  (READ-WRITE)          │
  │                                                                       │
  └───────────────────────────────────────────────────────────────────────┘
```

---

## Task Flow

```
┌──────────┐    ┌────────────┐    ┌──────────────────┐    ┌──────────────┐
│  Kanban  │───▶│ Dispatcher │───▶│ VM Task Runner   │───▶│  Docker Exec │
│  Board   │    │(hermes cron│    │carrier_vm_task   │    │ in bot       │
│          │    │ or manual) │    │_runner.py        │    │ container    │
└──────────┘    └────────────┘    └──────────────────┘    └──────────────┘
     ▲                                     │                      │
     │                                     │                      │
     └─────────────────────────────────────┘◀─────────────────────┘
              Task status updates                  Output / result
              (done/blocked/comments)
```

### Detailed Task Flow

1. **Kanban INSERT** — New task `status='ready'`, `assignee=<bot_id>`, `workspace_kind=worktree|scratch`

2. **Dispatcher** — Hermes kanban dispatcher (or manual trigger) picks up `ready` tasks

3. **VM Task Runner** (`carrier_vm_task_runner.py`):
   - Registers with carrier-peers broker (`POST /register`)
   - Calls `ensure_bot_vm_running(bot_id)` — starts container if absent
   - Updates task `status='running'`
   - Calls `exec_in_bot_vm(bot_id, command)` — `docker exec` into the bot container
   - For `workspace_kind=worktree`: mounts and cd's to the worktree path inside `/repo`

4. **Docker Exec** — Command runs inside isolated bot container:
   - Repo at `/repo` (read-only)
   - Bot profile at `/profile` (read-write)
   - Uses bot's assigned model via `carrier_provider_driver.route_request()`

5. **Result capture** — stdout/stderr captured and added as Kanban task comment

6. **Status update** — Task set to `done` (rc=0) or `blocked` (rc≠0)

---

## Network Topology

```
  Windows Host
  ┌───────────────────────────────────────────────────┐
  │                                                   │
  │  ┌─────────────────────────────────────────────┐  │
  │  │  carrier-fleet (bridge, 172.28.0.0/16)      │  │
  │  │                                             │  │
  │  │  .2  carrier-peers-broker      :9876        │  │
  │  │  .3  carrier-viking-server     :1933        │  │
  │  │  .4  carrier-ob1-brain         (stdio MCP)  │  │
  │  │  .5  carrier-webhook           :8800        │  │
  │  │  .10 carrier-chief_of_staff                 │  │
  │  │  .11 carrier-marshal                        │  │
  │  │  ... (one IP per bot)                       │  │
  │  │  .30 carrier-obsidian_archivist             │  │
  │  └─────────────────────────────────────────────┘  │
  │                                                   │
  │  Ollama  :11434  (host.docker.internal from ctr)  │
  │  Hermes  :9119   (host.docker.internal from ctr)  │
  │                                                   │
  └───────────────────────────────────────────────────┘

  Containers reach host services via: http://host.docker.internal:<port>
  Containers reach each other via:    http://carrier-<bot_id>:<port>
  Host reaches containers via:        http://localhost:<exposed_port>
```

---

## Memory Flow

```
  BOT REQUEST PROCESSING
  ──────────────────────

  Bot container receives task
        │
        ▼
  carrier_provider_driver.route_request()
        │
        ├── bot_id == chief_of_staff ──▶ XaiOAuthDriver (grok-4.5)
        │                                  └── quota exceeded? → Anthropic fallback
        │
        ├── bot_id == marshal/coding_lt/ops_lt/knowledge_lt
        │                             ──▶ AnthropicOAuthDriver
        │                                  ├── short/classify → haiku
        │                                  └── complex/execute → sonnet-4-6
        │
        └── workers/watchers         ──▶ OllamaLocalDriver (qwen2.5:7b)
                                          └── Ollama unavailable? → Anthropic fallback

  All routed through BillingGuardDriver:
    - Rate limit: 120 req/hour per bot
    - Max output tokens: 8192
    - Logs to carrier/routing_decisions.log
```

---

## Resource Limits Rationale

| Limit | Value | Rationale |
|---|---|---|
| CPUs per bot | 2 | Prevents one bot from monopolizing host CPU; still enough for inference |
| Memory per bot | 4 GB | Covers Python runtime + model client + output buffering |
| Total fleet (20 bots) | 80 GB RAM theoretical max | Docker caps enforce; host has sufficient headroom |
| Restart policy | unless-stopped | Bots auto-recover from crashes; stop only on explicit `docker stop` |
| Network | bridge 172.28.0.0/16 | Isolated from host network; bots reach host via host.docker.internal |

**Why 2 CPUs not 1?**
Anthropic/xAI client calls are I/O-bound but the Python runtime + Hermes tooling
needs CPU for JSON parsing, sqlite, and file ops. 2 CPUs prevents CPU-bound stalls.

**Why 4 GB not 2 GB?**
Hermes agent venv is ~300 MB loaded. Anthropic SDK + dependencies + task output
buffers can spike to 1-2 GB under load. 4 GB gives 2x headroom.

---

## How to Add a New Bot

1. **Add bot_id to ALL_BOT_IDS** in `scripts/carrier_vm_manager.py`

2. **Add to docker-compose.carrier-fleet.yml** — copy any existing service block,
   change `chief_of_staff` → `<new_bot_id>` in all four places:
   - service name
   - `container_name`
   - profile volume path
   - `HERMES_BOT_ID` and `HERMES_PROFILE` env vars

3. **Add model routing** in `scripts/carrier_provider_driver.py`:
   - Add entry to `BOT_DRIVER_MAP`: `"new_bot_id": "anthropic"|"xai"|"ollama"`

4. **Create profile directory**:
   ```bash
   mkdir -p C:/Users/micha/AppData/Local/hermes/profiles/<new_bot_id>/_agent
   ```

5. **Create OpenMausBot config**:
   ```bash
   # Create C:/Users/micha/.openmausbot/bots/<new_bot_id>.json
   # Follow the InstanceConfig schema (see docs/openmausbot-install.md)
   ```

6. **Start the new container**:
   ```bash
   python scripts/carrier_vm_manager.py start <new_bot_id>
   ```

7. **Verify**:
   ```bash
   python scripts/carrier_vm_manager.py status
   python scripts/carrier_vm_health.py
   ```

---

## Approval Gate Integration

Irreversible actions (git_push_main, send_email, delete_file, deploy, merge_pr)
must pass through the approval gate before execution:

```
  Bot task about to execute irreversible action
        │
        ▼
  is_irreversible(action_type) → True
        │
        ▼
  request_approval(bot_id, action_type, description, payload, timeout=300)
        │
        ├── INSERT pending record → approvals.db
        ├── POST Discord embed to #fleet-ops with [Approve] [Deny] buttons
        └── POLL approvals.db every 5s ...
              │
              ├── Discord button click → carrier-webhook :8800 → resolve_approval()
              │                                              → UPDATE approvals.db
              │
              └── Timeout (300s) → auto-Deny → return {approved: False}

  result["approved"] == True → proceed
  result["approved"] == False → raise RuntimeError, abort task
```

---

## Troubleshooting

### Container won't start

```bash
# Check Docker Desktop is running
docker info

# Check image exists
docker images carrier-bot

# Build image if missing
python scripts/carrier_vm_manager.py build

# Check carrier-fleet network
docker network ls | grep carrier-fleet

# Create network if missing
python scripts/carrier_vm_manager.py network
```

### Bot stuck in "absent" state

```bash
# Check all container statuses
python scripts/carrier_vm_manager.py status

# Force restart a specific bot
python scripts/carrier_vm_manager.py ensure <bot_id>

# Check container logs
python scripts/carrier_vm_manager.py logs <bot_id> --tail 100
```

### Health check fails

```bash
# Run health check
python scripts/carrier_vm_health.py

# Shows FLEET_HEALTHY or FLEET_DEGRADED:N_down
# If degraded, check which bots are down:
python scripts/carrier_vm_manager.py status | grep ✗
```

### Approval gate not resolving

```bash
# Check DB for pending approvals
python -c "
import sqlite3
conn = sqlite3.connect(r'C:\Users\micha\AppData\Local\hermes\carrier\approvals.db')
for row in conn.execute('SELECT id, bot_id, status, created_at FROM approvals ORDER BY created_at DESC LIMIT 5'):
    print(row)
"

# Manually resolve an approval
python scripts/carrier_approval_gate.py resolve <approval_id> approve admin-cli
```

### Discord token not working

```bash
# Verify token from Doppler
doppler secrets get DISCORD_FLEET_BOT_TOKEN --plain --project carrier-ops --config prd

# Set in environment if Doppler unavailable
export DISCORD_FLEET_BOT_TOKEN=<token>
```

### xAI quota exceeded

```bash
# Check quota state
cat C:/Users/micha/AppData/Local/hermes/carrier/xai_quota_state.json

# Reset quota state manually (if reset time passed)
echo '{"quota_exceeded": false, "exceeded_at": null, "reset_at": null}' > \
  C:/Users/micha/AppData/Local/hermes/carrier/xai_quota_state.json
```

### Routing decisions log

```bash
# See recent routing decisions
tail -20 C:/Users/micha/AppData/Local/hermes/carrier/routing_decisions.log | python -m json.tool
```

# carrier-peers — Provider-Agnostic Fleet Peer Discovery

carrier-peers lets any Hermes session discover, monitor, and message other active Hermes sessions in the carrier_hermes fleet. It is provider-agnostic — it works with any Hermes session regardless of the underlying LLM (Claude, local models, etc.).

Inspired by the broker pattern from [claude-peers-go](https://github.com/WillyV3/claude-peers-go), reimplemented from scratch in Python stdlib with no external dependencies.

## Architecture

```
Hermes session A (chief_of_staff) ──┐
Hermes session B (coding_lt)       ──┼── carrier_peers_broker.py (port 9876) ── SQLite
Hermes session C (research_lt)     ──┘
```

Each session registers itself with the broker when it starts. The broker maintains a list of active sessions with their current task and capabilities. Sessions expire 90 seconds after their last heartbeat.

## Files

| File | Purpose |
|------|---------|
| `scripts/carrier_peers_broker.py` | HTTP broker server (http.server + sqlite3) |
| `scripts/carrier_peers_client.py` | Client library (urllib.request only) |
| `scripts/carrier_peers_watchdog.py` | Cron-safe watchdog to ensure broker is running |
| `scripts/test_carrier_peers.py` | Self-contained integration test |
| `plugins/carrier-peers/` | Hermes plugin (exposes 4 tools) |

## Broker API

The broker runs on `http://localhost:9876` by default.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/register` | Register a new peer session |
| `DELETE` | `/register?session_id=X` | Unregister a session |
| `POST` | `/heartbeat?session_id=X` | Reset the 90s expiry timer |
| `GET` | `/peers` | List all active (non-expired) peers |
| `POST` | `/message?to_session_id=X` | Send a message to a session |
| `GET` | `/messages?session_id=X` | Retrieve and clear messages for a session |
| `GET` | `/health` | Health check (returns `{status: "ok", peer_count: N}`) |

### Register body

```json
{
  "session_id": "chief_of_staff-12345",
  "bot_id": "chief_of_staff",
  "profile_name": "default",
  "current_task": "Fleet oversight",
  "started_at": 1722000000.0,
  "capabilities": ["dispatch", "kanban"]
}
```

### Send message body

```json
{
  "from_session": "chief_of_staff-12345",
  "content": "Task assigned: review PR #42"
}
```

## Starting the Broker

```bash
# Start manually
python ~/carrier_hermes/scripts/carrier_peers_broker.py

# Start on a different port
python ~/carrier_hermes/scripts/carrier_peers_broker.py --port 9876 --host 127.0.0.1

# Check health
curl http://localhost:9876/health
# → {"status": "ok", "peer_count": 3}

# Use the watchdog (safe to run as a cron job)
python ~/carrier_hermes/scripts/carrier_peers_watchdog.py
# → BROKER_UP  (if already running)
# → BROKER_STARTED  (if it had to start it)
```

State persists in: `C:/Users/micha/AppData/Local/hermes/carrier/peers.db`

## Client Library

```python
from scripts.carrier_peers_client import (
    register, heartbeat, unregister,
    list_peers, send_message, poll_messages
)

BROKER = "http://localhost:9876"

# Register this session
register(BROKER, bot_id="chief_of_staff",
         profile_name="default",
         current_task="Fleet oversight",
         capabilities=["dispatch"])

# List active peers
peers = list_peers(BROKER)
for peer in peers:
    print(peer["bot_id"], "->", peer["current_task"])

# Send a message (resolves bot_id -> session_id automatically)
send_message(BROKER, to_bot_id="coding_lt",
             from_bot_id="chief_of_staff",
             content="Please review PR #42")

# Poll messages for this session
messages = poll_messages(BROKER, bot_id="coding_lt")
for msg in messages:
    print(f"From {msg['from_session']}: {msg['content']}")

# Keep session alive
heartbeat(BROKER, "chief_of_staff")

# Unregister when done
unregister(BROKER, "chief_of_staff")
```

All functions return `False` or `[]` on error — they never raise exceptions.

## Hermes Plugin

The plugin exposes four tools to the LLM:

| Tool | Description |
|------|-------------|
| `list_peers()` | List active fleet sessions |
| `send_peer_message(to_bot_id, message_content)` | Send a message to a peer |
| `read_peer_messages()` | Retrieve messages addressed to this session |
| `announce_task(task_description)` | Update this session's current task |

### Enabling the plugin

**Do not enable fleet-wide until the broker is deployed and reviewed.**

To enable for a single session:

```bash
# In the Hermes profile config
hermes plugins enable carrier-peers
```

Or set in a bot's `config.yaml`:

```yaml
plugins:
  carrier-peers:
    enabled: true
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CARRIER_PEERS_BROKER_URL` | `http://localhost:9876` | Broker endpoint |
| `HERMES_BOT_ID` | `unknown` | This session's bot identifier |
| `HERMES_PROFILE` | _(empty)_ | This session's Hermes profile name |
| `HERMES_SESSION_ID` | _(auto)_ | Override the session ID (default: `{bot_id}-{pid}`) |

## Integration with carrier_hermes

### Bot startup pattern

Add to each bot's initialization (e.g., in a carrier cron hook or fleet start script):

```python
import os
import sys

sys.path.insert(0, os.path.expanduser("~/carrier_hermes/scripts"))
from carrier_peers_client import register, heartbeat

BOT_ID = os.environ.get("HERMES_BOT_ID", "my-bot")
BROKER = os.environ.get("CARRIER_PEERS_BROKER_URL", "http://localhost:9876")

register(BROKER, bot_id=BOT_ID, current_task="Starting up", capabilities=["..."])
```

Then send periodic heartbeats (e.g., every 60 seconds via a background thread or cron).

### Watchdog cron

The watchdog is designed for stable cron output (hash-suppressible):

```python
# In hermes cron config:
# schedule: "*/5 * * * *"
# no_agent: true
# command: python ~/carrier_hermes/scripts/carrier_peers_watchdog.py
```

Outputs only `BROKER_UP` or `BROKER_STARTED` — cron hash suppression will silence
repeat `BROKER_UP` lines so you're only notified on state changes.

## Running Tests

```bash
python ~/carrier_hermes/scripts/test_carrier_peers.py
```

Expected output:

```
Starting broker on port 19876 ...
  ✓ register chief_of_staff
  ✓ register coding_lt
  ✓ list_peers returns both
  ✓ send_message to coding_lt
  ✓ coding_lt receives message
  ✓ message content correct
  ✓ messages cleared after poll
  ✓ heartbeat chief_of_staff
  ✓ unregister chief_of_staff
  ✓ unregister coding_lt
  ✓ peers empty after unregister

────────────────────────────────────────
Results: 11/11 checks passed
PASS
```

## Security

The broker binds to `127.0.0.1` (loopback only) by default. There is no authentication — rely on network isolation (single machine or Tailscale/WireGuard). Do not expose port 9876 to the public internet.

Peer expiry is 90 seconds — a crashed or network-partitioned session falls out of the peer list automatically.

## PR & Review Status

> This system was implemented on `feature/carrier-peers-broker`. The Kanban task
> **"Enable carrier-peers plugin fleet-wide after review"** is blocked on human
> review before plugin activation and broker deployment.
>
> See the PR: `feat: carrier peers broker - provider-agnostic session discovery`

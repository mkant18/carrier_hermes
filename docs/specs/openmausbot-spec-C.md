# Spec C: Webhook-Triggered Agent Dispatch

**Pattern source:** OpenMausBot `server/webhooks.ts` + `server/routines.ts` (shared queued task executor)  
**Assignee:** ops_lt  
**Priority:** 2 (blocked on human review)  
**Wave 1 dependency:** carrier-peers broker (PR #5, port 9876)

---

## Problem

The fleet currently receives work through two paths only:
1. Discord messages (human-initiated)
2. Hermes cron jobs (time-triggered)

There is no way for external systems — GitHub CI, other carrier fleets, monitoring tools, or the peers broker — to trigger a specific bot's task queue without manual intervention. The Wave 1 peers broker (port 9876) can route messages between bots but has no mechanism to dispatch kanban tasks in response to inbound events.

## Proposed Solution

Run a dedicated webhook receiver (port 8800, separate from peers broker at 9876) that accepts authenticated HTTP POST requests and creates kanban tasks in response. The receiver shares the queued task executor pattern with cron routines: multiple arriving webhooks are serialized per-bot, not dropped.

---

## Architecture

```
External sender
    │
    ▼  POST /hooks/<endpoint_id>
    │  Header: Authorization: Bearer <secret>
    │  Body: JSON payload
    ▼
webhook_receiver.py  (port 8800, Flask/FastAPI, standalone process)
    │
    ├─ validate Bearer token (HMAC-SHA256 constant-time compare)
    ├─ check event type against trigger.eventTypes allowlist
    ├─ dedup: check delivery_receipts table for this delivery_id
    ├─ extract task description from payload (or use trigger.prompt)
    │
    ▼  on accept:
kanban DB
    ├─ INSERT INTO tasks (status='ready', assignee=trigger.bot_id, ...)
    └─ INSERT INTO delivery_receipts (key=delivery_id, ...)
    │
    ▼  HTTP 202 Accepted  {"status":"queued","task_id":"t_..."}
```

---

## Data Models

### WebhookTrigger (stored in SQLite)

```python
@dataclass
class WebhookTrigger:
    id: str               # uuid
    endpoint_id: str      # URL path fragment (/hooks/<endpoint_id>)
    secret_hash: str      # HMAC-SHA256 of the secret (never stored in plain)
    name: str             # human label
    prompt: str           # pre-set prompt injected as task body (empty = parse payload)
    bot_id: str           # assignee: coding_lt, ops_lt, research_agent, etc.
    enabled: bool
    created_at: int
    updated_at: int
    last_received_at: int | None
    last_run_id: str | None
    delivery_count: int
    verification_pending: bool  # True until first authenticated request received
    verified_at: int | None
    event_types: list[str]      # empty = accept all; ["push","pull_request"] for GitHub
```

### WebhookAttempt (audit log)

```python
@dataclass  
class WebhookAttempt:
    id: str
    webhook_id: str
    received_at: int
    outcome: Literal["accepted", "captured", "duplicate", "ignored", "rejected"]
    status_code: int
    event_name: str | None   # X-GitHub-Event, X-Event-Type, etc.
    preview: str | None      # first 200 chars of payload
    task_id: str | None      # kanban task created, if accepted
    reason: str | None       # why it was not accepted (for non-accepted outcomes)
```

### Outcome semantics (from OpenMausBot)

| Outcome | Meaning |
|---------|---------|
| `accepted` | Task created, bot queued |
| `captured` | Trigger disabled or verification pending; stored but not run |
| `duplicate` | delivery_id already in receipts; 202 returned, not rerun |
| `ignored` | event_type not in allowlist |
| `rejected` | Bad auth (401) or malformed payload |

---

## Peers Broker Integration

The Wave 1 peers broker (port 9876) gains a new capability: forwarding peer events as webhook calls to the local webhook receiver.

**New peers broker endpoint:** `POST /webhook-forward`

```json
{
  "event_type": "peer_registered",
  "payload": {
    "peer_id": "carrier_alpha",
    "address": "10.0.0.5:9876",
    "capabilities": ["fleet_orchestration"]
  }
}
```

The peers broker authenticates to the webhook receiver using a shared local secret (stored in `~/.hermes/carrier/webhook_local_secret`). This means:
- A new peer fleet registering with the broker → triggers `ops_lt` to evaluate and add to fleet registry
- A peer sending a task message → creates a kanban task for the target bot
- A peer leaving the network → triggers `passive_watch` to update monitoring

**Event type mapping:**

| Peers broker event | webhook event_type | Assigned bot |
|-------------------|-------------------|-------------|
| `peer_registered` | `peer_registered` | `ops_lt` |
| `peer_message` (to specific bot) | `peer_task` | target bot |
| `peer_left` | `peer_left` | `passive_watch` |

---

## Task Body Construction

If `trigger.prompt` is non-empty, it's used as the task body verbatim (static routine pattern).

If `trigger.prompt` is empty, the receiver parses the payload for a task description:

```python
def task_from_payload(payload: dict, event_type: str | None) -> str:
    """Extract a human-readable task description from the webhook payload."""
    # GitHub CI failure
    if event_type in ("check_run", "workflow_run"):
        return f"CI {payload.get('action','?')}: {payload.get('check_run',{}).get('name','?')} — {payload.get('repository',{}).get('full_name','?')}"
    # Peer message
    if event_type == "peer_task":
        return payload.get("message", "Peer task (no message)")
    # Generic fallback: first 200 chars of JSON
    return json.dumps(payload)[:200]
```

The full payload is appended as a code block in the task body for bot context.

---

## Security

- **Bearer authentication** (recommended): `Authorization: Bearer <secret>`
- **Capability URL** (fallback for senders that can't set headers): `/hooks/<endpoint_id>/<secret>` — secret is in the path, so it appears in access logs. Documented as lower security.
- **HMAC-SHA256** with constant-time comparison to prevent timing attacks
- **Verification flow:** New triggers are `verification_pending=True` until they receive one authenticated request. During pending, requests are `captured` (stored) but no task is created. Prevents misconfigured endpoints from creating noise.
- **Deduplication:** `X-Delivery-ID` (GitHub-style) stored in `delivery_receipts`. Retried webhook = same ID = `duplicate` outcome, no second task.

---

## Receiver Process Management

- The webhook receiver runs as a separate process (not inside Helm)
- Started by NSSM service `carrier-webhook-receiver` (same pattern as `carrier-peers-broker`)
- Health check: `GET /health` → `{"status":"ok","triggers":N}`
- Port: 8800 (environment variable `CARRIER_WEBHOOK_PORT` to override)
- Peers broker integration: local-only connection, no external exposure

---

## SQLite Tables

```sql
CREATE TABLE IF NOT EXISTS webhook_triggers (
    id                  TEXT PRIMARY KEY,
    endpoint_id         TEXT UNIQUE NOT NULL,
    secret_hash         TEXT NOT NULL,
    name                TEXT NOT NULL,
    prompt              TEXT NOT NULL DEFAULT '',
    bot_id              TEXT NOT NULL,
    enabled             INTEGER NOT NULL DEFAULT 1,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    last_received_at    INTEGER,
    last_run_id         TEXT,
    delivery_count      INTEGER NOT NULL DEFAULT 0,
    verification_pending INTEGER NOT NULL DEFAULT 1,
    verified_at         INTEGER,
    event_types         TEXT NOT NULL DEFAULT '[]'  -- JSON array
);

CREATE TABLE IF NOT EXISTS webhook_delivery_receipts (
    key         TEXT NOT NULL,     -- X-Delivery-ID header value
    webhook_id  TEXT NOT NULL,
    task_id     TEXT,
    at          INTEGER NOT NULL,
    PRIMARY KEY (key, webhook_id)
);

CREATE TABLE IF NOT EXISTS webhook_attempts (
    id          TEXT PRIMARY KEY,
    webhook_id  TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    outcome     TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    event_name  TEXT,
    preview     TEXT,
    task_id     TEXT,
    reason      TEXT
);
```

Stored in `C:/Users/micha/AppData/Local/hermes/carrier/webhooks.db` (separate from kanban DB to avoid locking contention).

---

## Implementation Path

1. Create `carrier_hermes/scripts/webhook_receiver.py` — Flask/FastAPI app, port 8800
2. Create `carrier_hermes/scripts/webhook_db.py` — SQLite helpers for webhook tables
3. Add NSSM service registration to fleet provisioning docs
4. Extend peers broker (`carrier_hermes/scripts/peers_broker.py`) with `/webhook-forward` endpoint
5. Add `hermes kanban --board carrier create-webhook` CLI convenience wrapper (optional)
6. Write admin script `carrier_hermes/scripts/manage_webhooks.py` — create/list/rotate/delete

---

## Out of Scope (this spec)

- Web UI for managing triggers (OpenMausBot has one; carrier_hermes uses CLI + Discord commands)
- Scheduled (cron-style) routines — already handled by Hermes cron system
- Webhook response body forwarding to the originating system (fire-and-forget model)
- Rate limiting per sender (future, if external webhook volume grows)

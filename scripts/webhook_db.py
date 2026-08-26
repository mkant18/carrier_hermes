"""
webhook_db.py — SQLite helpers for webhook_triggers, delivery_receipts, and attempts tables.

Stored in: C:/Users/micha/AppData/Local/hermes/carrier/webhooks.db
Separate from kanban.db to avoid locking contention under concurrent HTTP load.

Tables:
  webhook_triggers          — registered webhook endpoints + routing config
  webhook_delivery_receipts — dedup ledger keyed by X-Delivery-ID
  webhook_attempts          — immutable audit log of every inbound request
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "CARRIER_WEBHOOK_DB",
        r"C:\Users\micha\AppData\Local\hermes\carrier\webhooks.db",
    )
)


def get_db_path() -> Path:
    return Path(
        os.environ.get("CARRIER_WEBHOOK_DB", str(DEFAULT_DB_PATH))
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS webhook_triggers (
    id                   TEXT PRIMARY KEY,
    endpoint_id          TEXT UNIQUE NOT NULL,
    secret_hash          TEXT NOT NULL,
    name                 TEXT NOT NULL,
    prompt               TEXT NOT NULL DEFAULT '',
    bot_id               TEXT NOT NULL,
    enabled              INTEGER NOT NULL DEFAULT 1,
    created_at           INTEGER NOT NULL,
    updated_at           INTEGER NOT NULL,
    last_received_at     INTEGER,
    last_run_id          TEXT,
    delivery_count       INTEGER NOT NULL DEFAULT 0,
    verification_pending INTEGER NOT NULL DEFAULT 1,
    verified_at          INTEGER,
    event_types          TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS webhook_delivery_receipts (
    key         TEXT NOT NULL,
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
"""


def open_db(path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialize) the webhooks DB. Creates directories as needed."""
    db_path = path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(DDL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

Outcome = Literal["accepted", "captured", "duplicate", "ignored", "rejected"]


@dataclass
class WebhookTrigger:
    id: str
    endpoint_id: str
    secret_hash: str        # HMAC-SHA256 hex of raw secret — never stored in plain
    name: str
    prompt: str             # pre-set task body; empty = parse payload
    bot_id: str             # kanban assignee
    enabled: bool
    created_at: int
    updated_at: int
    last_received_at: int | None
    last_run_id: str | None
    delivery_count: int
    verification_pending: bool  # True until first authenticated request received
    verified_at: int | None
    event_types: list[str]  # empty list = accept any event type


@dataclass
class WebhookAttempt:
    id: str
    webhook_id: str
    received_at: int
    outcome: Outcome
    status_code: int
    event_name: str | None
    preview: str | None
    task_id: str | None
    reason: str | None


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def hash_secret(secret: str) -> str:
    """Return HMAC-SHA256 hex of the raw secret. One-way — secret not recoverable."""
    return hmac.new(
        secret.encode(), secret.encode(), hashlib.sha256
    ).hexdigest()


def _secret_hash(raw_secret: str) -> str:
    """Stable hash used for storage: sha256(raw_secret)."""
    return hashlib.sha256(raw_secret.encode()).hexdigest()


def verify_bearer(raw_secret: str, stored_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    candidate = _secret_hash(raw_secret)
    return hmac.compare_digest(candidate, stored_hash)


def generate_secret() -> str:
    """Generate a URL-safe 32-byte bearer token."""
    return secrets.token_urlsafe(32)


def generate_endpoint_id() -> str:
    """Generate a short random endpoint path fragment."""
    return secrets.token_urlsafe(16)


# ---------------------------------------------------------------------------
# Trigger CRUD
# ---------------------------------------------------------------------------

def create_trigger(
    conn: sqlite3.Connection,
    *,
    name: str,
    bot_id: str,
    prompt: str = "",
    event_types: list[str] | None = None,
    secret: str | None = None,
    endpoint_id: str | None = None,
) -> tuple[WebhookTrigger, str]:
    """
    Create a new WebhookTrigger.
    Returns (trigger, raw_secret) — raw_secret shown exactly once to the user.
    """
    raw_secret = secret or generate_secret()
    eid = endpoint_id or generate_endpoint_id()
    now = int(time.time())
    trigger_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO webhook_triggers (
            id, endpoint_id, secret_hash, name, prompt, bot_id,
            enabled, created_at, updated_at, last_received_at, last_run_id,
            delivery_count, verification_pending, verified_at, event_types
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, NULL, 0, 1, NULL, ?)
        """,
        (
            trigger_id,
            eid,
            _secret_hash(raw_secret),
            name,
            prompt,
            bot_id,
            now,
            now,
            json.dumps(event_types or []),
        ),
    )
    conn.commit()

    trigger = WebhookTrigger(
        id=trigger_id,
        endpoint_id=eid,
        secret_hash=_secret_hash(raw_secret),
        name=name,
        prompt=prompt,
        bot_id=bot_id,
        enabled=True,
        created_at=now,
        updated_at=now,
        last_received_at=None,
        last_run_id=None,
        delivery_count=0,
        verification_pending=True,
        verified_at=None,
        event_types=event_types or [],
    )
    return trigger, raw_secret


def get_trigger_by_endpoint(
    conn: sqlite3.Connection, endpoint_id: str
) -> WebhookTrigger | None:
    """Look up trigger by endpoint_id (URL path fragment)."""
    row = conn.execute(
        "SELECT * FROM webhook_triggers WHERE endpoint_id = ?", (endpoint_id,)
    ).fetchone()
    return _row_to_trigger(row) if row else None


def get_trigger_by_id(
    conn: sqlite3.Connection, trigger_id: str
) -> WebhookTrigger | None:
    row = conn.execute(
        "SELECT * FROM webhook_triggers WHERE id = ?", (trigger_id,)
    ).fetchone()
    return _row_to_trigger(row) if row else None


def list_triggers(conn: sqlite3.Connection) -> list[WebhookTrigger]:
    rows = conn.execute(
        "SELECT * FROM webhook_triggers ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_trigger(r) for r in rows]


def update_trigger(
    conn: sqlite3.Connection,
    trigger_id: str,
    **fields,
) -> None:
    """
    Update arbitrary fields on a trigger.
    Allowed: name, prompt, bot_id, enabled, event_types.
    """
    allowed = {"name", "prompt", "bot_id", "enabled", "event_types"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    if "event_types" in updates:
        updates["event_types"] = json.dumps(updates["event_types"])
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [trigger_id]
    conn.execute(
        f"UPDATE webhook_triggers SET {set_clause} WHERE id = ?", values
    )
    conn.commit()


def delete_trigger(conn: sqlite3.Connection, trigger_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM webhook_triggers WHERE id = ?", (trigger_id,)
    )
    conn.commit()
    return cur.rowcount > 0


def rotate_secret(
    conn: sqlite3.Connection, trigger_id: str
) -> tuple[str, str]:
    """Rotate the bearer secret. Returns (new_raw_secret, new_hash)."""
    new_secret = generate_secret()
    new_hash = _secret_hash(new_secret)
    now = int(time.time())
    conn.execute(
        "UPDATE webhook_triggers SET secret_hash = ?, updated_at = ? WHERE id = ?",
        (new_hash, now, trigger_id),
    )
    conn.commit()
    return new_secret, new_hash


# ---------------------------------------------------------------------------
# Attempt logging
# ---------------------------------------------------------------------------

def log_attempt(
    conn: sqlite3.Connection,
    *,
    webhook_id: str,
    outcome: Outcome,
    status_code: int,
    event_name: str | None = None,
    preview: str | None = None,
    task_id: str | None = None,
    reason: str | None = None,
) -> WebhookAttempt:
    attempt = WebhookAttempt(
        id=str(uuid.uuid4()),
        webhook_id=webhook_id,
        received_at=int(time.time()),
        outcome=outcome,
        status_code=status_code,
        event_name=event_name,
        preview=preview,
        task_id=task_id,
        reason=reason,
    )
    conn.execute(
        """
        INSERT INTO webhook_attempts
            (id, webhook_id, received_at, outcome, status_code,
             event_name, preview, task_id, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attempt.id,
            attempt.webhook_id,
            attempt.received_at,
            attempt.outcome,
            attempt.status_code,
            attempt.event_name,
            attempt.preview,
            attempt.task_id,
            attempt.reason,
        ),
    )
    conn.commit()
    return attempt


def list_attempts(
    conn: sqlite3.Connection, webhook_id: str, limit: int = 50
) -> list[WebhookAttempt]:
    rows = conn.execute(
        """
        SELECT * FROM webhook_attempts
        WHERE webhook_id = ?
        ORDER BY received_at DESC
        LIMIT ?
        """,
        (webhook_id, limit),
    ).fetchall()
    return [
        WebhookAttempt(
            id=r["id"],
            webhook_id=r["webhook_id"],
            received_at=r["received_at"],
            outcome=r["outcome"],
            status_code=r["status_code"],
            event_name=r["event_name"],
            preview=r["preview"],
            task_id=r["task_id"],
            reason=r["reason"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Dedup receipts
# ---------------------------------------------------------------------------

def is_duplicate(
    conn: sqlite3.Connection, delivery_id: str, webhook_id: str
) -> bool:
    """Return True if this (delivery_id, webhook_id) pair was already processed."""
    row = conn.execute(
        "SELECT 1 FROM webhook_delivery_receipts WHERE key = ? AND webhook_id = ?",
        (delivery_id, webhook_id),
    ).fetchone()
    return row is not None


def record_receipt(
    conn: sqlite3.Connection,
    delivery_id: str,
    webhook_id: str,
    task_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO webhook_delivery_receipts (key, webhook_id, task_id, at)
        VALUES (?, ?, ?, ?)
        """,
        (delivery_id, webhook_id, task_id, int(time.time())),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def bump_delivery_count(
    conn: sqlite3.Connection, trigger_id: str, run_id: str | None = None
) -> None:
    now = int(time.time())
    conn.execute(
        """
        UPDATE webhook_triggers
        SET delivery_count = delivery_count + 1,
            last_received_at = ?,
            last_run_id = COALESCE(?, last_run_id),
            updated_at = ?
        WHERE id = ?
        """,
        (now, run_id, now, trigger_id),
    )
    conn.commit()


def mark_verified(conn: sqlite3.Connection, trigger_id: str) -> None:
    now = int(time.time())
    conn.execute(
        """
        UPDATE webhook_triggers
        SET verification_pending = 0, verified_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, trigger_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Kanban task insertion
# ---------------------------------------------------------------------------

KANBAN_DB_PATH = Path(
    os.environ.get(
        "HERMES_KANBAN_DB",
        r"C:\Users\micha\AppData\Local\hermes\kanban\boards\carrier\kanban.db",
    )
)


def task_from_payload(payload: dict, event_type: str | None) -> str:
    """Extract a human-readable task description from the webhook payload."""
    if event_type in ("check_run", "workflow_run"):
        return (
            f"CI {payload.get('action', '?')}: "
            f"{payload.get('check_run', {}).get('name', '?')} — "
            f"{payload.get('repository', {}).get('full_name', '?')}"
        )
    if event_type == "peer_task":
        return payload.get("message", "Peer task (no message)")
    if event_type == "peer_registered":
        peer_id = payload.get("peer_id", "?")
        addr = payload.get("address", "?")
        return f"New peer registered: {peer_id} at {addr}"
    if event_type == "peer_left":
        peer_id = payload.get("peer_id", "?")
        return f"Peer left network: {peer_id}"
    return json.dumps(payload)[:200]


def create_kanban_task(
    *,
    title: str,
    body: str,
    assignee: str,
    kanban_db: Path | None = None,
) -> str:
    """
    Insert a kanban task directly into the carrier board's SQLite DB.
    Returns the new task_id (UUID4 string).
    """
    db_path = kanban_db or KANBAN_DB_PATH
    task_id = "t_" + uuid.uuid4().hex[:8]
    now = int(time.time())

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, body, assignee, status,
                priority, created_by, created_at,
                workspace_kind, workspace_path,
                max_retries
            ) VALUES (?, ?, ?, ?, 'ready', 2, 'webhook_receiver', ?, 'scratch', NULL, 2)
            """,
            (task_id, title, body, assignee, now),
        )
        conn.commit()

    return task_id


# ---------------------------------------------------------------------------
# Row deserializer
# ---------------------------------------------------------------------------

def _row_to_trigger(row: sqlite3.Row) -> WebhookTrigger:
    return WebhookTrigger(
        id=row["id"],
        endpoint_id=row["endpoint_id"],
        secret_hash=row["secret_hash"],
        name=row["name"],
        prompt=row["prompt"],
        bot_id=row["bot_id"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_received_at=row["last_received_at"],
        last_run_id=row["last_run_id"],
        delivery_count=row["delivery_count"],
        verification_pending=bool(row["verification_pending"]),
        verified_at=row["verified_at"],
        event_types=json.loads(row["event_types"] or "[]"),
    )


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    print("webhook_db self-test...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = Path(f.name)

    conn = open_db(tmp)

    trigger, secret = create_trigger(
        conn,
        name="Test hook",
        bot_id="ops_lt",
        event_types=["push", "pull_request"],
    )
    print(f"  Created trigger {trigger.id[:8]}… endpoint={trigger.endpoint_id}")
    print(f"  Secret: {secret[:12]}…")

    ok = verify_bearer(secret, trigger.secret_hash)
    print(f"  Auth verify: {ok}")
    assert ok

    t2 = get_trigger_by_endpoint(conn, trigger.endpoint_id)
    assert t2 is not None
    print(f"  Lookup by endpoint: {t2.name}")

    attempt = log_attempt(
        conn,
        webhook_id=trigger.id,
        outcome="accepted",
        status_code=202,
        event_name="push",
        preview='{"ref": "refs/heads/main"}',
        task_id="t_abc123",
    )
    print(f"  Logged attempt {attempt.id[:8]}…")

    assert not is_duplicate(conn, "del-001", trigger.id)
    record_receipt(conn, "del-001", trigger.id, "t_abc123")
    assert is_duplicate(conn, "del-001", trigger.id)
    print("  Dedup: OK")

    new_secret, _ = rotate_secret(conn, trigger.id)
    print(f"  Rotated secret: {new_secret[:12]}…")

    conn.close()
    tmp.unlink()
    print("Self-test PASSED.")

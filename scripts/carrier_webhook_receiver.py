"""
carrier_webhook_receiver.py — HTTP webhook receiver for carrier fleet events.

Inspired by OpenMausBot's webhooks.ts: accepts inbound events from GitHub,
calendar, and manual triggers, deduplicates them, and inserts ready tasks
into the carrier Kanban DB.

Usage:
    python scripts/carrier_webhook_receiver.py          # starts on port 8800
    CARRIER_WEBHOOK_PORT=9000 python scripts/carrier_webhook_receiver.py

Test:
    python scripts/test_carrier_webhook.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "C:/Users/micha/AppData/Local/hermes"))
CARRIER_DIR = HERMES_HOME / "carrier"
CARRIER_DIR.mkdir(parents=True, exist_ok=True)

WEBHOOKS_DB = CARRIER_DIR / "webhooks.db"
KANBAN_DB = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"

PORT = int(os.environ.get("CARRIER_WEBHOOK_PORT", "8800"))
DEDUP_WINDOW_HOURS = 24

# ── Supported event types ──────────────────────────────────────────────────────
SUPPORTED_EVENT_TYPES = frozenset([
    "github_pr_opened",
    "github_push",
    "calendar_event",
    "manual_trigger",
])

# ── DB init ────────────────────────────────────────────────────────────────────

def _init_webhooks_db() -> None:
    with sqlite3.connect(str(WEBHOOKS_DB)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                dedup_id    TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                received_at TEXT NOT NULL,
                task_id     TEXT
            )
        """)
        conn.commit()


def _init_kanban_db() -> None:
    """Ensure the Kanban DB exists and is accessible."""
    if not KANBAN_DB.exists():
        raise RuntimeError(
            f"Kanban DB not found: {KANBAN_DB}. "
            "Ensure carrier Kanban board is initialized before starting the webhook receiver."
        )


_init_webhooks_db()

# ── Dedup helpers ──────────────────────────────────────────────────────────────

def _is_duplicate(dedup_id: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)).isoformat()
    with sqlite3.connect(str(WEBHOOKS_DB)) as conn:
        row = conn.execute(
            "SELECT dedup_id FROM webhook_deliveries WHERE dedup_id = ? AND received_at > ?",
            (dedup_id, cutoff),
        ).fetchone()
    return row is not None


def _record_delivery(dedup_id: str, event_type: str, task_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(WEBHOOKS_DB)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO webhook_deliveries (dedup_id, event_type, received_at, task_id) VALUES (?, ?, ?, ?)",
            (dedup_id, event_type, now, task_id),
        )
        conn.commit()


# ── Kanban insertion ───────────────────────────────────────────────────────────

def _build_task_body(event_type: str, payload: dict) -> str:
    lines = [f"**Webhook event:** `{event_type}`", ""]
    if event_type == "github_pr_opened":
        lines += [
            f"**PR:** {payload.get('pr_title', '(unknown)')}",
            f"**Repo:** {payload.get('repo', '(unknown)')}",
            f"**URL:** {payload.get('pr_url', '')}",
        ]
    elif event_type == "github_push":
        lines += [
            f"**Branch:** {payload.get('branch', '(unknown)')}",
            f"**Pusher:** {payload.get('pusher', '(unknown)')}",
            f"**Commits:** {payload.get('commits', 0)}",
        ]
    elif event_type == "calendar_event":
        lines += [
            f"**Event:** {payload.get('event_title', '(unknown)')}",
            f"**Time:** {payload.get('event_time', '(unknown)')}",
        ]
    elif event_type == "manual_trigger":
        lines += [f"**Triggered by:** {payload.get('triggered_by', '(unknown)')}"]
    lines += ["", f"Raw payload:\n```json\n{json.dumps(payload, indent=2)[:800]}\n```"]
    return "\n".join(lines)


def _insert_kanban_task(
    event_type: str,
    target_bot_id: str,
    task_description: str,
    payload: dict,
) -> str:
    """Insert a ready task into the carrier Kanban DB and return the task ID."""
    task_id = str(uuid.uuid4())
    now_ts = int(time.time())
    body = _build_task_body(event_type, payload)

    with sqlite3.connect(str(KANBAN_DB)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO tasks
                (id, title, body, assignee, status, priority, created_by,
                 created_at, workspace_kind, workspace_path, branch_name)
            VALUES (?, ?, ?, ?, 'ready', 50, 'webhook_receiver', ?, 'scratch', NULL, NULL)
            """,
            (task_id, task_description[:200], body, target_bot_id, now_ts),
        )
        conn.commit()

    print(f"[webhook_receiver] Inserted Kanban task {task_id} for bot={target_bot_id}")
    return task_id


# ── Webhook secret validation ──────────────────────────────────────────────────

def _validate_secret(provided: str) -> bool:
    expected = os.environ.get("CARRIER_WEBHOOK_SECRET", "")
    if not expected:
        print("[webhook_receiver] WARNING: CARRIER_WEBHOOK_SECRET not set — accepting all requests!")
        return True
    import hmac
    return hmac.compare_digest(provided.encode(), expected.encode())


# ── HTTP handler ───────────────────────────────────────────────────────────────

class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[webhook_receiver] {self.address_string()} - {format % args}")

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {
                "status": "ok",
                "webhooks_db": str(WEBHOOKS_DB),
                "kanban_db": str(KANBAN_DB),
                "kanban_exists": KANBAN_DB.exists(),
                "supported_event_types": sorted(SUPPORTED_EVENT_TYPES),
                "port": PORT,
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._send_json(404, {"error": "not found"})
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc}"})
            return

        # Extract fields
        event_type = body.get("event_type", "")
        target_bot_id = body.get("target_bot_id", "")
        task_description = body.get("task_description", "")
        dedup_id = body.get("dedup_id", "")
        secret = body.get("secret", "")

        # Validate secret
        if not _validate_secret(secret):
            self._send_json(401, {"error": "invalid secret"})
            return

        # Validate required fields
        missing = [f for f in ("event_type", "target_bot_id", "task_description", "dedup_id") if not body.get(f)]
        if missing:
            self._send_json(400, {"error": f"missing required fields: {missing}"})
            return

        # Validate event_type
        if event_type not in SUPPORTED_EVENT_TYPES:
            self._send_json(400, {
                "error": f"unsupported event_type '{event_type}'",
                "supported": sorted(SUPPORTED_EVENT_TYPES),
            })
            return

        # Dedup check
        if _is_duplicate(dedup_id):
            self._send_json(200, {
                "status": "duplicate",
                "dedup_id": dedup_id,
                "message": "Already processed within 24h window",
            })
            return

        # Insert Kanban task
        try:
            task_id = _insert_kanban_task(
                event_type, target_bot_id, task_description, body
            )
        except Exception as exc:
            print(f"[webhook_receiver] Kanban insert failed: {exc}")
            self._send_json(500, {"error": f"kanban insert failed: {exc}"})
            return

        # Record dedup
        _record_delivery(dedup_id, event_type, task_id)

        self._send_json(202, {
            "status": "accepted",
            "task_id": task_id,
            "event_type": event_type,
            "target_bot_id": target_bot_id,
            "dedup_id": dedup_id,
        })


# ── Server start ───────────────────────────────────────────────────────────────

def start_server(port: int = PORT, block: bool = True) -> HTTPServer:
    _init_webhooks_db()
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"[webhook_receiver] Listening on http://0.0.0.0:{port}")
    print(f"[webhook_receiver] POST /webhook  GET /health")
    print(f"[webhook_receiver] Kanban DB: {KANBAN_DB}")
    if block:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[webhook_receiver] Shutting down...")
            server.shutdown()
    else:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
    return server


if __name__ == "__main__":
    start_server()

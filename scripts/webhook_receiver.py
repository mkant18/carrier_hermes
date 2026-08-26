"""
webhook_receiver.py — Carrier Hermes webhook receiver service.

Port : 8800  (override with CARRIER_WEBHOOK_PORT env var)
Auth : Bearer token (recommended) or capability URL fallback
Dedup: X-Delivery-ID header prevents double-dispatch on retries

Endpoints:
  GET  /health
      Returns {"status":"ok","triggers":N}

  POST /hooks/<endpoint_id>
      Main inbound webhook. Validates auth, deduplicates, creates kanban task.
      Returns 202 {"status":"queued","task_id":"t_..."} on accept.
      Returns 4xx on reject/ignore.
      Returns 202 {"status":"duplicate"} on retried deliveries.

  POST /hooks/<endpoint_id>/<secret>
      Capability URL fallback — secret in path for senders that can't set headers.
      Lower security (appears in access logs). Documented as such.

Run standalone:
  python webhook_receiver.py

Or via NSSM service: carrier-webhook-receiver
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

# Prefer Flask (lighter); fall back to a note about missing dep.
try:
    from flask import Flask, Response, request, jsonify
    _HAVE_FLASK = True
except ImportError:
    _HAVE_FLASK = False

# Add scripts dir to path so webhook_db can be imported
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import webhook_db as wdb

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [webhook_receiver] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("webhook_receiver")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("CARRIER_WEBHOOK_PORT", "8800"))
HOST = os.environ.get("CARRIER_WEBHOOK_HOST", "127.0.0.1")

# ---------------------------------------------------------------------------
# DB connection (module-level, reused across requests)
# ---------------------------------------------------------------------------

_db_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = wdb.open_db()
        log.info("Opened webhooks DB at %s", wdb.get_db_path())
    return _db_conn


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def extract_event_name(req) -> str | None:
    """Extract event type from common headers (GitHub, generic)."""
    for hdr in ("X-GitHub-Event", "X-Event-Type", "X-Webhook-Event"):
        val = req.headers.get(hdr)
        if val:
            return val.strip().lower()
    return None


def extract_delivery_id(req) -> str | None:
    """Extract idempotency key from X-Delivery-ID or X-GitHub-Delivery."""
    for hdr in ("X-Delivery-ID", "X-GitHub-Delivery", "X-Request-ID"):
        val = req.headers.get(hdr)
        if val:
            return val.strip()
    return None


def build_task_body(
    trigger: wdb.WebhookTrigger,
    payload: dict,
    event_type: str | None,
) -> str:
    """Build the kanban task body from trigger config and inbound payload."""
    if trigger.prompt:
        # Static routine pattern — use the pre-set prompt verbatim
        description = trigger.prompt
    else:
        description = wdb.task_from_payload(payload, event_type)

    # Append full payload as code block for bot context
    payload_block = json.dumps(payload, indent=2)
    return (
        f"{description}\n\n"
        f"**Webhook trigger:** `{trigger.name}` (`{trigger.endpoint_id}`)\n"
        f"**Event type:** `{event_type or 'unspecified'}`\n\n"
        f"```json\n{payload_block}\n```"
    )


# ---------------------------------------------------------------------------
# Core processing logic (transport-agnostic)
# ---------------------------------------------------------------------------

def process_webhook(
    *,
    endpoint_id: str,
    bearer_token: str | None,
    payload: dict,
    event_type: str | None,
    delivery_id: str | None,
    preview: str,
) -> tuple[dict, int]:
    """
    Core webhook processing. Returns (response_body_dict, http_status_code).

    Outcome semantics (from OpenMausBot spec):
      accepted  — Task created, 202
      captured  — Trigger disabled / verification pending, 202
      duplicate — delivery_id already seen, 202
      ignored   — event_type not in allowlist, 400
      rejected  — Bad auth or missing trigger, 401/404
    """
    conn = get_conn()

    # 1. Look up trigger
    trigger = wdb.get_trigger_by_endpoint(conn, endpoint_id)
    if trigger is None:
        log.warning("No trigger found for endpoint_id=%s", endpoint_id)
        wdb.log_attempt(
            conn,
            webhook_id="unknown",
            outcome="rejected",
            status_code=404,
            event_name=event_type,
            preview=preview,
            reason="endpoint_id not registered",
        )
        return {"error": "not found"}, 404

    # 2. Validate bearer token
    if bearer_token is None or not wdb.verify_bearer(bearer_token, trigger.secret_hash):
        log.warning(
            "Auth failure for endpoint_id=%s bearer_present=%s",
            endpoint_id,
            bearer_token is not None,
        )
        wdb.log_attempt(
            conn,
            webhook_id=trigger.id,
            outcome="rejected",
            status_code=401,
            event_name=event_type,
            preview=preview,
            reason="invalid or missing bearer token",
        )
        return {"error": "unauthorized"}, 401

    # 3. Verification flow — first authenticated request flips verification_pending
    was_pending = trigger.verification_pending
    if was_pending:
        wdb.mark_verified(conn, trigger.id)
        # Refresh trigger object
        trigger = wdb.get_trigger_by_endpoint(conn, endpoint_id)
        log.info("Trigger %s (%s) verified by first authenticated request", trigger.id[:8], trigger.name)

    # 4. Deduplication
    if delivery_id and wdb.is_duplicate(conn, delivery_id, trigger.id):
        log.info("Duplicate delivery_id=%s for trigger=%s", delivery_id[:16], trigger.id[:8])
        wdb.log_attempt(
            conn,
            webhook_id=trigger.id,
            outcome="duplicate",
            status_code=202,
            event_name=event_type,
            preview=preview,
            reason=f"delivery_id {delivery_id} already processed",
        )
        return {"status": "duplicate"}, 202

    # 5. Event type allowlist (if configured)
    if trigger.event_types and event_type not in trigger.event_types:
        log.info(
            "Ignored event_type=%s for trigger=%s (allowlist=%s)",
            event_type, trigger.id[:8], trigger.event_types,
        )
        wdb.log_attempt(
            conn,
            webhook_id=trigger.id,
            outcome="ignored",
            status_code=400,
            event_name=event_type,
            preview=preview,
            reason=f"event_type '{event_type}' not in allowlist {trigger.event_types}",
        )
        return {"error": "event_type not in allowlist"}, 400

    # 6. Disabled trigger or still pending (shouldn't happen — mark_verified above clears it, but guard)
    if not trigger.enabled or trigger.verification_pending:
        log.info(
            "Captured (trigger disabled or still pending): trigger=%s enabled=%s pending=%s",
            trigger.id[:8], trigger.enabled, trigger.verification_pending,
        )
        wdb.bump_delivery_count(conn, trigger.id)
        wdb.log_attempt(
            conn,
            webhook_id=trigger.id,
            outcome="captured",
            status_code=202,
            event_name=event_type,
            preview=preview,
            reason="trigger disabled" if not trigger.enabled else "verification still pending",
        )
        return {"status": "captured"}, 202

    # 7. Create kanban task
    title = wdb.task_from_payload(payload, event_type)
    body = build_task_body(trigger, payload, event_type)

    try:
        task_id = wdb.create_kanban_task(
            title=f"[webhook] {title}"[:200],
            body=body,
            assignee=trigger.bot_id,
        )
    except Exception as exc:
        log.exception("Failed to create kanban task: %s", exc)
        wdb.log_attempt(
            conn,
            webhook_id=trigger.id,
            outcome="rejected",
            status_code=500,
            event_name=event_type,
            preview=preview,
            reason=f"kanban insert error: {exc}",
        )
        return {"error": "internal error creating task"}, 500

    # 8. Record receipt and bump stats
    if delivery_id:
        wdb.record_receipt(conn, delivery_id, trigger.id, task_id)
    wdb.bump_delivery_count(conn, trigger.id, run_id=task_id)

    wdb.log_attempt(
        conn,
        webhook_id=trigger.id,
        outcome="accepted",
        status_code=202,
        event_name=event_type,
        preview=preview,
        task_id=task_id,
    )

    log.info(
        "Accepted: trigger=%s event=%s task=%s assignee=%s",
        trigger.id[:8], event_type, task_id, trigger.bot_id,
    )

    return {"status": "queued", "task_id": task_id}, 202


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

if _HAVE_FLASK:
    app = Flask("webhook_receiver")

    @app.route("/health", methods=["GET"])
    def health():
        conn = get_conn()
        triggers = conn.execute(
            "SELECT COUNT(*) FROM webhook_triggers WHERE enabled = 1"
        ).fetchone()[0]
        return jsonify({"status": "ok", "triggers": triggers})

    @app.route("/hooks/<endpoint_id>", methods=["POST"])
    def receive_hook(endpoint_id: str):
        return _handle_request(endpoint_id, bearer_from_path=None)

    @app.route("/hooks/<endpoint_id>/<path:secret_in_path>", methods=["POST"])
    def receive_hook_capability_url(endpoint_id: str, secret_in_path: str):
        """
        Capability URL fallback. Secret in URL path for senders that cannot
        set Authorization headers (some CI systems, IoT devices, etc.).
        Lower security — secret appears in server access logs.
        """
        return _handle_request(endpoint_id, bearer_from_path=secret_in_path)

    def _handle_request(endpoint_id: str, bearer_from_path: str | None) -> Response:
        # Parse bearer from Authorization header (preferred)
        auth_hdr = request.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            bearer = auth_hdr[7:].strip()
        elif bearer_from_path:
            bearer = bearer_from_path
        else:
            bearer = None

        # Parse JSON body
        try:
            payload = request.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}

        event_type = extract_event_name(request)
        delivery_id = extract_delivery_id(request)
        raw_body = request.get_data(as_text=True)
        preview = raw_body[:200] if raw_body else ""

        body_dict, status = process_webhook(
            endpoint_id=endpoint_id,
            bearer_token=bearer,
            payload=payload,
            event_type=event_type,
            delivery_id=delivery_id,
            preview=preview,
        )
        return jsonify(body_dict), status


# ---------------------------------------------------------------------------
# Minimal WSGI-free fallback (http.server) for zero-dependency operation
# ---------------------------------------------------------------------------

import http.server
import threading
import urllib.parse


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP/1.1 handler — used only when Flask is unavailable."""

    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def _send_json(self, body: dict, status: int = 200) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            conn = get_conn()
            triggers = conn.execute(
                "SELECT COUNT(*) FROM webhook_triggers WHERE enabled = 1"
            ).fetchone()[0]
            self._send_json({"status": "ok", "triggers": triggers})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        if len(parts) < 2 or parts[0] != "hooks":
            self._send_json({"error": "not found"}, 404)
            return

        endpoint_id = parts[1]
        bearer_from_path = parts[2] if len(parts) >= 3 else None

        auth_hdr = self.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            bearer = auth_hdr[7:].strip()
        elif bearer_from_path:
            bearer = bearer_from_path
        else:
            bearer = None

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8", errors="replace") if content_length else ""

        try:
            payload = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            payload = {}

        # Reconstruct a request-like object for header extraction
        class _FakeReq:
            headers = self.headers
        event_type = extract_event_name(_FakeReq())
        delivery_id = extract_delivery_id(_FakeReq())

        body_dict, status = process_webhook(
            endpoint_id=endpoint_id,
            bearer_token=bearer,
            payload=payload,
            event_type=event_type,
            delivery_id=delivery_id,
            preview=raw_body[:200],
        )
        self._send_json(body_dict, status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not _HAVE_FLASK:
        log.warning(
            "Flask not installed. Falling back to http.server (no keep-alive, single-threaded). "
            "Install Flask for production: pip install flask"
        )

    log.info("Starting carrier webhook receiver on %s:%d", HOST, PORT)

    if _HAVE_FLASK:
        # Flask dev server — for production, use gunicorn or waitress
        # e.g.:  waitress-serve --host 127.0.0.1 --port 8800 webhook_receiver:app
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)
    else:
        server = http.server.HTTPServer((HOST, PORT), _WebhookHandler)
        log.info("Listening (stdlib http.server)…")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("Shutdown requested.")
            server.shutdown()


if __name__ == "__main__":
    main()

"""
peers_broker.py — Carrier Hermes Wave 1 peers broker.

Port : 9876  (override with CARRIER_PEERS_PORT env var)

The peers broker is a lightweight HTTP server that lets carrier fleets discover
each other, exchange messages, and forward peer events to the local webhook
receiver for kanban task dispatch.

Endpoints:
  GET  /health
      {"status":"ok","peers":N}

  POST /peers/register
      Register a remote peer fleet.
      Body: {"peer_id":"carrier_alpha","address":"10.0.0.5:9876","capabilities":["fleet_orchestration"]}
      Returns 200 {"status":"registered"}

  DELETE /peers/<peer_id>
      Deregister a peer.
      Returns 200 {"status":"removed"}

  GET  /peers
      List all known peers.
      Returns {"peers":[...]}

  POST /peers/<peer_id>/message
      Send a message to a specific bot on a peer fleet (routed locally if peer_id is "self").
      Body: {"to_bot":"ops_lt","message":"..."}
      Returns 202 {"status":"forwarded"} or 200 {"status":"dispatched"} if local

  POST /webhook-forward
      Forward peer lifecycle events to the local webhook receiver.
      Body: {"event_type":"peer_registered","payload":{...}}
      Returns 202 from webhook receiver or error passthrough.
      Auth: shared local secret from ~/.hermes/carrier/webhook_local_secret

Run standalone:
  python peers_broker.py

Or via NSSM service: carrier-peers-broker
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import sqlite3
import sys
import time
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [peers_broker] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("peers_broker")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("CARRIER_PEERS_PORT", "9876"))
HOST = os.environ.get("CARRIER_PEERS_HOST", "127.0.0.1")

WEBHOOK_HOST = os.environ.get("CARRIER_WEBHOOK_HOST", "127.0.0.1")
WEBHOOK_PORT = int(os.environ.get("CARRIER_WEBHOOK_PORT", "8800"))
WEBHOOK_BASE = f"http://{WEBHOOK_HOST}:{WEBHOOK_PORT}"

LOCAL_SECRET_PATH = Path(
    os.environ.get(
        "CARRIER_WEBHOOK_LOCAL_SECRET",
        r"C:\Users\micha\AppData\Local\hermes\carrier\webhook_local_secret",
    )
)

# Peers broker event → webhook event_type → assignee bot mapping (from spec)
PEER_EVENT_MAP: dict[str, tuple[str, str]] = {
    "peer_registered": ("peer_registered", "ops_lt"),
    "peer_message":    ("peer_task",        ""),     # assignee determined by payload.to_bot
    "peer_left":       ("peer_left",        "passive_watch"),
}

# ---------------------------------------------------------------------------
# In-memory peer registry (no persistence requirement for Wave 1)
# ---------------------------------------------------------------------------

_peers_lock = threading.Lock()
_peers: dict[str, dict[str, Any]] = {}  # peer_id -> peer record


def _get_peers() -> list[dict]:
    with _peers_lock:
        return list(_peers.values())


def _register_peer(peer_id: str, address: str, capabilities: list[str]) -> dict:
    now = int(time.time())
    with _peers_lock:
        existing = _peers.get(peer_id)
        record = {
            "peer_id": peer_id,
            "address": address,
            "capabilities": capabilities,
            "registered_at": existing["registered_at"] if existing else now,
            "last_seen_at": now,
        }
        _peers[peer_id] = record
    return record


def _remove_peer(peer_id: str) -> bool:
    with _peers_lock:
        return _peers.pop(peer_id, None) is not None


# ---------------------------------------------------------------------------
# Local secret management
# ---------------------------------------------------------------------------

def _load_or_create_local_secret() -> str:
    """Load the shared local secret used for broker→receiver auth. Create if absent."""
    import secrets as _secrets
    if LOCAL_SECRET_PATH.exists():
        return LOCAL_SECRET_PATH.read_text(encoding="utf-8").strip()
    LOCAL_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    token = _secrets.token_urlsafe(32)
    LOCAL_SECRET_PATH.write_text(token, encoding="utf-8")
    log.info("Generated new webhook local secret at %s", LOCAL_SECRET_PATH)
    return token


_LOCAL_SECRET: str | None = None


def local_secret() -> str:
    global _LOCAL_SECRET
    if _LOCAL_SECRET is None:
        _LOCAL_SECRET = _load_or_create_local_secret()
    return _LOCAL_SECRET


# ---------------------------------------------------------------------------
# Webhook forwarding
# ---------------------------------------------------------------------------

# Endpoint IDs for each peer event type (registered at startup if not already present).
# The broker uses its local secret to call the webhook receiver's known endpoint IDs.
# These are named endpoints that the webhook receiver must have registered.

PEER_WEBHOOK_ENDPOINT_MAP = {
    "peer_registered": "peer-registered",
    "peer_task":       "peer-task",
    "peer_left":       "peer-left",
}


def forward_to_webhook(event_type: str, payload: dict) -> tuple[dict, int]:
    """
    Forward a peer event to the local webhook receiver.
    Uses the local shared secret for auth.
    Returns (response_body, status_code).
    """
    # Map broker event names to webhook event_types
    webhook_event = PEER_EVENT_MAP.get(event_type)
    if webhook_event is None:
        log.warning("No webhook mapping for event_type=%s", event_type)
        return {"error": f"unknown event_type '{event_type}'"}, 400

    wh_event_type, default_bot = webhook_event

    # For peer_message, bot comes from payload.to_bot
    if event_type == "peer_message":
        default_bot = payload.get("to_bot", "ops_lt")

    endpoint_id = PEER_WEBHOOK_ENDPOINT_MAP.get(wh_event_type, wh_event_type)
    url = f"{WEBHOOK_BASE}/hooks/{endpoint_id}"
    delivery_id = f"broker-{uuid.uuid4().hex[:12]}"

    body = json.dumps({
        "event_type": wh_event_type,
        "default_bot": default_bot,
        **payload,
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {local_secret()}",
            "Content-Type": "application/json",
            "X-Event-Type": wh_event_type,
            "X-Delivery-ID": delivery_id,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = json.loads(resp.read().decode())
            log.info(
                "Forwarded %s → webhook %s → %d %s",
                event_type, url, resp.status, resp_body.get("status", ""),
            )
            return resp_body, resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        log.warning("Webhook forward failed: %d %s", e.code, err_body[:200])
        try:
            return json.loads(err_body), e.code
        except Exception:
            return {"error": err_body[:200]}, e.code
    except urllib.error.URLError as e:
        log.error("Webhook receiver unreachable: %s", e.reason)
        return {"error": f"webhook receiver unavailable: {e.reason}"}, 503


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _BrokerHandler(http.server.BaseHTTPRequestHandler):
    """Single-threaded HTTP handler for the peers broker."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log.debug(format, *args)

    def _send_json(self, body: dict, status: int = 200) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"status": "ok", "peers": len(_peers)})
        elif self.path == "/peers":
            self._send_json({"peers": _get_peers()})
        else:
            self._send_json({"error": "not found"}, 404)

    # ── DELETE ───────────────────────────────────────────────────────────────

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "peers":
            peer_id = parts[1]
            removed = _remove_peer(peer_id)
            if removed:
                # Forward peer_left event to webhook receiver
                threading.Thread(
                    target=forward_to_webhook,
                    args=("peer_left", {"peer_id": peer_id}),
                    daemon=True,
                ).start()
                self._send_json({"status": "removed"})
            else:
                self._send_json({"error": f"peer '{peer_id}' not found"}, 404)
        else:
            self._send_json({"error": "not found"}, 404)

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        parts = self.path.strip("/").split("/")

        # POST /peers/register
        if parts == ["peers", "register"]:
            self._handle_register()

        # POST /peers/<peer_id>/message
        elif len(parts) == 3 and parts[0] == "peers" and parts[2] == "message":
            self._handle_message(parts[1])

        # POST /webhook-forward
        elif parts == ["webhook-forward"]:
            self._handle_webhook_forward()

        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_register(self) -> None:
        body = self._read_body()
        peer_id = body.get("peer_id", "").strip()
        address = body.get("address", "").strip()
        capabilities = body.get("capabilities", [])

        if not peer_id or not address:
            self._send_json({"error": "peer_id and address are required"}, 400)
            return

        record = _register_peer(peer_id, address, capabilities)
        log.info("Registered peer: %s at %s caps=%s", peer_id, address, capabilities)

        # Forward peer_registered event to webhook receiver (async)
        threading.Thread(
            target=forward_to_webhook,
            args=("peer_registered", {"peer_id": peer_id, "address": address, "capabilities": capabilities}),
            daemon=True,
        ).start()

        self._send_json({"status": "registered", "peer": record})

    def _handle_message(self, peer_id: str) -> None:
        body = self._read_body()
        to_bot = body.get("to_bot", "").strip()
        message = body.get("message", "").strip()

        if not to_bot:
            self._send_json({"error": "to_bot is required"}, 400)
            return

        log.info("Message from peer %s to bot %s: %s", peer_id, to_bot, message[:80])

        # Forward peer_message → webhook for kanban task dispatch
        threading.Thread(
            target=forward_to_webhook,
            args=("peer_message", {
                "from_peer": peer_id,
                "to_bot": to_bot,
                "message": message,
            }),
            daemon=True,
        ).start()

        self._send_json({"status": "forwarded"}, 202)

    def _handle_webhook_forward(self) -> None:
        """
        POST /webhook-forward — Internal endpoint for direct broker→receiver forwarding.
        Accepts {"event_type":"peer_registered","payload":{...}}
        """
        body = self._read_body()
        event_type = body.get("event_type", "").strip()
        payload = body.get("payload", {})

        if not event_type:
            self._send_json({"error": "event_type is required"}, 400)
            return

        resp_body, status = forward_to_webhook(event_type, payload)
        self._send_json(resp_body, status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Starting carrier peers broker on %s:%d", HOST, PORT)
    log.info("Webhook receiver target: %s", WEBHOOK_BASE)
    log.info("Local secret path: %s", LOCAL_SECRET_PATH)

    # Pre-load/create local secret at startup
    _ = local_secret()

    server = http.server.ThreadingHTTPServer((HOST, PORT), _BrokerHandler)
    log.info("Listening (ThreadingHTTPServer)…")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown requested.")
        server.shutdown()


if __name__ == "__main__":
    main()

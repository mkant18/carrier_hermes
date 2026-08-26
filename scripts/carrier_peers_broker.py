#!/usr/bin/env python3
"""
carrier_peers_broker.py -- Lightweight peer discovery and messaging broker.
Provider-agnostic: works with any Hermes session, not just Claude Code.

Adapted from the broker pattern in claude-peers-go (WillyV3) but reimplemented
in Python stdlib with no external dependencies.

Usage:
    python scripts/carrier_peers_broker.py [--port 9876] [--host 127.0.0.1]

State persists in SQLite at: C:/Users/micha/AppData/Local/hermes/carrier/peers.db
"""
import argparse
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_PORT = 9876
DEFAULT_HOST = "127.0.0.1"
PEER_TTL_SECONDS = 90
DB_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local")),
    "hermes", "carrier", "peers.db"
)

# ── Thread-safe state ────────────────────────────────────────────────────────
_lock = threading.Lock()


# ── Database helpers ─────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    """Open (and initialize) the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS peers (
            session_id    TEXT PRIMARY KEY,
            bot_id        TEXT NOT NULL,
            profile_name  TEXT NOT NULL DEFAULT '',
            current_task  TEXT NOT NULL DEFAULT '',
            started_at    REAL NOT NULL,
            capabilities  TEXT NOT NULL DEFAULT '[]',
            last_heartbeat REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            to_session_id TEXT NOT NULL,
            from_session  TEXT NOT NULL,
            content       TEXT NOT NULL,
            created_at    REAL NOT NULL
        );
    """)
    conn.commit()
    return conn


# Singleton connection (thread-safe with the lock)
_db: sqlite3.Connection | None = None

def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _get_db()
    return _db


# ── Request handler ───────────────────────────────────────────────────────────

class PeerBrokerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        # Quiet logging -- only errors to stderr
        if args and str(args[1]) >= "400":
            super().log_message(format, *args)

    def _parse_query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def _query_param(self, key: str) -> str | None:
        params = self._parse_query()
        vals = params.get(key, [])
        return vals[0] if vals else None

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _send_json(self, status: int, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": message})

    # ── Route dispatcher ──────────────────────────────────────────────────────

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/peers":
            self._handle_list_peers()
        elif path == "/messages":
            self._handle_get_messages()
        elif path == "/health":
            self._handle_health()
        else:
            self._send_error(404, "not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/register":
            self._handle_register()
        elif path == "/heartbeat":
            self._handle_heartbeat()
        elif path == "/message":
            self._handle_post_message()
        else:
            self._send_error(404, "not found")

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/register":
            self._handle_unregister()
        else:
            self._send_error(404, "not found")

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_register(self):
        body = self._read_json_body()
        session_id = body.get("session_id", "").strip()
        bot_id = body.get("bot_id", "").strip()
        if not session_id or not bot_id:
            return self._send_error(400, "session_id and bot_id are required")

        profile_name = body.get("profile_name", "")
        current_task = body.get("current_task", "")
        started_at = body.get("started_at", time.time())
        capabilities = json.dumps(body.get("capabilities", []))
        now = time.time()

        with _lock:
            db = get_db()
            db.execute("""
                INSERT INTO peers (session_id, bot_id, profile_name, current_task,
                                   started_at, capabilities, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    bot_id=excluded.bot_id,
                    profile_name=excluded.profile_name,
                    current_task=excluded.current_task,
                    started_at=excluded.started_at,
                    capabilities=excluded.capabilities,
                    last_heartbeat=excluded.last_heartbeat
            """, (session_id, bot_id, profile_name, current_task, started_at, capabilities, now))
            db.commit()

        self._send_json(200, {"ok": True, "session_id": session_id})

    def _handle_unregister(self):
        session_id = self._query_param("session_id")
        if not session_id:
            return self._send_error(400, "session_id query param required")

        with _lock:
            db = get_db()
            db.execute("DELETE FROM peers WHERE session_id = ?", (session_id,))
            db.commit()

        self._send_json(200, {"ok": True})

    def _handle_heartbeat(self):
        session_id = self._query_param("session_id")
        if not session_id:
            return self._send_error(400, "session_id query param required")

        now = time.time()
        with _lock:
            db = get_db()
            cur = db.execute(
                "UPDATE peers SET last_heartbeat = ? WHERE session_id = ?",
                (now, session_id)
            )
            db.commit()
            found = cur.rowcount > 0

        if not found:
            return self._send_error(404, "session not found")
        self._send_json(200, {"ok": True})

    def _handle_list_peers(self):
        cutoff = time.time() - PEER_TTL_SECONDS
        with _lock:
            db = get_db()
            rows = db.execute(
                "SELECT * FROM peers WHERE last_heartbeat >= ? ORDER BY started_at ASC",
                (cutoff,)
            ).fetchall()

        peers = []
        for row in rows:
            peers.append({
                "session_id": row["session_id"],
                "bot_id": row["bot_id"],
                "profile_name": row["profile_name"],
                "current_task": row["current_task"],
                "started_at": row["started_at"],
                "capabilities": json.loads(row["capabilities"]),
                "last_heartbeat": row["last_heartbeat"],
            })
        self._send_json(200, {"peers": peers})

    def _handle_post_message(self):
        to_session_id = self._query_param("to_session_id")
        if not to_session_id:
            return self._send_error(400, "to_session_id query param required")

        body = self._read_json_body()
        from_session = body.get("from_session", "").strip()
        content = body.get("content", "").strip()
        if not from_session or not content:
            return self._send_error(400, "from_session and content are required")

        now = time.time()
        with _lock:
            db = get_db()
            # Verify destination exists (or was recently active)
            cutoff = now - PEER_TTL_SECONDS
            row = db.execute(
                "SELECT session_id FROM peers WHERE session_id = ? AND last_heartbeat >= ?",
                (to_session_id, cutoff)
            ).fetchone()
            if not row:
                return self._send_error(404, "destination session not found or expired")

            db.execute(
                "INSERT INTO messages (to_session_id, from_session, content, created_at) VALUES (?, ?, ?, ?)",
                (to_session_id, from_session, content, now)
            )
            db.commit()

        self._send_json(200, {"ok": True})

    def _handle_get_messages(self):
        session_id = self._query_param("session_id")
        if not session_id:
            return self._send_error(400, "session_id query param required")

        with _lock:
            db = get_db()
            rows = db.execute(
                "SELECT * FROM messages WHERE to_session_id = ? ORDER BY created_at ASC",
                (session_id,)
            ).fetchall()
            db.execute("DELETE FROM messages WHERE to_session_id = ?", (session_id,))
            db.commit()

        messages = [
            {
                "id": row["id"],
                "from_session": row["from_session"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        self._send_json(200, {"messages": messages})

    def _handle_health(self):
        cutoff = time.time() - PEER_TTL_SECONDS
        with _lock:
            db = get_db()
            count = db.execute(
                "SELECT COUNT(*) FROM peers WHERE last_heartbeat >= ?", (cutoff,)
            ).fetchone()[0]

        self._send_json(200, {"status": "ok", "peer_count": count})


# ── Expiry reaper ─────────────────────────────────────────────────────────────

def _reap_expired_peers(interval: int = 60):
    """Background thread: delete expired peer rows every `interval` seconds."""
    while True:
        time.sleep(interval)
        cutoff = time.time() - PEER_TTL_SECONDS
        try:
            with _lock:
                db = get_db()
                db.execute("DELETE FROM peers WHERE last_heartbeat < ?", (cutoff,))
                db.execute(
                    "DELETE FROM messages WHERE created_at < ?",
                    (time.time() - 3600,)   # clean messages older than 1h
                )
                db.commit()
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Carrier peers broker")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    # Initialise DB
    with _lock:
        get_db()

    # Start background reaper
    reaper = threading.Thread(target=_reap_expired_peers, daemon=True)
    reaper.start()

    server = HTTPServer((args.host, args.port), PeerBrokerHandler)
    print(f"[carrier_peers_broker] Listening on {args.host}:{args.port} | DB: {DB_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[carrier_peers_broker] Shutting down.", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()

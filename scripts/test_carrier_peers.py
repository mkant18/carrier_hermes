#!/usr/bin/env python3
"""
test_carrier_peers.py -- Integration test for the carrier peers broker + client.

Self-contained: starts the broker in a background thread, runs the full
register/message/unregister lifecycle, then prints PASS or FAIL.

Usage:
    python scripts/test_carrier_peers.py
"""
import json
import os
import sys
import threading
import time

# ── Allow importing broker/client from the same scripts/ directory ────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Use a throwaway in-memory-style DB for the test (temp file)
import tempfile
_TMP_DB = os.path.join(tempfile.gettempdir(), "carrier_peers_test.db")

# Monkey-patch DB_PATH before importing broker
import importlib
import carrier_peers_broker as _broker_mod
_broker_mod.DB_PATH = _TMP_DB
# Reset singleton so broker uses patched path
_broker_mod._db = None

from http.server import HTTPServer
import carrier_peers_client as client

TEST_PORT = 19876
BROKER_URL = f"http://127.0.0.1:{TEST_PORT}"

PASS_COUNT = 0
FAIL_COUNT = 0
ERRORS: list[str] = []


def _check(label: str, condition: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✓ {label}")
    else:
        FAIL_COUNT += 1
        msg = f"  ✗ {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)


# ── Patch client's session_id generation to be deterministic ─────────────────
_FIXED_SESSIONS: dict[str, str] = {}

_orig_session_id = client._session_id_for

def _patched_session_id(bot_id: str) -> str:
    if bot_id not in _FIXED_SESSIONS:
        _FIXED_SESSIONS[bot_id] = f"test-{bot_id}-{os.getpid()}"
    return _FIXED_SESSIONS[bot_id]

client._session_id_for = _patched_session_id


# ── Broker thread ─────────────────────────────────────────────────────────────

def _run_broker(server: HTTPServer) -> None:
    server.serve_forever()


def _start_broker() -> HTTPServer:
    # Re-init DB with patched path
    _broker_mod._db = None
    _broker_mod._lock = threading.Lock()

    server = HTTPServer(("127.0.0.1", TEST_PORT), _broker_mod.PeerBrokerHandler)
    t = threading.Thread(target=_run_broker, args=(server,), daemon=True)
    t.start()
    # Give it a moment to start
    time.sleep(0.3)
    return server


# ── Test runner ───────────────────────────────────────────────────────────────

def run_tests():
    print("Starting broker on port", TEST_PORT, "...")
    server = _start_broker()

    try:
        # 1. Register chief_of_staff
        ok = client.register(BROKER_URL, bot_id="chief_of_staff",
                             profile_name="default",
                             current_task="Fleet oversight",
                             capabilities=["dispatch", "kanban"])
        _check("register chief_of_staff", ok)

        # 2. Register coding_lt
        ok = client.register(BROKER_URL, bot_id="coding_lt",
                             profile_name="coding",
                             current_task="Writing tests",
                             capabilities=["python", "git"])
        _check("register coding_lt", ok)

        # 3. List peers -- both should appear
        peers = client.list_peers(BROKER_URL)
        bot_ids = {p["bot_id"] for p in peers}
        _check("list_peers returns both", {"chief_of_staff", "coding_lt"} <= bot_ids,
               f"got: {bot_ids}")

        # 4. Send message from chief_of_staff -> coding_lt
        ok = client.send_message(BROKER_URL,
                                  to_bot_id="coding_lt",
                                  from_bot_id="chief_of_staff",
                                  content="Hello from chief_of_staff!")
        _check("send_message to coding_lt", ok)

        # 5. coding_lt polls and retrieves the message
        msgs = client.poll_messages(BROKER_URL, bot_id="coding_lt")
        _check("coding_lt receives message", len(msgs) == 1,
               f"got {len(msgs)} messages")
        if msgs:
            _check("message content correct",
                   msgs[0]["content"] == "Hello from chief_of_staff!",
                   f"got: {msgs[0]['content']!r}")

        # 6. Messages are cleared after poll
        msgs2 = client.poll_messages(BROKER_URL, bot_id="coding_lt")
        _check("messages cleared after poll", len(msgs2) == 0,
               f"got {len(msgs2)} messages")

        # 7. Heartbeat works
        ok = client.heartbeat(BROKER_URL, "chief_of_staff")
        _check("heartbeat chief_of_staff", ok)

        # 8. Unregister both
        ok1 = client.unregister(BROKER_URL, "chief_of_staff")
        ok2 = client.unregister(BROKER_URL, "coding_lt")
        _check("unregister chief_of_staff", ok1)
        _check("unregister coding_lt", ok2)

        # 9. List peers -- should be empty now
        peers = client.list_peers(BROKER_URL)
        _check("peers empty after unregister", len(peers) == 0,
               f"got: {[p['bot_id'] for p in peers]}")

    finally:
        server.shutdown()
        # Cleanup temp DB
        try:
            os.remove(_TMP_DB)
        except OSError:
            pass


def main():
    run_tests()
    total = PASS_COUNT + FAIL_COUNT
    print(f"\n{'─'*40}")
    print(f"Results: {PASS_COUNT}/{total} checks passed")
    if FAIL_COUNT == 0:
        print("PASS")
    else:
        print("FAIL")
        for e in ERRORS:
            print(" ", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

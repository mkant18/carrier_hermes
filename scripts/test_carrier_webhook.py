"""
test_carrier_webhook.py — Integration test for the carrier webhook receiver.

Starts the receiver in-process, sends a test payload, verifies a Kanban task
was created, prints PASS or FAIL.

Usage:
    python scripts/test_carrier_webhook.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.carrier_webhook_receiver import (
    KANBAN_DB,
    WEBHOOKS_DB,
    _init_webhooks_db,
    start_server,
)

TEST_PORT = 8801  # Use a distinct port so we don't collide with a running instance
TEST_SECRET = "test-secret-carrier-webhook"
TEST_DEDUP_ID = f"test-dedup-{int(time.time())}"

os.environ["CARRIER_WEBHOOK_SECRET"] = TEST_SECRET


def _send_webhook(payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}/webhook",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _health_check() -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def _task_exists(task_id: str) -> bool:
    if not KANBAN_DB.exists():
        return False
    with sqlite3.connect(str(KANBAN_DB)) as conn:
        row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row is not None


def run_tests() -> bool:
    all_passed = True

    print(f"[test] Starting webhook receiver on port {TEST_PORT}...")
    server = start_server(port=TEST_PORT, block=False)
    time.sleep(0.3)  # Let the server start

    def fail(msg: str) -> None:
        nonlocal all_passed
        print(f"  FAIL: {msg}")
        all_passed = False

    def ok(msg: str) -> None:
        print(f"  PASS: {msg}")

    # Test 1: Health check
    print("\n[test] 1. Health check")
    if _health_check():
        ok("GET /health returns status=ok")
    else:
        fail("GET /health did not return ok")

    # Test 2: Valid webhook accepted
    print("\n[test] 2. Valid webhook → Kanban task created")
    payload = {
        "event_type": "github_pr_opened",
        "target_bot_id": "coding_lt",
        "task_description": "Review PR: Add OpenMausBot patterns",
        "dedup_id": TEST_DEDUP_ID,
        "secret": TEST_SECRET,
        "repo": "carrier_hermes",
        "pr_title": "feat: OpenMausBot implementation",
        "pr_url": "https://github.com/org/carrier_hermes/pull/99",
    }
    status, resp = _send_webhook(payload)
    if status == 202:
        ok(f"POST /webhook returned 202 (task_id={resp.get('task_id', '?')})")
        task_id = resp.get("task_id")
        if task_id and _task_exists(task_id):
            ok(f"Kanban task {task_id} found in DB")
        elif not KANBAN_DB.exists():
            print(f"  SKIP: Kanban DB not found at {KANBAN_DB} (expected in CI)")
        else:
            fail(f"Kanban task {task_id} NOT found in DB")
    else:
        fail(f"POST /webhook returned {status}: {resp}")

    # Test 3: Duplicate rejected
    print("\n[test] 3. Duplicate dedup_id → rejected")
    status2, resp2 = _send_webhook(payload)  # same dedup_id
    if status2 == 200 and resp2.get("status") == "duplicate":
        ok("Duplicate webhook correctly returned status=duplicate")
    else:
        fail(f"Expected 200/duplicate, got {status2}: {resp2}")

    # Test 4: Wrong secret rejected
    print("\n[test] 4. Wrong secret → 401")
    bad_payload = dict(payload, secret="wrong", dedup_id=f"bad-{time.time()}")
    status3, resp3 = _send_webhook(bad_payload)
    if status3 == 401:
        ok("Wrong secret returns 401")
    else:
        fail(f"Expected 401, got {status3}: {resp3}")

    # Test 5: Unsupported event_type
    print("\n[test] 5. Unsupported event_type → 400")
    bad_event = dict(payload, event_type="unknown_event", dedup_id=f"bad2-{time.time()}")
    status4, resp4 = _send_webhook(bad_event)
    if status4 == 400:
        ok("Unsupported event_type returns 400")
    else:
        fail(f"Expected 400, got {status4}: {resp4}")

    server.shutdown()

    print("\n" + ("=" * 50))
    if all_passed:
        print("PASS — all carrier webhook receiver tests passed")
    else:
        print("FAIL — some tests failed (see above)")
    print("=" * 50)

    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

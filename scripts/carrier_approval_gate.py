"""
carrier_approval_gate.py — Human-in-the-loop approval gate for carrier bot actions.

Posts a Discord embed with Approve/Deny buttons to the fleet channel, polls
SQLite for button-click resolution, and auto-denies on timeout. All state is
persisted for audit trail. Inspired by OpenMausBot's auto-approve.ts pattern:
a lightweight "you probably didn't mean to hand THIS one over unattended"
backstop for irreversible actions.

Usage:
    from scripts.carrier_approval_gate import request_approval, is_irreversible

    if is_irreversible("git_push_main"):
        result = request_approval(
            bot_id="coding_lt",
            action_type="git_push_main",
            description="Push release branch to main",
            payload={"branch": "release/v2.1", "sha": "abc123"},
        )
        if not result["approved"]:
            raise RuntimeError(f"Approval denied: {result['reason']}")
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
CARRIER_DIR = HERMES_HOME / "carrier"
APPROVALS_DB = CARRIER_DIR / "approvals.db"
DISCORD_CHANNEL_ID = "1541866378255011980"

IRREVERSIBLE_ACTIONS: list[str] = [
    "git_push_main",
    "send_email",
    "delete_file",
    "deploy",
    "merge_pr",
]


def is_irreversible(action_type: str) -> bool:
    """Return True if action_type requires an approval gate."""
    return action_type in IRREVERSIBLE_ACTIONS


# ── Token resolution ─────────────────────────────────────────────────────────

def _get_discord_token() -> str:
    """Fetch DISCORD_FLEET_BOT_TOKEN from env or Doppler."""
    token = os.environ.get("DISCORD_FLEET_BOT_TOKEN", "")
    if token:
        return token
    try:
        result = subprocess.run(
            [
                "doppler", "secrets", "get", "DISCORD_FLEET_BOT_TOKEN",
                "--plain",
                "--project", "carrier-ops",
                "--config", "prd",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


# ── DB helpers ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Open (and lazily initialize) the approvals database connection."""
    CARRIER_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(APPROVALS_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id                  TEXT PRIMARY KEY,
                bot_id              TEXT NOT NULL,
                action_type         TEXT NOT NULL,
                action_description  TEXT NOT NULL,
                payload_json        TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'pending',
                created_at          REAL NOT NULL,
                resolved_at         REAL,
                resolved_by         TEXT,
                timeout_seconds     INTEGER NOT NULL DEFAULT 300
            )
        """)
        conn.commit()


_init_db()


def get_pending_approvals() -> list[dict]:
    """Return all pending approvals (used by the listener)."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Discord helpers ──────────────────────────────────────────────────────────

def _discord_post(endpoint: str, payload: dict, token: str) -> dict | None:
    """POST to Discord REST API. Returns parsed JSON or None on error."""
    url = f"https://discord.com/api/v10{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[approval_gate] Discord POST {endpoint} HTTP {exc.code}: {body[:200]}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[approval_gate] Discord POST {endpoint} error: {exc}")
        return None


def _post_approval_embed(
    approval_id: str,
    bot_id: str,
    action_type: str,
    description: str,
    payload: Any,
    timeout: int,
    token: str,
) -> str | None:
    """Post approval embed with Approve/Deny buttons. Returns message_id or None."""
    payload_preview = json.dumps(payload, indent=2, default=str)[:800]
    embed = {
        "title": f"⚠️ Approval Required — `{action_type}`",
        "color": 0xFF6600,
        "fields": [
            {"name": "Bot", "value": bot_id, "inline": True},
            {"name": "Action", "value": action_type, "inline": True},
            {"name": "Timeout", "value": f"{timeout}s", "inline": True},
            {"name": "Description", "value": description[:1024]},
            {"name": "Payload Preview", "value": f"```json\n{payload_preview}\n```"},
        ],
        "footer": {"text": f"approval_id: {approval_id}"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    body = {
        "embeds": [embed],
        "components": [
            {
                "type": 1,  # ACTION_ROW
                "components": [
                    {
                        "type": 2,  # BUTTON
                        "style": 3,  # SUCCESS (green)
                        "label": "✅ Approve",
                        "custom_id": "approve_" + approval_id,
                    },
                    {
                        "type": 2,  # BUTTON
                        "style": 4,  # DANGER (red)
                        "label": "❌ Deny",
                        "custom_id": "deny_" + approval_id,
                    },
                ],
            }
        ],
    }
    result = _discord_post(f"/channels/{DISCORD_CHANNEL_ID}/messages", body, token)
    if result and "id" in result:
        return result["id"]
    return None


def _post_confirmation(approval_id: str, approved: bool, resolved_by: str, token: str) -> None:
    """Post a confirmation message after resolution."""
    status_str = "✅ **Approved**" if approved else "❌ **Denied**"
    body = {
        "content": f"{status_str} — approval `{approval_id}` resolved by `{resolved_by}`",
    }
    _discord_post(f"/channels/{DISCORD_CHANNEL_ID}/messages", body, token)


# ── Core API ─────────────────────────────────────────────────────────────────

def resolve_approval(approval_id: str, approved: bool, resolved_by: str) -> bool:
    """
    Update approval record to approved/denied.

    Called by the listener when a button is clicked, or by admin tooling.
    Returns True if the record was found — resolving an already-resolved
    record is treated as an idempotent success.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if not row:
            print(f"[approval_gate] resolve_approval: unknown id {approval_id}")
            return False
        if row["status"] != "pending":
            print(f"[approval_gate] resolve_approval: {approval_id} already {row['status']}")
            return True  # idempotent
        new_status = "approved" if approved else "denied"
        conn.execute(
            """
            UPDATE approvals
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ?
            """,
            (new_status, time.time(), resolved_by, approval_id),
        )
        conn.commit()

    token = _get_discord_token()
    if token:
        _post_confirmation(approval_id, approved, resolved_by, token)
    return True


def request_approval(
    bot_id: str,
    action_type: str,
    description: str,
    payload: Any,
    timeout: int = 300,
) -> dict:
    """
    Gate an irreversible action behind a human approval.

    1. Inserts a pending record into the SQLite DB.
    2. Posts a Discord embed with Approve/Deny buttons.
    3. Polls the DB every 5 seconds until resolved or timed out.
    4. Auto-denies on timeout.

    Returns:
        {
            "approved": bool,
            "reason": str,
            "approval_id": str,
        }
    """
    approval_id = str(uuid.uuid4())
    payload_json = json.dumps(payload, default=str)

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO approvals
                (id, bot_id, action_type, action_description, payload_json,
                 status, created_at, timeout_seconds)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (approval_id, bot_id, action_type, description, payload_json,
             time.time(), timeout),
        )
        conn.commit()

    print(f"[approval_gate] Created approval {approval_id} for {bot_id}/{action_type}")

    token = _get_discord_token()
    if token:
        msg_id = _post_approval_embed(
            approval_id, bot_id, action_type, description, payload, timeout, token
        )
        if msg_id:
            print(f"[approval_gate] Discord embed posted (msg_id={msg_id})")
        else:
            print(f"[approval_gate] WARNING: Discord embed failed — will auto-deny in {timeout}s")
    else:
        print("[approval_gate] WARNING: No Discord token — approval will auto-deny on timeout")

    # Poll for resolution
    deadline = time.monotonic() + timeout
    poll_interval = 5.0

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT status, resolved_by FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()

        if row and row["status"] != "pending":
            approved = row["status"] == "approved"
            resolved_by = row["resolved_by"] or "unknown"
            reason = f"Resolved by {resolved_by}" if approved else f"Denied by {resolved_by}"
            print(f"[approval_gate] {approval_id} resolved: {row['status']} by {resolved_by}")
            return {"approved": approved, "reason": reason, "approval_id": approval_id}

    # Timeout → auto-deny
    print(f"[approval_gate] {approval_id} timed out after {timeout}s — auto-denying")
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE approvals
            SET status = 'denied', resolved_at = ?, resolved_by = 'auto-timeout'
            WHERE id = ? AND status = 'pending'
            """,
            (time.time(), approval_id),
        )
        conn.commit()

    if token:
        _post_confirmation(approval_id, False, f"auto-timeout ({timeout}s)", token)

    return {
        "approved": False,
        "reason": f"Auto-denied: no response within {timeout}s",
        "approval_id": approval_id,
    }


# ── CLI shim ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "resolve":
        # python carrier_approval_gate.py resolve <approval_id> approve|deny [resolved_by]
        aid = sys.argv[2]
        approved = sys.argv[3].lower() in ("approve", "approved", "true", "1")
        resolved_by = sys.argv[4] if len(sys.argv) > 4 else "cli-admin"
        ok = resolve_approval(aid, approved, resolved_by)
        print("OK" if ok else "FAILED")
        sys.exit(0 if ok else 1)

    # Demo request
    print("Running demo approval request (30s timeout)...")
    result = request_approval(
        bot_id="demo_bot",
        action_type="git_push_main",
        description="Demo: push test branch to main",
        payload={"branch": "demo", "sha": "abc123"},
        timeout=30,
    )
    print(f"Result: {result}")

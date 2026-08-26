"""
carrier_approval_gate.py — Human-in-the-loop approval gate for carrier bots.

Inspired by OpenMausBot's auto-approve.ts pattern: a lightweight "you probably
didn't mean to hand THIS one over unattended" backstop for irreversible actions.

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
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── paths ─────────────────────────────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "C:/Users/micha/AppData/Local/hermes"))
CARRIER_DIR = HERMES_HOME / "carrier"
CARRIER_DIR.mkdir(parents=True, exist_ok=True)
APPROVALS_DB = CARRIER_DIR / "approvals.db"

# ── Discord constants ──────────────────────────────────────────────────────────
FLEET_CHANNEL_ID = "1541866378255011980"

# ── irreversible action registry ──────────────────────────────────────────────
IRREVERSIBLE_ACTIONS: list[str] = [
    "git_push_main",
    "send_email",
    "delete_file",
    "deploy",
    "merge_pr",
]


def is_irreversible(action_type: str) -> bool:
    """Return True if action_type is on the irreversible list."""
    return action_type in IRREVERSIBLE_ACTIONS


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(APPROVALS_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id               TEXT PRIMARY KEY,
                bot_id           TEXT NOT NULL,
                action_type      TEXT NOT NULL,
                action_description TEXT NOT NULL,
                payload_json     TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending',
                created_at       TEXT NOT NULL,
                resolved_at      TEXT,
                resolved_by      TEXT,
                timeout_seconds  INTEGER NOT NULL DEFAULT 300
            )
        """)
        conn.commit()


_init_db()


# ── Doppler / token helper ─────────────────────────────────────────────────────

def _get_discord_token() -> str:
    """Fetch DISCORD_FLEET_BOT_TOKEN from Doppler, fall back to env."""
    env_val = os.environ.get("DISCORD_FLEET_BOT_TOKEN")
    if env_val:
        return env_val
    try:
        result = subprocess.run(
            ["doppler", "secrets", "get", "DISCORD_FLEET_BOT_TOKEN", "--plain"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError(
        "DISCORD_FLEET_BOT_TOKEN not found in env or Doppler. "
        "Set it or run: doppler run -- python carrier_approval_gate.py"
    )


# ── Discord embed poster ───────────────────────────────────────────────────────

def _post_discord_approval_request(
    approval_id: str,
    bot_id: str,
    action_type: str,
    description: str,
    payload: dict,
    timeout_seconds: int,
) -> None:
    """Post an approval request embed to the fleet Discord channel with Approve/Deny buttons."""
    import urllib.request
    import urllib.error

    try:
        token = _get_discord_token()
    except RuntimeError as exc:
        print(f"[approval_gate] WARNING: cannot post Discord notification: {exc}")
        return

    irreversible_note = "⚠️ **IRREVERSIBLE ACTION**" if is_irreversible(action_type) else "ℹ️ Reversible action"

    embed = {
        "title": f"🔐 Approval Request: `{action_type}`",
        "description": (
            f"**Bot:** `{bot_id}`\n"
            f"**Action:** `{action_type}`\n"
            f"**Description:** {description}\n"
            f"**Approval ID:** `{approval_id}`\n"
            f"{irreversible_note}\n"
            f"**Timeout:** {timeout_seconds}s — auto-Deny if not resolved"
        ),
        "color": 0xFF4444 if is_irreversible(action_type) else 0xFFAA00,
        "fields": [
            {"name": "Payload", "value": f"```json\n{json.dumps(payload, indent=2)[:900]}\n```", "inline": False}
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": f"approval_id={approval_id}"},
    }

    # Buttons (components)
    components = [
        {
            "type": 1,  # ACTION_ROW
            "components": [
                {
                    "type": 2,  # BUTTON
                    "style": 3,  # SUCCESS (green)
                    "label": "✅ Approve",
                    "custom_id": f"approve:{approval_id}",
                },
                {
                    "type": 2,
                    "style": 4,  # DANGER (red)
                    "label": "❌ Deny",
                    "custom_id": f"deny:{approval_id}",
                },
            ],
        }
    ]

    body = json.dumps({"embeds": [embed], "components": components}).encode()
    url = f"https://discord.com/api/v10/channels/{FLEET_CHANNEL_ID}/messages"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 201):
                print(f"[approval_gate] Discord post returned {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"[approval_gate] Discord HTTP error {exc.code}: {exc.read()[:200]}")
    except Exception as exc:
        print(f"[approval_gate] Discord post failed: {exc}")


# ── Core API ───────────────────────────────────────────────────────────────────

def request_approval(
    bot_id: str,
    action_type: str,
    description: str,
    payload: dict[str, Any],
    timeout: int = 300,
) -> dict:
    """
    Request human approval for an action.

    Inserts a pending record, posts a Discord embed with Approve/Deny buttons,
    then polls every 5 seconds until resolved or timed out.

    Returns:
        {"approved": bool, "reason": str, "approval_id": str}
    """
    approval_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO approvals
                (id, bot_id, action_type, action_description, payload_json,
                 status, created_at, timeout_seconds)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (approval_id, bot_id, action_type, description,
             json.dumps(payload), now, timeout),
        )
        conn.commit()

    print(f"[approval_gate] Approval requested: {approval_id} ({action_type})")
    _post_discord_approval_request(
        approval_id, bot_id, action_type, description, payload, timeout
    )

    # Poll for resolution
    deadline = time.monotonic() + timeout
    poll_interval = 5

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT status, resolved_by FROM approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        if row and row["status"] != "pending":
            approved = row["status"] == "approved"
            return {
                "approved": approved,
                "reason": f"Resolved by {row['resolved_by']}" if approved else f"Denied by {row['resolved_by']}",
                "approval_id": approval_id,
            }

    # Timeout — auto-Deny
    _auto_deny(approval_id, timeout)
    return {
        "approved": False,
        "reason": f"Auto-denied: no response within {timeout}s",
        "approval_id": approval_id,
    }


def resolve_approval(approval_id: str, approved: bool, resolved_by: str) -> bool:
    """
    Resolve a pending approval.

    Returns True if the record was found and updated, False if not found or
    already resolved.
    """
    now = datetime.now(timezone.utc).isoformat()
    status = "approved" if approved else "denied"

    with _get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE approvals
               SET status = ?, resolved_at = ?, resolved_by = ?
             WHERE id = ? AND status = 'pending'
            """,
            (status, now, resolved_by, approval_id),
        )
        conn.commit()
        updated = cur.rowcount > 0

    if updated:
        print(f"[approval_gate] Approval {approval_id} → {status} by {resolved_by}")
    else:
        print(f"[approval_gate] WARNING: resolve_approval: id={approval_id} not found or already resolved")
    return updated


def _auto_deny(approval_id: str, timeout: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE approvals
               SET status = 'denied', resolved_at = ?, resolved_by = 'auto-timeout'
             WHERE id = ? AND status = 'pending'
            """,
            (now, approval_id),
        )
        conn.commit()
    print(f"[approval_gate] Auto-denied {approval_id} after {timeout}s timeout")


def get_pending_approvals() -> list[dict]:
    """Return all pending approvals (used by the listener)."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("IRREVERSIBLE_ACTIONS:", IRREVERSIBLE_ACTIONS)
    print("is_irreversible('git_push_main'):", is_irreversible("git_push_main"))
    print("is_irreversible('lint'):", is_irreversible("lint"))
    print("APPROVALS_DB:", APPROVALS_DB)
    print("DB exists:", APPROVALS_DB.exists())
    print("Pending approvals:", len(get_pending_approvals()))
    print("OK — carrier_approval_gate ready (set DISCORD_FLEET_BOT_TOKEN to test Discord posting)")

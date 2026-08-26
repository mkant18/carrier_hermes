"""
carrier_approval_listener.py — Discord interaction poller for the approval gate.

Runs as a background daemon thread. Polls Discord's channel messages for
button interactions (Approve / Deny) and resolves matching pending approvals
via carrier_approval_gate.resolve_approval().

Start it as part of your fleet boot sequence:
    from scripts.carrier_approval_listener import start_listener_daemon
    start_listener_daemon()

Or run standalone:
    python scripts/carrier_approval_listener.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Allow direct execution from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.carrier_approval_gate import get_pending_approvals, resolve_approval

# ── Config ─────────────────────────────────────────────────────────────────────
FLEET_CHANNEL_ID = "1541866378255011980"
POLL_INTERVAL = 5          # seconds between Discord polls
INTERACTION_ENDPOINT_POLL_INTERVAL = 3  # seconds for interaction polling


def _get_discord_token() -> Optional[str]:
    """Fetch DISCORD_FLEET_BOT_TOKEN from env or Doppler."""
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
    return None


def _discord_get(url: str, token: str) -> Optional[dict]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:  # rate limited
            retry_after = float(json.loads(exc.read()).get("retry_after", 5))
            print(f"[approval_listener] Rate-limited, sleeping {retry_after}s")
            time.sleep(retry_after)
        elif exc.code not in (403, 404):
            print(f"[approval_listener] Discord GET error {exc.code}: {exc.read()[:200]}")
    except Exception as exc:
        print(f"[approval_listener] Discord GET failed: {exc}")
    return None


def _fetch_recent_interactions(token: str, after_message_id: Optional[str] = None) -> list[dict]:
    """
    Fetch recent messages from the fleet channel that contain component interactions.
    Discord bots see button clicks as messages in the channel timeline.

    We look for messages whose components reference our approval button custom_ids.
    """
    url = f"https://discord.com/api/v10/channels/{FLEET_CHANNEL_ID}/messages?limit=20"
    if after_message_id:
        url += f"&after={after_message_id}"
    data = _discord_get(url, token)
    return data if isinstance(data, list) else []


def _parse_button_click(message: dict) -> Optional[tuple[str, str]]:
    """
    Parse a Discord message/interaction for our approval button clicks.

    Returns (action, approval_id) where action is 'approve' or 'deny', or None.

    Discord sends button interactions as webhook events. Since we're polling
    the channel, we look for messages with interaction metadata whose
    referenced component matches our custom_id pattern.
    """
    # Check interaction field (set when a user clicks a component)
    interaction = message.get("interaction")
    if interaction:
        custom_id = interaction.get("data", {}).get("custom_id", "")
        if custom_id.startswith("approve:") or custom_id.startswith("deny:"):
            parts = custom_id.split(":", 1)
            return parts[0], parts[1]

    # Also check message components for echoed interactions (some bot setups)
    for component_row in message.get("components", []):
        for button in component_row.get("components", []):
            cid = button.get("custom_id", "")
            if cid.startswith("approve:") or cid.startswith("deny:"):
                # Only act if this looks like it's been interacted with
                # (style changed to indicate pressed / disabled)
                if button.get("disabled"):
                    parts = cid.split(":", 1)
                    return parts[0], parts[1]

    return None


def _poll_interactions_once(token: str, seen_message_ids: set, pending_ids: set) -> None:
    """Single poll cycle: fetch messages, match to pending approvals, resolve."""
    messages = _fetch_recent_interactions(token)

    for msg in messages:
        msg_id = msg.get("id")
        if not msg_id or msg_id in seen_message_ids:
            continue
        seen_message_ids.add(msg_id)

        result = _parse_button_click(msg)
        if not result:
            continue

        action, approval_id = result
        if approval_id not in pending_ids:
            continue

        resolved_by = msg.get("author", {}).get("username", "discord-user")
        approved = action == "approve"
        if resolve_approval(approval_id, approved, resolved_by):
            print(f"[approval_listener] Resolved {approval_id}: {action} by {resolved_by}")
            pending_ids.discard(approval_id)


def _listener_loop(stop_event: threading.Event) -> None:
    """Main listener loop — runs until stop_event is set."""
    token = _get_discord_token()
    if not token:
        print("[approval_listener] WARNING: DISCORD_FLEET_BOT_TOKEN not available. "
              "Listener running in no-op mode (approvals will auto-timeout).")
        # Keep thread alive so it can be stopped cleanly
        while not stop_event.is_set():
            stop_event.wait(timeout=30)
        return

    print("[approval_listener] Started — polling Discord interactions")
    seen_message_ids: set = set()

    while not stop_event.is_set():
        try:
            pending = get_pending_approvals()
            pending_ids = {a["id"] for a in pending}
            if pending_ids:
                _poll_interactions_once(token, seen_message_ids, pending_ids)
        except Exception as exc:
            print(f"[approval_listener] Error in poll loop: {exc}")

        stop_event.wait(timeout=POLL_INTERVAL)

    print("[approval_listener] Stopped")


# ── Public API ─────────────────────────────────────────────────────────────────

_listener_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None


def start_listener_daemon() -> threading.Thread:
    """Start the approval listener as a daemon background thread."""
    global _listener_thread, _stop_event

    if _listener_thread and _listener_thread.is_alive():
        print("[approval_listener] Already running")
        return _listener_thread

    _stop_event = threading.Event()
    _listener_thread = threading.Thread(
        target=_listener_loop,
        args=(_stop_event,),
        name="carrier-approval-listener",
        daemon=True,
    )
    _listener_thread.start()
    return _listener_thread


def stop_listener_daemon() -> None:
    """Signal the daemon thread to stop."""
    if _stop_event:
        _stop_event.set()
    if _listener_thread:
        _listener_thread.join(timeout=10)


# ── Standalone entry point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import signal

    stop = threading.Event()
    thread = start_listener_daemon()
    print("[approval_listener] Running standalone. Ctrl+C to stop.")

    def _handle_signal(signum, frame):
        print("\n[approval_listener] Shutting down...")
        stop_listener_daemon()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    thread.join()

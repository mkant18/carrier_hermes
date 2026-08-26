"""
carrier_approval_listener.py — Discord interaction listener for approval gate.

Polls Discord REST API every 2 seconds for button interactions on approval
embeds. Resolves approvals via carrier_approval_gate.resolve_approval().

Run as daemon thread:
    from scripts.carrier_approval_listener import start_listener_daemon
    start_listener_daemon()

Or standalone:
    python scripts/carrier_approval_listener.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# Allow import from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.carrier_approval_gate import resolve_approval, _get_discord_token  # noqa: E402

DISCORD_CHANNEL_ID = "1541866378255011980"
POLL_INTERVAL = 2.0  # seconds between Discord polls

# Track last seen interaction to avoid double-processing
_seen_interaction_ids: set[str] = set()
_last_message_id: str | None = None


def _discord_get(endpoint: str, token: str) -> dict | list | None:
    """GET from Discord REST API. Returns parsed JSON or None on error."""
    url = f"https://discord.com/api/v10{endpoint}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            print(f"[approval_listener] GET {endpoint} HTTP {exc.code}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[approval_listener] GET {endpoint} error: {exc}")
        return None


def _discord_post_ack(interaction_id: str, interaction_token: str) -> None:
    """Acknowledge a button interaction (type 6 = deferred update)."""
    url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
    data = json.dumps({"type": 6}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"[approval_listener] ACK interaction error: {exc}")


def _fetch_channel_messages(token: str, after: str | None = None) -> list[dict]:
    """Fetch recent messages from the fleet channel."""
    params = "?limit=20"
    if after:
        params += f"&after={after}"
    result = _discord_get(f"/channels/{DISCORD_CHANNEL_ID}/messages{params}", token)
    if isinstance(result, list):
        return result
    return []


def _process_message(message: dict, token: str) -> None:
    """Check message for button interaction components and extract approvals."""
    # Discord interactions arrive via webhooks, not polling channel messages.
    # For a polling-only approach, we check pinned interaction results in the channel.
    # The listener mainly reacts to messages that contain the custom_id patterns
    # in their interaction.data (from interaction webhook payloads stored in channel).
    pass  # See _poll_interactions_via_gateway below


def _poll_for_interactions(token: str) -> None:
    """
    Poll the interactions endpoint via the gateway.
    
    Since Discord doesn't expose interactions via REST polling directly,
    we poll the channel for messages where our bot posted a message with
    components. We rely on the approval gate's DB polling as the primary
    mechanism, and this listener watches for explicit /resolve commands
    or direct message triggers as a secondary path.
    
    For full button interaction handling, the bot needs a webhook endpoint.
    This listener polls channel messages for explicit resolve commands:
      Format: !resolve <approval_id> approve|deny
    """
    global _last_message_id
    
    messages = _fetch_channel_messages(token, after=_last_message_id)
    
    if not messages:
        return

    # Messages come newest-first; track the newest id
    newest_id = messages[0]["id"] if messages else None
    if newest_id:
        _last_message_id = newest_id

    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id in _seen_interaction_ids:
            continue

        content = msg.get("content", "").strip()
        author = msg.get("author", {})
        author_name = author.get("username", "unknown")

        # Support explicit !resolve commands in the channel
        if content.startswith("!resolve "):
            parts = content.split()
            if len(parts) >= 3:
                approval_id = parts[1]
                decision = parts[2].lower()
                approved = decision in ("approve", "approved", "yes", "true")
                _seen_interaction_ids.add(msg_id)

                print(
                    f"[approval_listener] !resolve {approval_id} "
                    f"{'approve' if approved else 'deny'} by {author_name}"
                )
                try:
                    ok = resolve_approval(approval_id, approved, author_name)
                    if ok:
                        print(f"[approval_listener] Resolved {approval_id} OK")
                    else:
                        print(f"[approval_listener] resolve_approval returned False for {approval_id}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[approval_listener] Error resolving {approval_id}: {exc}")

        # Check for button interaction data embedded in message components
        # (Discord sends these as interaction messages from bots)
        interaction = msg.get("interaction")
        if interaction:
            itype = msg.get("type")
            # Type 20 = interaction follow-up; look for component interactions
            pass

        # Look for component interaction messages (type 20 with interaction.data)
        components_data = msg.get("interaction_metadata") or {}
        if components_data:
            custom_id = components_data.get("data", {}).get("custom_id", "")
            if custom_id.startswith("approve_") or custom_id.startswith("deny_"):
                if msg_id not in _seen_interaction_ids:
                    _seen_interaction_ids.add(msg_id)
                    approval_id = (
                        custom_id[len("approve_"):]
                        if custom_id.startswith("approve_")
                        else custom_id[len("deny_"):]
                    )
                    approved = custom_id.startswith("approve_")
                    user = components_data.get("user", {}).get("username", "discord-user")
                    print(f"[approval_listener] Button click: {custom_id} by {user}")
                    try:
                        resolve_approval(approval_id, approved, user)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[approval_listener] Error resolving from button: {exc}")


def _listener_loop() -> None:
    """Main poll loop — runs in daemon thread."""
    print("[approval_listener] Starting Discord approval listener...")
    token = _get_discord_token()
    if not token:
        print("[approval_listener] WARNING: No DISCORD_FLEET_BOT_TOKEN — listener running in no-op mode")

    while True:
        try:
            if token:
                _poll_for_interactions(token)
            # Refresh token periodically (Doppler may rotate it)
            else:
                token = _get_discord_token()
        except Exception as exc:  # noqa: BLE001
            print(f"[approval_listener] Poll error: {exc}")
        time.sleep(POLL_INTERVAL)


def start_listener_daemon() -> threading.Thread:
    """Start the approval listener as a background daemon thread."""
    t = threading.Thread(target=_listener_loop, name="approval-listener", daemon=True)
    t.start()
    print(f"[approval_listener] Daemon thread started (id={t.ident})")
    return t


if __name__ == "__main__":
    print("[approval_listener] Running standalone — Ctrl+C to stop")
    _listener_loop()

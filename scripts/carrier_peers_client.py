#!/usr/bin/env python3
"""
carrier_peers_client.py -- Client library for the carrier peers broker.
Provider-agnostic: works with any Hermes session.

All functions use urllib.request (stdlib only, no requests).
All functions are error-safe: return False or [] on network/parse errors.

Typical usage:
    from scripts.carrier_peers_client import register, list_peers, send_message

    ok = register("http://localhost:9876", bot_id="chief_of_staff",
                  profile_name="default", current_task="Fleet oversight",
                  capabilities=["dispatch", "kanban"])
    peers = list_peers("http://localhost:9876")
"""
import json
import os
import time
import uuid
from urllib import request as _req
from urllib.error import URLError
from urllib.parse import urlencode

# ── Private helpers ────────────────────────────────────────────────────────────

def _http(method: str, url: str, body: dict | None = None, timeout: int = 5) -> dict | None:
    """
    Make an HTTP request. Returns parsed JSON dict on success, None on error.
    """
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = _req.Request(url, data=data, headers=headers, method=method)
    try:
        with _req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError):
        return None


def _session_id_for(bot_id: str) -> str:
    """
    Derive a stable session_id for this process from bot_id + PID.
    Can be overridden by env var HERMES_SESSION_ID.
    """
    env_sid = os.environ.get("HERMES_SESSION_ID", "")
    if env_sid:
        return env_sid
    return f"{bot_id}-{os.getpid()}"


# ── Public API ─────────────────────────────────────────────────────────────────

def register(
    broker_url: str,
    bot_id: str,
    profile_name: str = "",
    current_task: str = "",
    capabilities: list | None = None,
) -> bool:
    """
    Register this session with the broker.
    Returns True on success, False on error.
    """
    session_id = _session_id_for(bot_id)
    result = _http("POST", f"{broker_url}/register", {
        "session_id": session_id,
        "bot_id": bot_id,
        "profile_name": profile_name,
        "current_task": current_task,
        "started_at": time.time(),
        "capabilities": capabilities or [],
    })
    return bool(result and result.get("ok"))


def heartbeat(broker_url: str, bot_id: str) -> bool:
    """
    Send a heartbeat to keep this session alive in the broker.
    Returns True on success, False on error.
    """
    session_id = _session_id_for(bot_id)
    params = urlencode({"session_id": session_id})
    result = _http("POST", f"{broker_url}/heartbeat?{params}")
    return bool(result and result.get("ok"))


def unregister(broker_url: str, bot_id: str) -> bool:
    """
    Unregister this session from the broker.
    Returns True on success, False on error.
    """
    session_id = _session_id_for(bot_id)
    params = urlencode({"session_id": session_id})
    result = _http("DELETE", f"{broker_url}/register?{params}")
    return bool(result and result.get("ok"))


def list_peers(broker_url: str) -> list[dict]:
    """
    Return list of active peer dicts: {session_id, bot_id, profile_name,
    current_task, started_at, capabilities, last_heartbeat}.
    Returns [] on error.
    """
    result = _http("GET", f"{broker_url}/peers")
    if not result:
        return []
    return result.get("peers", [])


def send_message(
    broker_url: str,
    to_bot_id: str,
    from_bot_id: str,
    content: str,
) -> bool:
    """
    Send a message to the first active session whose bot_id matches to_bot_id.
    Returns True on success, False on error or not found.
    """
    # Resolve bot_id -> session_id
    peers = list_peers(broker_url)
    target = next((p for p in peers if p.get("bot_id") == to_bot_id), None)
    if not target:
        return False

    to_session_id = target["session_id"]
    from_session = _session_id_for(from_bot_id)
    params = urlencode({"to_session_id": to_session_id})
    result = _http("POST", f"{broker_url}/message?{params}", {
        "from_session": from_session,
        "content": content,
    })
    return bool(result and result.get("ok"))


def poll_messages(broker_url: str, bot_id: str) -> list[dict]:
    """
    Retrieve and clear all messages for this bot's session.
    Returns list of {id, from_session, content, created_at} dicts.
    Returns [] on error.
    """
    session_id = _session_id_for(bot_id)
    params = urlencode({"session_id": session_id})
    result = _http("GET", f"{broker_url}/messages?{params}")
    if not result:
        return []
    return result.get("messages", [])


def announce_task(broker_url: str, bot_id: str, task_description: str) -> bool:
    """
    Update current_task for this session by re-registering with a new task.
    Preserves capabilities and profile_name read from env or defaults.
    Returns True on success.
    """
    profile_name = os.environ.get("HERMES_PROFILE", "")
    # Re-register with updated task (broker uses upsert)
    session_id = _session_id_for(bot_id)
    result = _http("POST", f"{broker_url}/register", {
        "session_id": session_id,
        "bot_id": bot_id,
        "profile_name": profile_name,
        "current_task": task_description,
        "started_at": time.time(),
        "capabilities": [],
    })
    return bool(result and result.get("ok"))

"""
carrier-commands — zero-LLM Discord command interceptor for Carrier Hermes fleet.

Intercepts !status, !flights, and !trace [id] from the #command channel
in the pre_gateway_dispatch hook — before auth, before any LLM turn.

Runs local Python scripts to build the response, POSTs to Discord via
REST (First Watch or Carrier Ops token), then returns {"action": "skip"}
so no LLM turn is ever started.

Token used:
  - DISCORD_BOT_TOKEN on the chief_of_staff profile .env (Carrier Ops)
  - Falls back to DISCORD_FLEET_BOT_TOKEN in ~/.hermes/.env

Commands:
  !status          — per-bot status (state file age + phase + lock check)
  !flights         — all in-progress flights from active_flights.json
  !trace           — last 5 flights from flights.jsonl event log
  !trace <id>      — specific flight trace (exact or substring match)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO = Path.home() / "carrier_hermes"
SCRIPTS_DIR = REPO / "scripts"

COMMAND_SCRIPTS = {
    "!status":  SCRIPTS_DIR / "cmd_status.py",
    "!flights": SCRIPTS_DIR / "cmd_flights.py",
    "!trace":   SCRIPTS_DIR / "cmd_trace.py",
}

# Channel IDs (from docs/DISCORD_CHANNELS.md)
COMMAND_CHANNEL_ID = "1541866378255011980"   # #command — Carrier Ops token
FLEET_CHANNEL_ID   = "1541866443765977138"   # #fleet   — First Watch token


def _load_token() -> str | None:
    """Load DISCORD_BOT_TOKEN from the CoS profile .env (Carrier Ops gateway)."""
    env_path = Path.home() / ".hermes" / "profiles" / "chief_of_staff" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN=") and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    # Fallback to global .env First Watch token
    global_env = Path.home() / ".hermes" / ".env"
    if global_env.exists():
        for line in global_env.read_text().splitlines():
            line = line.strip()
            if line.startswith("DISCORD_FLEET_BOT_TOKEN=") and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return None


def _post_to_discord(channel_id: str, content: str, token: str) -> None:
    """POST a message to Discord via REST. Fire-and-forget; errors logged."""
    import json
    import urllib.error
    import urllib.request

    # Discord 2000 char limit: truncate if needed
    if len(content) > 1990:
        content = content[:1987] + "…"

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({
        "content": content,
        "allowed_mentions": {"parse": []},  # no pings
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.getcode()
            logger.debug("carrier-commands: Discord POST %s → %d", channel_id, status)
    except urllib.error.HTTPError as e:
        body = e.read(256).decode("utf-8", errors="replace")
        logger.warning("carrier-commands: Discord POST failed %d: %s", e.code, body)
    except Exception as exc:
        logger.warning("carrier-commands: Discord POST error: %s", exc)


def _run_command_script(script_path: Path, extra_args: list[str] | None = None) -> str:
    """Run a command script and return its stdout."""
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            err = result.stderr.strip()[:300]
            return f"⚠️ Command error (exit {result.returncode}): {err}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "⚠️ Command timed out after 15s."
    except Exception as exc:
        return f"⚠️ Command failed: {exc}"


def _handle_command(text: str, channel_id: str, token: str) -> bool:
    """
    Check if text is a fleet command. If so, run it, post reply, return True.
    Returns False if not a recognized command.
    """
    stripped = text.strip()
    lower = stripped.lower()

    # --- !status ---
    if lower == "!status":
        script = COMMAND_SCRIPTS["!status"]
        if not script.exists():
            _post_to_discord(channel_id, "⚠️ `cmd_status.py` not found in carrier_hermes/scripts/", token)
        else:
            output = _run_command_script(script)
            _post_to_discord(channel_id, output, token)
        return True

    # --- !flights ---
    if lower == "!flights":
        script = COMMAND_SCRIPTS["!flights"]
        if not script.exists():
            _post_to_discord(channel_id, "⚠️ `cmd_flights.py` not found.", token)
        else:
            output = _run_command_script(script)
            _post_to_discord(channel_id, output, token)
        return True

    # --- !trace [optional flight_id] ---
    if lower == "!trace" or lower.startswith("!trace "):
        script = COMMAND_SCRIPTS["!trace"]
        parts = stripped.split(None, 1)
        extra = [parts[1]] if len(parts) > 1 else []
        if not script.exists():
            _post_to_discord(channel_id, "⚠️ `cmd_trace.py` not found.", token)
        else:
            output = _run_command_script(script, extra)
            _post_to_discord(channel_id, output, token)
        return True

    return False


def pre_gateway_dispatch_handler(event: Any, gateway: Any, session_store: Any, **kwargs: Any) -> dict | None:
    """
    Intercept fleet commands before auth/LLM dispatch.

    Returns {"action": "skip", "reason": "carrier-command"} to swallow the
    message entirely (no LLM turn). Returns None for non-commands.
    """
    try:
        text = getattr(event, "text", None) or ""
        if not isinstance(text, str):
            return None

        stripped = text.strip()
        if not stripped.startswith("!"):
            return None

        lower = stripped.lower()
        is_fleet_cmd = (
            lower == "!status"
            or lower == "!flights"
            or lower == "!trace"
            or lower.startswith("!trace ")
        )
        if not is_fleet_cmd:
            return None

        # Determine the reply channel from event source
        source = getattr(event, "source", None)
        chat_id = getattr(source, "chat_id", None) or COMMAND_CHANNEL_ID

        token = _load_token()
        if not token:
            logger.warning("carrier-commands: no Discord token found; cannot reply")
            return {"action": "skip", "reason": "carrier-command-no-token"}

        logger.info("carrier-commands: intercepting '%s' from chat %s", stripped[:40], chat_id)

        handled = _handle_command(stripped, chat_id, token)
        if handled:
            return {"action": "skip", "reason": "carrier-command"}

    except Exception as exc:
        logger.error("carrier-commands pre_gateway_dispatch error: %s", exc, exc_info=True)

    return None


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch_handler)
    logger.info("carrier-commands: registered !status / !flights / !trace interceptors")

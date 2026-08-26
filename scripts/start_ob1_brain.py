"""Start OB1 Fleet Brain: FastMCP server + Discord capture background thread.

Usage:
    python scripts/start_ob1_brain.py

Environment:
    DISCORD_FLEET_BOT_TOKEN   — Discord bot token (fetched from Doppler if absent)
    OB1_BRAIN_DB              — path to SQLite DB (default: %LOCALAPPDATA%/hermes/carrier/ob1_brain.db)
    OB1_DISCORD_CHANNELS      — comma-separated Discord channel IDs to monitor
    OB1_DISCORD_GUILD         — guild name for metadata
    OB1_DISCORD_IGNORE_BOTS   — set 1 to skip bot messages

Logs to: C:/Users/micha/AppData/Local/hermes/carrier/logs/ob1_brain.log
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

LOG_PATH = Path("C:/Users/micha/AppData/Local/hermes/carrier/logs/ob1_brain.log")
OB1_BRAIN_DIR = Path("C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain")
SERVER_SCRIPT = OB1_BRAIN_DIR / "server.py"
DISCORD_SCRIPT = OB1_BRAIN_DIR / "discord_capture.py"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ob1_brain")


# ---------------------------------------------------------------------------
# Doppler token fetch
# ---------------------------------------------------------------------------

def get_discord_token() -> str:
    """Return DISCORD_FLEET_BOT_TOKEN, fetching from Doppler if not set."""
    token = os.environ.get("DISCORD_FLEET_BOT_TOKEN", "")
    if token:
        return token
    log.info("DISCORD_FLEET_BOT_TOKEN not in env — fetching from Doppler …")
    try:
        result = subprocess.run(
            ["doppler", "secrets", "get", "DISCORD_FLEET_BOT_TOKEN", "--plain"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            os.environ["DISCORD_FLEET_BOT_TOKEN"] = token
            log.info("Fetched DISCORD_FLEET_BOT_TOKEN from Doppler OK")
            return token
        else:
            log.warning("Doppler fetch failed: %s", result.stderr.strip())
    except Exception as exc:
        log.warning("Doppler not available: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Discord capture thread
# ---------------------------------------------------------------------------

def _run_discord_capture() -> None:
    """Run discord_capture.py in a background thread (standalone runner)."""
    token = get_discord_token()
    if not token:
        log.warning("No Discord token — skipping Discord capture thread")
        return

    env = {**os.environ, "DISCORD_BOT_TOKEN": token}
    log.info("Starting Discord capture subprocess …")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(DISCORD_SCRIPT)],
            env=env,
            cwd=str(OB1_BRAIN_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:  # type: ignore[union-attr]
            log.info("[discord_capture] %s", line.rstrip())
        proc.wait()
        log.warning("Discord capture subprocess exited with code %d", proc.returncode)
    except Exception as exc:
        log.error("Discord capture thread error: %s", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("OB1 Fleet Brain starting …")
    log.info("Brain dir: %s", OB1_BRAIN_DIR)
    log.info("Server:    %s", SERVER_SCRIPT)

    if not SERVER_SCRIPT.exists():
        log.error("server.py not found at %s — aborting", SERVER_SCRIPT)
        sys.exit(1)

    # Start Discord capture in background thread
    discord_thread = threading.Thread(target=_run_discord_capture, daemon=True, name="discord-capture")
    discord_thread.start()

    # Start FastMCP server (blocks)
    log.info("Launching FastMCP server (stdio) …")
    env = {**os.environ}
    if "OB1_BRAIN_DB" not in env:
        env["OB1_BRAIN_DB"] = "C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db"

    try:
        result = subprocess.run(
            [sys.executable, str(SERVER_SCRIPT)],
            env=env,
            cwd=str(OB1_BRAIN_DIR),
        )
        log.info("FastMCP server exited with code %d", result.returncode)
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down")
    except Exception as exc:
        log.error("Server error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

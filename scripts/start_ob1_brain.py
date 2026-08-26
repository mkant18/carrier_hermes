"""Start OB1 Fleet Brain: FastMCP server (stdio) + Discord capture background thread.

Usage:
    python scripts/start_ob1_brain.py

Environment (auto-fetched from Doppler if not set):
    SUPABASE_URL              — Supabase project URL
    SUPABASE_SERVICE_KEY      — Supabase service role key
    DISCORD_FLEET_BOT_TOKEN   — Discord bot token
    OB1_BRAIN_DB              — SQLite fallback path
    OB1_DISCORD_CHANNELS      — comma-separated channel IDs (default: 1541866378255011980)
    OB1_DISCORD_IGNORE_BOTS   — set 0 to capture bot messages too

Logs:
    C:/Users/micha/AppData/Local/hermes/carrier/logs/ob1_brain.log
    C:/Users/micha/AppData/Local/hermes/carrier/logs/discord_capture.log
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

OB1_BRAIN_DIR = Path("C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain")
SERVER_SCRIPT = OB1_BRAIN_DIR / "server.py"
DISCORD_SCRIPT = OB1_BRAIN_DIR / "discord_capture.py"
LOG_DIR = Path("C:/Users/micha/AppData/Local/hermes/carrier/logs")
LOG_PATH = LOG_DIR / "ob1_brain.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("start_ob1_brain")


# ---------------------------------------------------------------------------
# Doppler env injection
# ---------------------------------------------------------------------------

def _doppler_get(key: str) -> str:
    try:
        r = subprocess.run(
            ["doppler", "secrets", "get", key, "--plain",
             "--project", "carrier-ops", "--config", "prd"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _ensure_env(*keys: str) -> None:
    """Pull missing env vars from Doppler."""
    for key in keys:
        if not os.environ.get(key):
            val = _doppler_get(key)
            if val:
                os.environ[key] = val
                log.info("Loaded %s from Doppler", key)
            else:
                log.warning("%s not available (Supabase/Discord may not work)", key)


# ---------------------------------------------------------------------------
# Discord capture thread
# ---------------------------------------------------------------------------

def _run_discord_capture() -> None:
    """Run discord_capture.py in a daemon thread."""
    log.info("Discord capture thread: starting %s", DISCORD_SCRIPT)
    try:
        # Import and run directly to share the process
        spec_dir = str(OB1_BRAIN_DIR)
        if spec_dir not in sys.path:
            sys.path.insert(0, spec_dir)

        import importlib.util
        spec = importlib.util.spec_from_file_location("discord_capture", DISCORD_SCRIPT)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        if not (hasattr(mod, 'get_bot_token') and hasattr(mod, 'run_discord_capture')):
            log.error(
                "discord_capture.py missing required API (get_bot_token / run_discord_capture) "
                "— Discord capture disabled"
            )
            return

        import asyncio
        token = mod.get_bot_token()
        if not token:
            log.error("Discord capture: no token — capture disabled")
            return
        log.info("Discord capture: starting asyncio loop")
        asyncio.run(mod.run_discord_capture(token))
    except Exception as exc:
        log.error("Discord capture thread failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("OB1 Fleet Brain starting up")
    log.info("Server script: %s", SERVER_SCRIPT)
    log.info("Discord script: %s", DISCORD_SCRIPT)

    # 1. Inject env vars from Doppler
    _ensure_env(
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "DISCORD_FLEET_BOT_TOKEN",
    )

    # 2. Start Discord capture in background thread
    if DISCORD_SCRIPT.exists():
        dc_thread = threading.Thread(
            target=_run_discord_capture,
            name="discord-capture",
            daemon=True,
        )
        dc_thread.start()
        log.info("Discord capture thread started")
    else:
        log.warning("Discord capture script not found: %s", DISCORD_SCRIPT)

    # 3. Start MCP server (blocking — takes over stdio)
    if not SERVER_SCRIPT.exists():
        log.error("MCP server script not found: %s", SERVER_SCRIPT)
        sys.exit(1)

    log.info("Starting MCP server on stdio …")
    # Import and run the MCP server directly
    spec_dir = str(OB1_BRAIN_DIR)
    if spec_dir not in sys.path:
        sys.path.insert(0, spec_dir)

    import importlib.util
    spec = importlib.util.spec_from_file_location("ob1_server", SERVER_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # mcp.run() blocks — this is the main thread
    if not hasattr(mod, 'mcp'):
        log.error("OB1 server.py missing required .mcp attribute — cannot start MCP server")
        sys.exit(1)
    mod.mcp.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
carrier_viking_watchdog.py - Watchdog for the carrier-viking OpenViking server.

Stdlib only. No external dependencies required.

Usage (as cron / no_agent):
  python scripts/carrier_viking_watchdog.py

Behavior:
  - GET http://localhost:1933/health
  - Prints VIKING_UP if server responds OK
  - Prints VIKING_STARTED if server was down and was restarted
  - Prints VIKING_DOWN if server is unreachable and restart failed
  - Prints VIKING_ERROR on unexpected errors

Exit codes:
  0  — server is up (VIKING_UP or VIKING_STARTED)
  1  — server is down (VIKING_DOWN)
  2  — error occurred

Environment:
  VIKING_SERVER_URL    — server URL (default: http://localhost:1933)
  VIKING_AUTO_RESTART  — if '1', attempt to restart server if down (default: '1')
  CARRIER_HOME         — hermes carrier directory
"""

import os
import subprocess
import sys
import urllib.error
import urllib.request

# ── Config ─────────────────────────────────────────────────────────────────────
SERVER_URL = os.environ.get("VIKING_SERVER_URL", "http://localhost:1933")
AUTO_RESTART = os.environ.get("VIKING_AUTO_RESTART", "1") == "1"
CARRIER_HOME = os.environ.get(
    "CARRIER_HOME",
    os.path.join(os.path.expanduser("~"), "AppData", "Local", "hermes", "carrier"),
)
HERMES_REPO = os.environ.get(
    "CARRIER_HERMES_REPO",
    os.path.join(os.path.expanduser("~"), "carrier_hermes"),
)
START_SCRIPT = os.path.join(HERMES_REPO, "scripts", "start_viking_server.py")
LOG_PATH = os.path.join(CARRIER_HOME, "logs", "viking.log")

# ── Health check ───────────────────────────────────────────────────────────────

def check_health() -> dict | None:
    """
    Returns parsed JSON from /health if server responds OK.
    Returns None if server is unreachable.
    """
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/health", timeout=3) as resp:
            if resp.status == 200:
                import json
                return json.loads(resp.read().decode())
            return None
    except (urllib.error.URLError, OSError):
        return None


def start_server() -> bool:
    """
    Attempt to restart the viking server as a background process.
    Returns True if process was launched (not necessarily healthy yet).
    """
    if not os.path.exists(START_SCRIPT):
        print(f"VIKING_ERROR: start script not found at {START_SCRIPT}", flush=True)
        return False

    log_dir = os.path.dirname(LOG_PATH)
    os.makedirs(log_dir, exist_ok=True)

    try:
        with open(LOG_PATH, "a") as log_f:
            proc = subprocess.Popen(
                [sys.executable, START_SCRIPT],
                stdout=log_f,
                stderr=log_f,
                close_fds=True,
                start_new_session=True,
            )
        print(f"VIKING_STARTING: launched pid={proc.pid}", flush=True)
        return True
    except Exception as e:
        print(f"VIKING_ERROR: failed to launch server: {e}", flush=True)
        return False


def wait_for_server(max_seconds: int = 10) -> bool:
    """Poll /health until server responds or timeout."""
    import time
    for _ in range(max_seconds * 2):
        if check_health() is not None:
            return True
        time.sleep(0.5)
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    health = check_health()

    if health is not None:
        backend = health.get("backend", "unknown")
        db = health.get("db_path", "unknown")
        print(f"VIKING_UP backend={backend} db={db}", flush=True)
        return 0

    # Server is down
    if not AUTO_RESTART:
        print(f"VIKING_DOWN server={SERVER_URL}", flush=True)
        return 1

    print(f"VIKING_DOWN: server unreachable at {SERVER_URL}, attempting restart...", flush=True)
    launched = start_server()

    if not launched:
        print("VIKING_DOWN: restart failed", flush=True)
        return 1

    # Wait for server to come up
    if wait_for_server(max_seconds=15):
        health = check_health()
        backend = (health or {}).get("backend", "unknown")
        print(f"VIKING_STARTED backend={backend}", flush=True)
        return 0
    else:
        print(f"VIKING_DOWN: server launched but not responding after 15s. Check {LOG_PATH}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""OB1 Fleet Brain watchdog — no_agent cron script (stdlib only).

Checks if the OB1 brain MCP server is alive. If it is down, spawns
start_ob1_brain.py. Prints a stable status line for hash-suppression.

Usage (cron, no_agent):
    python scripts/carrier_ob1_watchdog.py

Prints:
    OB1_UP     — server responded to health probe
    OB1_STARTED — server was down, start_ob1_brain.py launched
    OB1_ERROR   — unexpected error during probe or spawn

Env:
    OB1_HEALTH_URL  — override health endpoint (default http://localhost:8001/health)
    OB1_TIMEOUT     — HTTP probe timeout in seconds (default 5)
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HEALTH_URL = os.environ.get("OB1_HEALTH_URL", "http://localhost:8001/health")
TIMEOUT = int(os.environ.get("OB1_TIMEOUT", "5"))

REPO_ROOT = Path(__file__).resolve().parent.parent
START_SCRIPT = REPO_ROOT / "scripts" / "start_ob1_brain.py"


def _health_ok() -> bool:
    """Return True if the OB1 server answers the health endpoint."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def main() -> None:
    try:
        if _health_ok():
            print("OB1_UP")
            return

        # Server is down — spawn start script detached
        if not START_SCRIPT.exists():
            print(f"OB1_ERROR: start script not found at {START_SCRIPT}", file=sys.stderr)
            print("OB1_ERROR")
            return

        subprocess.Popen(
            [sys.executable, str(START_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Detach from parent so watchdog can exit immediately
            close_fds=True,
            start_new_session=True,
        )
        print("OB1_STARTED")

    except Exception as exc:
        print(f"OB1_ERROR: {exc}", file=sys.stderr)
        print("OB1_ERROR")


if __name__ == "__main__":
    main()

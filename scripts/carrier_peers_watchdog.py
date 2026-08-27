#!/usr/bin/env python3
"""
carrier_peers_watchdog.py -- Ensure the carrier peers broker is running.
no_agent: True  (pure stdlib cron script, no agent needed)

This script:
1. Checks GET http://localhost:9876/health
2. If healthy -> prints BROKER_UP
3. If not -> spawns carrier_peers_broker.py and prints BROKER_STARTED

Designed for stable, hash-suppressible cron output.
"""
import os
import subprocess
import sys
import time
from urllib import request as _req
from urllib.error import URLError

BROKER_URL = os.environ.get("CARRIER_PEERS_BROKER_URL", "http://localhost:9876")
HEALTH_URL = f"{BROKER_URL}/health"

# Resolve path to broker script relative to this file
_HERE = os.path.dirname(os.path.abspath(__file__))
BROKER_SCRIPT = os.path.join(_HERE, "carrier_peers_broker.py")

PYTHON = sys.executable


def is_broker_up() -> bool:
    try:
        with _req.urlopen(HEALTH_URL, timeout=3) as resp:
            return resp.status == 200
    except (URLError, OSError):
        return False


def start_broker() -> None:
    """Spawn the broker as a detached background process."""
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen([PYTHON, BROKER_SCRIPT], **kwargs)
    # Brief pause to let the broker initialise before declaring success
    time.sleep(1.5)


def main():
    if is_broker_up():
        print("BROKER_UP", flush=True)
        return

    if not os.path.isfile(BROKER_SCRIPT):
        print(f"BROKER_ERROR: broker script not found at {BROKER_SCRIPT}", flush=True)
        sys.exit(1)

    start_broker()

    # Verify it actually started
    if is_broker_up():
        print("BROKER_STARTED", flush=True)
    else:
        print("BROKER_ERROR: failed to start broker", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

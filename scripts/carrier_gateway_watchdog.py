#!/usr/bin/env python3
"""
carrier_gateway_watchdog.py — Self-healing gateway health monitor
=================================================================
no_agent cron script (zero LLM calls). Runs every 5 minutes via Hermes cron
or Windows Task Scheduler.

WHAT IT DOES:
  1. Reads gateway_state.json to find the gateway PID.
  2. Uses psutil to inspect the gateway process's actual environment variables
     for HERMES_DELEGATED_CHILD_CONTEXT=1 (the "poisoning" bug).
  3. Reads the last 200 lines of gateway.log for tick failures / stall signals.
  4. If gateway is missing, poisoned, or stuck: kills it, removes stale lock,
     runs start_gateway.ps1 to restart cleanly.

OUTPUTS (one line to stdout — hash-suppressed by Hermes cron on stable healthy):
  GATEWAY_HEALTHY       — gateway is running and healthy
  GATEWAY_RESTARTED     — gateway was poisoned/stuck, restarted
  GATEWAY_DOWN          — restart was attempted but gateway still not running
  SUPPRESSED: <reason>  — used by Hermes cron suppression (stable no-LLM path)

REQUIREMENTS: psutil (available in Hermes venv)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
HERMES_HOME  = Path(LOCALAPPDATA) / "hermes"
PROFILE_NAME = "chief_of_staff"
PROFILE_DIR  = HERMES_HOME / "profiles" / PROFILE_NAME

GW_STATE_FILE  = PROFILE_DIR / "gateway_state.json"
GW_LOG_FILE    = PROFILE_DIR / "logs" / "gateway.log"
GW_PID_FILE    = PROFILE_DIR / "gateway.pid"
LOCK_FILE      = HERMES_HOME / "kanban" / ".dispatcher.lock"
CARRIER_LOCK   = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db.dispatch.lock"

# Where this repo lives (for start_gateway.ps1)
CARRIER_HERMES = Path("C:/Users/micha/carrier_hermes")
START_GW_PS1   = CARRIER_HERMES / "scripts" / "start_gateway.ps1"

LOG_DIR        = HERMES_HOME / "carrier" / "logs"
WATCHDOG_LOG   = LOG_DIR / "gateway_watchdog.log"

# Tick failure patterns that indicate the dispatcher is stuck
TICK_FAILURE_PATTERNS = [
    "tick_failure",
    "dispatcher.*error",
    "PermissionError",
    "kanban.*permission",
    "dispatcher.*exception",
    "dispatch.*failed",
    "ERROR.*dispatcher",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg: str, level: str = "INFO") -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] [gateway_watchdog] {msg}"
    print(line, file=sys.stderr)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with WATCHDOG_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Helper: read gateway state
# ---------------------------------------------------------------------------
def _read_gateway_state() -> dict:
    if not GW_STATE_FILE.exists():
        return {}
    try:
        return json.loads(GW_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Helper: check if a PID is alive
# ---------------------------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        # Fallback: os.kill(pid, 0)
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ---------------------------------------------------------------------------
# Helper: check process env for poisoning
# ---------------------------------------------------------------------------
def _is_poisoned(pid: int) -> bool:
    """Return True if the process has HERMES_DELEGATED_CHILD_CONTEXT=1."""
    try:
        import psutil
        proc = psutil.Process(pid)
        env = proc.environ()
        val = env.get("HERMES_DELEGATED_CHILD_CONTEXT", "")
        if val == "1":
            _log(f"PID {pid} is POISONED: HERMES_DELEGATED_CHILD_CONTEXT={val}", "WARN")
            return True
        # Also flag if HERMES_IS_CHILD is set
        child_val = env.get("HERMES_IS_CHILD", "")
        if child_val in ("1", "true", "True"):
            _log(f"PID {pid} has HERMES_IS_CHILD={child_val} set — potential poisoning", "WARN")
            return True
        return False
    except Exception as e:
        _log(f"Could not read env for PID {pid}: {e}", "WARN")
        return False


# ---------------------------------------------------------------------------
# Helper: scan gateway log for tick failures
# ---------------------------------------------------------------------------
def _has_tick_failures() -> bool:
    """Return True if the last 200 lines of gateway.log contain failure signals."""
    import re
    if not GW_LOG_FILE.exists():
        return False
    try:
        lines = GW_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        tail  = lines[-200:] if len(lines) > 200 else lines
        combined = "\n".join(tail)
        for pat in TICK_FAILURE_PATTERNS:
            if re.search(pat, combined, re.IGNORECASE):
                _log(f"Tick failure pattern matched: {pat!r}", "WARN")
                return True
        return False
    except Exception as e:
        _log(f"Could not read gateway.log: {e}", "WARN")
        return False


# ---------------------------------------------------------------------------
# Helper: kill gateway process
# ---------------------------------------------------------------------------
def _kill_gateway(pid: int) -> None:
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        gone, alive = psutil.wait_procs([proc], timeout=5)
        for p in alive:
            p.kill()
        _log(f"Gateway PID {pid} terminated.", "INFO")
    except Exception as e:
        _log(f"Error killing PID {pid}: {e}", "WARN")
        # Fallback
        try:
            os.kill(pid, 9)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helper: remove stale locks
# ---------------------------------------------------------------------------
def _clear_stale_locks() -> None:
    for lock in (LOCK_FILE, CARRIER_LOCK):
        if lock.exists():
            try:
                # Read lock to check if owner is alive
                content = lock.read_text(encoding="utf-8", errors="replace").strip()
                lock_pid = None
                try:
                    d = json.loads(content)
                    lock_pid = d.get("pid")
                except Exception:
                    if content.isdigit():
                        lock_pid = int(content)

                if lock_pid and _pid_alive(int(lock_pid)):
                    _log(f"Lock {lock.name} held by live PID {lock_pid} — skipping.")
                    continue

                lock.unlink()
                _log(f"Removed stale lock: {lock}", "INFO")
            except Exception as e:
                _log(f"Error clearing lock {lock}: {e}", "WARN")


# ---------------------------------------------------------------------------
# Helper: restart gateway via start_gateway.ps1
# ---------------------------------------------------------------------------
def _restart_gateway() -> bool:
    """Kill gateway, clear locks, invoke start_gateway.ps1. Return True if healthy after."""
    # Resolve start_gateway.ps1 — look in scripts/ relative to this file first
    script = START_GW_PS1
    if not script.exists():
        # Fallback: look relative to this script's location
        here = Path(__file__).parent
        alt = here / "start_gateway.ps1"
        if alt.exists():
            script = alt
        else:
            _log(f"start_gateway.ps1 not found at {script} or {alt}", "ERROR")
            return False

    _log(f"Running {script} ...")
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                _log(f"PS1: {line}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                _log(f"PS1 STDERR: {line}", "WARN")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        _log("start_gateway.ps1 timed out after 60s", "ERROR")
        return False
    except Exception as e:
        _log(f"Failed to run start_gateway.ps1: {e}", "ERROR")
        return False


# ---------------------------------------------------------------------------
# Main health check
# ---------------------------------------------------------------------------
def main() -> None:
    _log("=== gateway watchdog tick ===")

    state = _read_gateway_state()
    gw_pid = state.get("pid")

    # --- Case 1: No gateway PID in state ---
    if not gw_pid:
        _log("No gateway PID in gateway_state.json — gateway is down.", "WARN")
        # Also check pid file directly
        if GW_PID_FILE.exists():
            try:
                raw = GW_PID_FILE.read_text().strip()
                if raw.isdigit():
                    gw_pid = int(raw)
                    _log(f"Found PID {gw_pid} in gateway.pid file.")
            except Exception:
                pass

    # --- Case 2: PID found — verify it's alive -------------------------------
    if gw_pid:
        if not _pid_alive(int(gw_pid)):
            _log(f"Gateway PID {gw_pid} is NOT alive — gateway crashed.", "ERROR")
            _clear_stale_locks()
            success = _restart_gateway()
            print("GATEWAY_RESTARTED" if success else "GATEWAY_DOWN")
            return

        # PID is alive — check for poisoning
        poisoned = _is_poisoned(int(gw_pid))
        tick_failures = _has_tick_failures()

        if poisoned or tick_failures:
            reason = []
            if poisoned:      reason.append("HERMES_DELEGATED_CHILD_CONTEXT poisoning")
            if tick_failures: reason.append("tick failures in gateway.log")
            _log(f"Gateway unhealthy: {', '.join(reason)}. Restarting...", "ERROR")
            _kill_gateway(int(gw_pid))
            time.sleep(2)
            _clear_stale_locks()
            success = _restart_gateway()
            print("GATEWAY_RESTARTED" if success else "GATEWAY_DOWN")
            return

        # Healthy!
        _log(f"Gateway PID {gw_pid} is alive and healthy.")
        # Emit stable suppression-friendly output
        print("GATEWAY_HEALTHY")
        return

    # --- Case 3: No PID at all ----------------------------------------------
    _log("Gateway is completely down (no PID file, no state). Attempting restart...", "ERROR")
    _clear_stale_locks()
    success = _restart_gateway()
    if success:
        print("GATEWAY_RESTARTED")
    else:
        print("GATEWAY_DOWN")


if __name__ == "__main__":
    main()

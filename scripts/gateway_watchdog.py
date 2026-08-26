#!/usr/bin/env python3
"""
gateway_watchdog.py — Persistent daemon watchdog for Hermes chief_of_staff gateway
====================================================================================
Runs as a background process (launched by VBS, NSSM, or Scheduled Task).
Every 30 seconds checks if the gateway is alive and healthy. If unhealthy
for 2 consecutive checks (60s), kills any stale process and relaunches.

ZERO LLM calls — pure Python subprocess management only.

HEALTH CRITERIA:
  1. gateway_state.json exists and platforms.discord.state == "connected"
  2. The PID in gateway_state.json is still alive (psutil.pid_exists)

RESTART STORM PROTECTION:
  - Cap at 10 restarts per hour
  - If cap exceeded: log "restart storm detected", pause 1 hour

SIGNALS:
  - Logs heartbeat every 5 minutes to watchdog log
  - Sends Discord notification via hermes CLI when it restarts the gateway

USAGE:
  pythonw.exe gateway_watchdog.py          # No console window (background)
  python.exe  gateway_watchdog.py          # With console (debug)
"""

import json
import logging
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths (Windows native — no MSYS paths)
# ─────────────────────────────────────────────────────────────────────────────
LOCALAPPDATA  = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
HERMES_HOME   = Path(LOCALAPPDATA) / "hermes"
PROFILE_DIR   = HERMES_HOME / "profiles" / "chief_of_staff"
GW_STATE_FILE = PROFILE_DIR / "gateway_state.json"
GW_LOG_DIR    = PROFILE_DIR / "logs"

CARRIER_ROOT  = Path("C:/Users/micha/carrier_hermes")
LOG_DIR       = HERMES_HOME / "carrier" / "logs"
WATCHDOG_LOG  = LOG_DIR / "gateway_watchdog.log"

HERMES_VENV   = HERMES_HOME / "hermes-agent" / "venv"
PYTHON_EXE    = str(HERMES_VENV / "Scripts" / "python.exe")
PYTHONW_EXE   = str(HERMES_VENV / "Scripts" / "pythonw.exe")
HERMES_EXE    = str(HERMES_VENV / "Scripts" / "hermes.exe")

# Gateway launch params
GW_MODULE     = "hermes_cli.main"
GW_ARGS       = ["--profile", "chief_of_staff", "gateway", "run"]
GW_WORKDIR    = str(PROFILE_DIR)

# Gateway env vars (passed explicitly to avoid inheriting watchdog's env)
GW_ENV_VARS   = {
    "HERMES_HOME":             str(PROFILE_DIR),
    "PYTHONIOENCODING":        "utf-8",
    "HERMES_GATEWAY_DETACHED": "1",
    "VIRTUAL_ENV":             str(HERMES_VENV),
    "PYTHONPATH":              str(HERMES_HOME / "hermes-agent"),
    # Explicitly unset child-context poisoning vars
    "HERMES_DELEGATED_CHILD_CONTEXT": "",
    "HERMES_IS_CHILD":                "",
    "HERMES_CHILD_SESSION_ID":        "",
}

# ─────────────────────────────────────────────────────────────────────────────
# Timing
# ─────────────────────────────────────────────────────────────────────────────
CHECK_INTERVAL_S   = 30     # Poll every 30s
UNHEALTHY_THRESH   = 2      # Restart after N consecutive unhealthy checks
HEARTBEAT_EVERY_S  = 300    # Log heartbeat every 5 minutes
RESTART_STORM_CAP  = 10     # Max restarts per hour
RESTART_STORM_WAIT = 3600   # If storm detected, wait 1 hour before trying again
STARTUP_GRACE_S    = 30     # Grace period after restart before rechecking health

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gateway_watchdog")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [gateway_watchdog] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(str(WATCHDOG_LOG), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler (for debug / non-pythonw runs)
    try:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    except Exception:
        pass  # pythonw has no stderr — swallow gracefully

    return logger


log = _setup_logging()


# ─────────────────────────────────────────────────────────────────────────────
# psutil import (required)
# ─────────────────────────────────────────────────────────────────────────────
try:
    import psutil as _psutil  # type: ignore[import]
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False
    log.error("psutil not found. Install via: pip install psutil")


# ─────────────────────────────────────────────────────────────────────────────
# Health checks
# ─────────────────────────────────────────────────────────────────────────────
def read_gateway_state() -> dict:
    """Read gateway_state.json; return {} on missing/corrupt."""
    if not GW_STATE_FILE.exists():
        return {}
    try:
        return json.loads(GW_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Failed to read gateway_state.json: {e}")
        return {}


def pid_alive(pid: int) -> bool:
    """Return True if the PID exists on the system."""
    if not pid:
        return False
    if _HAS_PSUTIL and _psutil is not None:
        return _psutil.pid_exists(int(pid))
    # Fallback: os.kill(pid, 0)
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def check_health() -> tuple[bool, str]:
    """
    Return (healthy: bool, reason: str).
    Healthy = PID alive AND discord.state == "connected".
    """
    state = read_gateway_state()

    if not state:
        return False, "gateway_state.json missing or empty"

    gw_pid = state.get("pid")
    if not gw_pid:
        return False, "no PID in gateway_state.json"

    if not pid_alive(gw_pid):
        return False, f"PID {gw_pid} not alive"

    # Check discord platform state
    platforms = state.get("platforms", {})
    discord   = platforms.get("discord", {})
    dc_state  = discord.get("state", "unknown")

    if dc_state != "connected":
        return False, f"discord.state={dc_state!r} (expected 'connected')"

    # Optionally check telegram too (non-fatal — just log)
    telegram  = platforms.get("telegram", {})
    tg_state  = telegram.get("state", "unknown")
    if tg_state != "connected":
        log.warning(f"Telegram state={tg_state!r} (non-fatal for restart decision)")

    return True, f"PID {gw_pid} alive, discord={dc_state}, telegram={tg_state}"


# ─────────────────────────────────────────────────────────────────────────────
# Gateway restart
# ─────────────────────────────────────────────────────────────────────────────
def kill_stale_gateway() -> None:
    """Kill any stale gateway process from gateway_state.json."""
    state = read_gateway_state()
    gw_pid = state.get("pid")
    if not gw_pid or not pid_alive(gw_pid):
        return
    log.warning(f"Killing stale gateway PID {gw_pid}...")
    try:
        if _HAS_PSUTIL and _psutil is not None:
            proc = _psutil.Process(int(gw_pid))
            proc.terminate()
            gone, alive = _psutil.wait_procs([proc], timeout=5)
            for p in alive:
                p.kill()
        else:
            os.kill(int(gw_pid), 9)
        log.info(f"Stale gateway PID {gw_pid} killed.")
    except Exception as e:
        log.warning(f"Error killing PID {gw_pid}: {e}")


def build_gateway_env() -> dict:
    """Build a clean environment dict for the gateway process."""
    env = dict(os.environ)
    # Apply required vars
    env.update(GW_ENV_VARS)
    # Remove child-context poison vars (set them to empty means they'll be unset below)
    for key in ("HERMES_DELEGATED_CHILD_CONTEXT", "HERMES_IS_CHILD", "HERMES_CHILD_SESSION_ID"):
        env.pop(key, None)
    return env


def launch_gateway() -> bool:
    """
    Start the gateway as a detached subprocess.
    Returns True if process was spawned (not necessarily healthy yet).
    """
    cmd = [PYTHON_EXE, "-m", GW_MODULE] + GW_ARGS
    env = build_gateway_env()

    log.info(f"Launching gateway: {' '.join(cmd)}")
    log.info(f"  WorkDir: {GW_WORKDIR}")

    # Ensure log dir exists
    GW_LOG_DIR.mkdir(parents=True, exist_ok=True)
    gw_stdout = str(GW_LOG_DIR / "gateway_restart_stdout.log")
    gw_stderr = str(GW_LOG_DIR / "gateway_restart_stderr.log")

    try:
        with open(gw_stdout, "a", encoding="utf-8") as fout, \
             open(gw_stderr, "a", encoding="utf-8") as ferr:
            proc = subprocess.Popen(
                cmd,
                cwd=GW_WORKDIR,
                env=env,
                stdout=fout,
                stderr=ferr,
                # Windows: CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                creationflags=0x00000200 | 0x00000008,
                close_fds=True,
            )
        log.info(f"Gateway spawned with PID {proc.pid}")
        return True
    except Exception as e:
        log.error(f"Failed to launch gateway: {e}")
        return False


def restart_gateway() -> bool:
    """Kill stale process, launch fresh gateway. Returns True on success."""
    kill_stale_gateway()
    time.sleep(2)

    spawned = launch_gateway()
    if not spawned:
        return False

    # Wait for gateway to become healthy
    log.info(f"Waiting {STARTUP_GRACE_S}s for gateway to become healthy...")
    deadline = time.monotonic() + STARTUP_GRACE_S
    while time.monotonic() < deadline:
        time.sleep(5)
        healthy, reason = check_health()
        if healthy:
            log.info(f"Gateway healthy after restart: {reason}")
            return True

    log.warning("Gateway did not become healthy within grace period.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Discord notification
# ─────────────────────────────────────────────────────────────────────────────
def notify_discord(message: str) -> None:
    """Send a notification to Discord via hermes CLI (best-effort)."""
    try:
        hermes_candidates = [
            HERMES_EXE,
            str(HERMES_VENV / "Scripts" / "hermes"),
        ]
        hermes_bin = None
        for h in hermes_candidates:
            if Path(h).exists():
                hermes_bin = h
                break

        if not hermes_bin:
            log.warning("hermes binary not found — skipping Discord notification")
            return

        subprocess.Popen(
            [hermes_bin, "-p", "chief_of_staff", "send", "--to", "discord", message],
            env=build_gateway_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000200 | 0x00000008,
        )
        log.info("Discord notification sent.")
    except Exception as e:
        log.warning(f"Discord notification failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Watchdog state file (for gateway_health.py to inspect)
# ─────────────────────────────────────────────────────────────────────────────
WATCHDOG_STATE_FILE = PROFILE_DIR / "gateway_watchdog_state.json"


def write_watchdog_state(extra: dict | None = None) -> None:
    """Write watchdog PID and last heartbeat to a state file."""
    state = {
        "pid":            os.getpid(),
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        state.update(extra)
    try:
        WATCHDOG_STATE_FILE.write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning(f"Could not write watchdog state: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    log.info("=" * 60)
    log.info("Hermes Gateway Watchdog starting")
    log.info(f"  PID:             {os.getpid()}")
    log.info(f"  Gateway state:   {GW_STATE_FILE}")
    log.info(f"  Check interval:  {CHECK_INTERVAL_S}s")
    log.info(f"  Restart cap:     {RESTART_STORM_CAP}/hour")
    log.info("=" * 60)

    write_watchdog_state({"status": "starting"})

    # Restart history: deque of timestamps for storm detection
    restart_times: deque = deque()
    storm_pause_until: float = 0.0

    consecutive_unhealthy: int = 0
    last_heartbeat: float = 0.0

    while True:
        now = time.monotonic()

        # ── Heartbeat log ──────────────────────────────────────────────────
        if now - last_heartbeat >= HEARTBEAT_EVERY_S:
            healthy, reason = check_health()
            log.info(f"[HEARTBEAT] Gateway {'healthy' if healthy else 'unhealthy'}: {reason}")
            write_watchdog_state({"status": "healthy" if healthy else "unhealthy"})
            last_heartbeat = now

        # ── Health check ───────────────────────────────────────────────────
        try:
            healthy, reason = check_health()
        except Exception as e:
            log.error(f"Health check raised exception: {e}")
            healthy, reason = False, f"exception: {e}"

        if healthy:
            if consecutive_unhealthy > 0:
                log.info(f"Gateway recovered after {consecutive_unhealthy} unhealthy check(s).")
            consecutive_unhealthy = 0
        else:
            consecutive_unhealthy += 1
            log.warning(
                f"Gateway unhealthy ({consecutive_unhealthy}/{UNHEALTHY_THRESH}): {reason}"
            )

        # ── Restart decision ───────────────────────────────────────────────
        if consecutive_unhealthy >= UNHEALTHY_THRESH:
            # Check storm protection
            now_real = time.time()
            if storm_pause_until and now_real < storm_pause_until:
                remaining = int(storm_pause_until - now_real)
                log.warning(
                    f"Restart storm pause active — {remaining}s remaining. Skipping restart."
                )
                consecutive_unhealthy = 0
            else:
                # Prune restart timestamps older than 1 hour
                cutoff = now_real - 3600
                while restart_times and restart_times[0] < cutoff:
                    restart_times.popleft()

                if len(restart_times) >= RESTART_STORM_CAP:
                    log.error(
                        f"restart storm detected — {len(restart_times)} restarts in the last hour. "
                        f"Pausing restart attempts for {RESTART_STORM_WAIT}s."
                    )
                    notify_discord(
                        f"⚠️ Watchdog: restart storm detected ({len(restart_times)} restarts/hour). "
                        f"Pausing for {RESTART_STORM_WAIT // 60} minutes."
                    )
                    storm_pause_until = now_real + RESTART_STORM_WAIT
                    consecutive_unhealthy = 0
                else:
                    log.error(
                        f"Gateway unhealthy for {consecutive_unhealthy} consecutive checks. "
                        f"Initiating restart (attempt #{len(restart_times) + 1} this hour)..."
                    )
                    notify_discord(
                        f"🔄 Watchdog: Gateway unhealthy ({reason}). Restarting... "
                        f"(restart #{len(restart_times) + 1}/hr)"
                    )

                    restart_times.append(now_real)
                    success = restart_gateway()

                    if success:
                        log.info("Gateway restarted successfully.")
                        notify_discord("✅ Watchdog: Gateway restarted and healthy.")
                    else:
                        log.error("Gateway restart failed — will retry next cycle.")
                        notify_discord("❌ Watchdog: Gateway restart failed. Will retry.")

                    consecutive_unhealthy = 0

        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Watchdog interrupted by user.")
    except Exception as exc:
        log.exception(f"Watchdog crashed: {exc}")
        sys.exit(1)

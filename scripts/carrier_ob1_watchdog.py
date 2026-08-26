"""OB1 Fleet Brain watchdog — no agent, stdlib only.

Starts the OB1 brain process if not running.
Prints OB1_UP (already running) or OB1_STARTED (just launched) to stdout.
Designed to be called from cron, Hermes, or any watcher.

Usage:
    python scripts/carrier_ob1_watchdog.py [--dry-run]

No external dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent
START_SCRIPT = SCRIPTS_DIR / "start_ob1_brain.py"
PID_FILE = Path("C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.pid")
LOG_DIR = Path("C:/Users/micha/AppData/Local/hermes/carrier/logs")
START_LOG = LOG_DIR / "ob1_watchdog.log"

PYTHON = sys.executable  # use same Python that runs this watchdog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [watchdog] {msg}"
    # Write to log file only — keep stdout clean for hash-suppression
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with START_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _process_alive(pid: int) -> bool:
    """Return True if a process with the given PID is running."""
    try:
        # Windows: tasklist
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in r.stdout
    except Exception:
        # POSIX fallback
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _is_ob1_running() -> bool:
    """Check if OB1 brain is already running via PID file."""
    pid = _read_pid()
    if pid is None:
        return False
    if _process_alive(pid):
        return True
    # Stale PID
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return False


def _start_ob1(dry_run: bool = False) -> int | None:
    """Launch the OB1 brain process. Returns its PID."""
    if dry_run:
        _log(f"DRY RUN: would launch: {PYTHON} {START_SCRIPT}")
        return None

    if not START_SCRIPT.exists():
        _log(f"ERROR: start script not found: {START_SCRIPT}")
        return None

    # Launch detached so watchdog can exit
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_out = open(LOG_DIR / "ob1_brain_stdout.log", "a", encoding="utf-8")
    log_err = open(LOG_DIR / "ob1_brain_stderr.log", "a", encoding="utf-8")

    proc = subprocess.Popen(
        [PYTHON, str(START_SCRIPT)],
        stdout=log_out,
        stderr=log_err,
        close_fds=True,
        # On Windows, CREATE_NEW_PROCESS_GROUP keeps it independent
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    _write_pid(proc.pid)
    _log(f"Started OB1 brain (PID={proc.pid})")
    return proc.pid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OB1 fleet brain watchdog")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, don't act")
    args = parser.parse_args()

    if _is_ob1_running():
        pid = _read_pid()
        _log(f"OB1 fleet brain already running (PID={pid})")
        print("OB1_UP", flush=True)
        sys.exit(0)

    _log("OB1 fleet brain not running — starting …")
    pid = _start_ob1(dry_run=args.dry_run)

    if pid:
        # Brief pause to let it initialise
        time.sleep(2)
        if _process_alive(pid):
            _log(f"OB1 fleet brain started successfully (PID={pid})")
            print("OB1_STARTED", flush=True)
            sys.exit(0)
        else:
            _log(f"OB1 fleet brain process died immediately (PID={pid})")
            print("OB1_START_FAILED", flush=True)
            sys.exit(1)
    elif args.dry_run:
        print("OB1_STARTED (dry-run)", flush=True)
    else:
        print("OB1_START_FAILED", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

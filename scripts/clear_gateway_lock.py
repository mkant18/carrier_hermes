#!/usr/bin/env python3
"""
clear_gateway_lock.py — Safe dispatcher lock cleanup utility
============================================================
Checks whether the dispatcher lock exists and, if so, whether the owner
process is still alive. Deletes stale locks. Refuses to delete live locks.

OUTPUTS (stdout):
  LOCK_CLEARED        — lock existed and was stale; removed successfully
  LOCK_HELD_BY_PID_N  — lock exists and owner is alive; not removed
  LOCK_NOT_FOUND      — no lock file exists

USAGE:
  python clear_gateway_lock.py [--board carrier]
  python clear_gateway_lock.py --force   (skip liveness check — dangerous)
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
HERMES_HOME  = Path(LOCALAPPDATA) / "hermes"

# Default: kanban-level dispatcher lock
DEFAULT_LOCK = HERMES_HOME / "kanban" / ".dispatcher.lock"
# Board-level locks
BOARD_LOCKS  = {
    "carrier": HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db.dispatch.lock",
    "default": HERMES_HOME / "kanban" / "kanban.db.dispatch.lock",
}


def _pid_alive(pid: int) -> bool:
    """Return True if the given PID is alive."""
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _read_lock_pid(lock_path: Path):
    """Extract PID from lock file. Returns int or None."""
    try:
        content = lock_path.read_text(encoding="utf-8", errors="replace").strip()
        # Try JSON format first
        try:
            d = json.loads(content)
            pid = d.get("pid") or d.get("dispatcher_pid")
            if pid:
                return int(pid)
        except (json.JSONDecodeError, ValueError):
            pass
        # Plain integer
        if content.isdigit():
            return int(content)
        return None
    except Exception:
        return None


def check_and_clear(lock_path: Path, force: bool = False) -> str:
    """Check a single lock file and clear it if stale. Returns status string."""
    if not lock_path.exists():
        return f"LOCK_NOT_FOUND: {lock_path.name}"

    if force:
        lock_path.unlink()
        return f"LOCK_CLEARED (forced): {lock_path}"

    pid = _read_lock_pid(lock_path)

    if pid is None:
        # Unreadable or zero-byte lock — treat as stale
        lock_path.unlink()
        return f"LOCK_CLEARED (unreadable): {lock_path}"

    if _pid_alive(pid):
        return f"LOCK_HELD_BY_PID_{pid}: {lock_path.name}"
    else:
        lock_path.unlink()
        return f"LOCK_CLEARED (stale PID {pid}): {lock_path}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clear stale Hermes dispatcher locks.")
    parser.add_argument("--board", default=None, help="Board name (carrier, default) or 'all'")
    parser.add_argument("--force", action="store_true", help="Delete lock regardless of owner liveness")
    args = parser.parse_args()

    locks_to_check = []

    if args.board == "all":
        locks_to_check.append(DEFAULT_LOCK)
        locks_to_check.extend(BOARD_LOCKS.values())
    elif args.board and args.board in BOARD_LOCKS:
        locks_to_check.append(BOARD_LOCKS[args.board])
    else:
        # Default: check the main kanban dispatcher lock
        locks_to_check.append(DEFAULT_LOCK)

    any_held    = False
    any_cleared = False
    results     = []

    for lock in locks_to_check:
        result = check_and_clear(lock, force=args.force)
        results.append(result)
        if "LOCK_HELD" in result:
            any_held = True
        elif "LOCK_CLEARED" in result:
            any_cleared = True

    for r in results:
        print(r)

    # Single-word summary for cron-style callers
    if any_held:
        # Print the full LOCK_HELD_BY_PID_N for the first held lock
        for r in results:
            if "LOCK_HELD" in r:
                # Extract just PID summary
                parts = r.split(":")
                summary = parts[0].strip()
                print(summary)
                break
    elif any_cleared:
        print("LOCK_CLEARED")
    else:
        print("LOCK_NOT_FOUND")


if __name__ == "__main__":
    main()

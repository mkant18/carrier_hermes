#!/usr/bin/env python3
"""
maintenance_preflight.py — Shipwright Wing availability gate.

Runs before every maintenance cron tick as a monitor_script.
Hermes hashes stdout each tick; identical output suppresses the agent turn.
All output is deterministic — no timestamps, no random data.

Exit 0 : all conditions met → agent fires
Exit 1 : suppressed      → cron hash-suppresses the agent turn
"""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

# ─── Configuration ────────────────────────────────────────────────────────────

HERMES_HOME = r"C:\Users\micha\AppData\Local\hermes"
PROFILES_DIR = os.path.join(HERMES_HOME, "profiles")
CARRIER_DIR  = os.path.join(HERMES_HOME, "carrier")

DISPATCH_LOCK = os.path.join(CARRIER_DIR, "DISPATCH_LOCK")
SPEND_HALT    = os.path.join(CARRIER_DIR, "SPEND_HALT")

OLLAMA_URL    = "http://localhost:11434/api/tags"
REQUIRED_MODEL = "qwen2.5:7b-instruct-q4_K_M"

MAINTENANCE_PROFILE = "maintenance_lt"
MAINTENANCE_DB      = os.path.join(PROFILES_DIR, MAINTENANCE_PROFILE, "state.db")

# All 5 Shipwright wing bots — used for kanban in-progress check
SHIPWRIGHT_BOTS = {
    "maintenance_lt",
    "code_auditor",
    "repair_planner",
    "patch_writer",
    "pr_reviewer",
}

KANBAN_DB = os.path.join(HERMES_HOME, "kanban", "boards", "carrier", "kanban.db")

# Fleet-quiet threshold: suppress if >= this many active sessions across all profiles
FLEET_ACTIVE_THRESHOLD = 5
FLEET_WINDOW_SECONDS   = 15 * 60   # 15 minutes

# In-progress session window for maintenance_lt (suppress if active within this)
MAINTENANCE_ACTIVE_WINDOW = 30 * 60  # 30 minutes

# Rate-limit keywords to detect in session end_reason / handoff_error
RATE_LIMIT_KEYWORDS = ("rate_limit", "rate-limit", "429", "quota", "overloaded", "too_many_requests")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def suppress(reason: str) -> None:
    """Print stable suppression line and exit 1."""
    print(f"SUPPRESSED: {reason}", flush=True)
    sys.exit(1)


def db_connect(path: str) -> sqlite3.Connection | None:
    """Open a SQLite DB read-only; return None if file missing or unreadable."""
    if not os.path.exists(path):
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return None


# ─── Check 1: Ollama running and required model available ─────────────────────

def check_ollama() -> None:
    try:
        req = urllib.request.Request(OLLAMA_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
    except urllib.error.URLError:
        suppress("ollama_unavailable")
    except Exception:
        suppress("ollama_unavailable")

    models = body.get("models", [])
    names  = [m.get("name", "") for m in models]
    # Model names may appear as "qwen2.5:7b-instruct-q4_K_M" or include a digest suffix;
    # match on prefix so both forms work.
    if not any(n == REQUIRED_MODEL or n.startswith(REQUIRED_MODEL + ":") for n in names):
        suppress("ollama_model_missing")


# ─── Check 2 & 3: DISPATCH_LOCK / SPEND_HALT absent ──────────────────────────

def check_lock_files() -> None:
    if os.path.exists(DISPATCH_LOCK):
        suppress("dispatch_lock_present")
    if os.path.exists(SPEND_HALT):
        suppress("spend_halt_present")


# ─── Check 4: No in-progress Shipwright Kanban task ───────────────────────────

def check_maintenance_not_running() -> None:
    """
    Suppress if any Shipwright wing bot currently has an in_progress Kanban task.
    Also suppresses if maintenance_lt has an active session in the last 30 minutes
    (covers the case where the kanban task was claimed but DB not yet updated).
    """
    # 4a: Kanban DB — any in_progress task assigned to a wing bot?
    if os.path.exists(KANBAN_DB):
        con = db_connect(KANBAN_DB)
        if con:
            try:
                placeholders = ",".join("?" * len(SHIPWRIGHT_BOTS))
                cur = con.execute(
                    f"SELECT COUNT(*) FROM tasks WHERE status='in_progress' AND assignee IN ({placeholders})",
                    tuple(SHIPWRIGHT_BOTS),
                )
                count = cur.fetchone()[0]
            except Exception:
                count = 0
            finally:
                con.close()
            if count > 0:
                suppress("maintenance_task_in_progress")

    # 4b: maintenance_lt state.db — any session active in last 30 min?
    con = db_connect(MAINTENANCE_DB)
    if con:
        try:
            cutoff = time.time() - MAINTENANCE_ACTIVE_WINDOW
            cur = con.execute(
                """SELECT COUNT(*) FROM sessions
                   WHERE ended_at IS NULL
                      OR last_activity_at > ?""",
                (cutoff,),
            )
            count = cur.fetchone()[0]
        except Exception:
            count = 0
        finally:
            con.close()
        if count > 0:
            suppress("maintenance_session_active")


# ─── Check 5: Fleet quiet (< 5 active bot sessions across all profiles) ───────

def check_fleet_quiet() -> None:
    cutoff = time.time() - FLEET_WINDOW_SECONDS
    total_active = 0

    if not os.path.isdir(PROFILES_DIR):
        return  # Can't check → allow (fail-open for fleet quiet)

    for profile in os.listdir(PROFILES_DIR):
        db_path = os.path.join(PROFILES_DIR, profile, "state.db")
        con = db_connect(db_path)
        if con is None:
            continue
        try:
            cur = con.execute(
                """SELECT COUNT(*) FROM sessions
                   WHERE (ended_at IS NULL OR last_activity_at > ?)
                     AND hidden = 0""",
                (cutoff,),
            )
            total_active += cur.fetchone()[0]
        except Exception:
            pass
        finally:
            con.close()

    if total_active >= FLEET_ACTIVE_THRESHOLD:
        suppress("fleet_busy")


# ─── Check 6: Anthropic not rate-limited in maintenance_lt ───────────────────

def check_not_rate_limited() -> None:
    """
    Suppress if the most-recent session in maintenance_lt's state.db ended
    with a rate-limit-like error (end_reason or handoff_error contains known keywords).
    """
    con = db_connect(MAINTENANCE_DB)
    if con is None:
        return  # No DB yet — allow (first run)

    try:
        cur = con.execute(
            """SELECT end_reason, handoff_error
               FROM sessions
               WHERE ended_at IS NOT NULL
               ORDER BY ended_at DESC
               LIMIT 1"""
        )
        row = cur.fetchone()
    except Exception:
        row = None
    finally:
        con.close()

    if row is None:
        return  # No completed sessions → allow

    end_reason, handoff_error = row
    combined = " ".join(filter(None, [end_reason, handoff_error])).lower()

    if any(kw in combined for kw in RATE_LIMIT_KEYWORDS):
        suppress("anthropic_rate_limited")


# ─── Eligible-cycle counter (hash-suppression guard) ─────────────────────────

def _eligible_cycle() -> int:
    """Return an incrementing integer so each eligible tick produces unique stdout.

    Hermes monitor_script hashes stdout each tick; identical output permanently
    suppresses the agent turn.  A stable 'PREFLIGHT: OK' would fire the LLM once
    then suppress it forever.  This counter ensures every eligible tick differs.
    State persists in CARRIER_DIR so the counter survives across cron invocations.
    """
    cycle_file = os.path.join(CARRIER_DIR, "maintenance_preflight_cycle.txt")
    try:
        if os.path.exists(cycle_file):
            with open(cycle_file, "r") as fh:
                cycle = int(fh.read().strip())
        else:
            cycle = 0
        cycle += 1
        with open(cycle_file, "w") as fh:
            fh.write(str(cycle))
        return cycle
    except (IOError, OSError, ValueError):
        # Fallback: current epoch seconds always changes between ticks.
        return int(time.time())


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    check_ollama()
    check_lock_files()
    check_maintenance_not_running()
    check_fleet_quiet()
    check_not_rate_limited()

    # All checks passed — emit a CHANGING token so Hermes does not hash-suppress
    # this tick and permanently silence the maintenance agent.
    print(f"PREFLIGHT: OK cycle={_eligible_cycle()}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()

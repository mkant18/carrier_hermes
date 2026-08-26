#!/usr/bin/env python3
"""silent_running_ladder.py — zero-LLM tier inspector for Silent Running.

Reports which of the six Silent Running priority tiers currently has work, so
Helm (OAuth, high-level) can pick the HIGHEST non-empty tier and delegate one
throttled unit of work to the local-LLM workers.

The seven tiers (fixed priority, highest first):
  1. BACKLOG      — clear active Kanban tasks (all wings)
  2. MAINTENANCE  — Shipwright pipeline; coding + research wings ASSIST
  3. MEMORY       — agent-memory optimization (OpenViking L0/L1/L2 concept)
  4. CLEANING     — remove stale / temp / unused artifacts
  5. TRENDS       — identify patterns: frequent bot stalls, billing/usage trends.
                    OAuth-tier work: Helm + LTs on Sonnet/Opus (subscription OAuth
                    ONLY — never OpenRouter). This tier is the exception to the
                    "primarily local LLM" rule because it is high-level analysis.
  6. TRAINING     — self-optimize from last-48h corrections + optimal production
  7. FEATURES     — research trending repos → plan → Marshal subtasks → dev cycle

Tiers 1 & 2 have HARD countable signals from the Kanban DB. Tiers 3–6 are
standing work that is always available once the higher tiers are clear; for those
we surface freshness signals (last-run timestamps from the state file) so Helm can
judge whether the tier is "due" and avoid re-doing recently-completed work.

Usage:
    python silent_running_ladder.py            # human-readable + JSON
    python silent_running_ladder.py --json     # JSON only (for Helm to parse)

ZERO-LLM. Safe from cron / no_agent contexts. Spends no tokens.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time

import silent_running_common as C

# Statuses that count as "actionable backlog" for a normal work bot.
BACKLOG_STATUSES = ("ready", "todo")
# Shipwright maintenance wing bots (their open tasks == maintenance in flight).
SHIPWRIGHT_BOTS = ("maintenance_lt", "code_auditor", "repair_planner",
                   "patch_writer", "pr_reviewer")

# Freshness windows: a standing tier is "due" if it hasn't run within this.
DUE_WINDOWS_S = {
    "memory":    24 * 3600,   # optimize Hermes memory stores ~daily
    "omb_audit": 12 * 3600,   # OMB bot health audit + hardening ~twice daily
    "cleaning":  24 * 3600,   # sweep stale artifacts ~daily
    "trends":    24 * 3600,   # trend analysis ~daily (OAuth-tier: Helm + LTs)
    "training":  48 * 3600,   # 48h corrections review window (per Michael)
    "features":  72 * 3600,   # feature scouting every ~3 days
}


def _q(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def inspect_kanban() -> dict:
    """Count backlog and maintenance work from the carrier Kanban DB."""
    out = {
        "backlog_count": 0,
        "backlog_tasks": [],
        "maintenance_open": 0,
        "maintenance_tasks": [],
        "running_count": 0,
        "blocked_count": 0,
    }
    if not C.KANBAN_DB.exists():
        return out
    conn = sqlite3.connect(f"file:{C.KANBAN_DB}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        ph = ",".join("?" * len(BACKLOG_STATUSES))
        # Tier 1: actionable backlog for NON-maintenance bots.
        mp = ",".join("?" * len(SHIPWRIGHT_BOTS))
        rows = _q(conn,
            f"SELECT id, assignee, status, priority, substr(title,1,60) AS t "
            f"FROM tasks WHERE status IN ({ph}) AND assignee NOT IN ({mp}) "
            f"ORDER BY priority ASC, created_at ASC",
            (*BACKLOG_STATUSES, *SHIPWRIGHT_BOTS))
        out["backlog_count"] = len(rows)
        out["backlog_tasks"] = [dict(r) for r in rows[:15]]

        # Tier 2: open maintenance (Shipwright) tasks in any live state.
        rows = _q(conn,
            f"SELECT id, assignee, status, substr(title,1,60) AS t "
            f"FROM tasks WHERE assignee IN ({mp}) "
            f"AND status IN ('ready','todo','running','blocked') "
            f"ORDER BY created_at ASC", SHIPWRIGHT_BOTS)
        out["maintenance_open"] = len(rows)
        out["maintenance_tasks"] = [dict(r) for r in rows[:15]]

        out["running_count"] = len(_q(conn,
            "SELECT id FROM tasks WHERE status='running'"))
        out["blocked_count"] = len(_q(conn,
            "SELECT id FROM tasks WHERE status='blocked'"))
    finally:
        conn.close()
    return out


def standing_tier_status(state: dict) -> dict:
    """Freshness for the standing tiers (3–6) from the state file's run log."""
    now = time.time()
    runs = state.get("tier_last_run", {}) if isinstance(state, dict) else {}
    out = {}
    for name, window in DUE_WINDOWS_S.items():
        last = runs.get(name)
        due = (last is None) or ((now - last) >= window)
        out[name] = {
            "last_run_at": last,
            "age_hours": None if last is None else round((now - last) / 3600, 1),
            "due": due,
        }
    return out


def build_report() -> dict:
    cap = C.read_capacity()
    state = C.read_state()
    kb = inspect_kanban()
    standing = standing_tier_status(state)

    # Determine the top non-empty tier. Higher tiers strictly win.
    top = None
    if kb["backlog_count"] > 0:
        top = 1
    elif kb["maintenance_open"] > 0:
        top = 2
    elif standing["memory"]["due"]:
        top = 3
    elif standing["omb_audit"]["due"]:
        top = 4
    elif standing["cleaning"]["due"]:
        top = 5
    elif standing["trends"]["due"]:
        top = 6
    elif standing["training"]["due"]:
        top = 7
    elif standing["features"]["due"]:
        top = 8
    # If everything is clear and nothing is due, Helm holds (top=None → idle).

    tier_names = {1: "backlog", 2: "maintenance", 3: "memory",
                  4: "omb_audit", 5: "cleaning", 6: "trends",
                  7: "training", 8: "features"}

    return {
        "generated_at": int(time.time()),
        "phase": state.get("phase"),
        "capacity": cap,
        "gates": {
            "idle_ok": cap["idle_ok"],
            "headroom_ok": cap["headroom_ok"],
            "ceiling_ok": cap["ceiling_ok"],
            "lock": C.locks_present(),
            "ollama_ready": C.ollama_ready(),
        },
        "kanban": kb,
        "standing": standing,
        "top_tier": top,
        "top_tier_name": tier_names.get(top) if top is not None else None,
        "concurrency": {
            "max_units": C.MAX_CONCURRENT_UNITS,
            "running_units": kb["running_count"],
            "spawn_allowed": (
                cap["ceiling_ok"]
                and kb["running_count"] < C.MAX_CONCURRENT_UNITS
                and C.locks_present() is None
                and not C.brake_present()
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    c = report["capacity"]
    g = report["gates"]
    kb = report["kanban"]
    print("=== Silent Running — Ladder Inspector ===")
    print(f"phase={report['phase']}  top_tier={report['top_tier']} "
          f"({report['top_tier_name']})")
    print(f"capacity: cpu={c['cpu']}%  gpu={c['gpu']}%  idle={c['idle_s']}s")
    print(f"gates: idle_ok={g['idle_ok']} headroom_ok={c['headroom_ok']} "
          f"ceiling_ok={c['ceiling_ok']} lock={g['lock']} "
          f"ollama={g['ollama_ready']}")
    print(f"tier1 backlog     : {kb['backlog_count']} task(s)")
    print(f"tier2 maintenance : {kb['maintenance_open']} open task(s)")
    for name in ("memory", "omb_audit", "cleaning", "trends", "training", "features"):
        s = report["standing"][name]
        age = "never" if s["last_run_at"] is None else f"{s['age_hours']}h ago"
        print(f"tier {name:9}: due={s['due']} (last: {age})")
    print(f"concurrency: {kb['running_count']}/{report['concurrency']['max_units']} "
          f"units  spawn_allowed={report['concurrency']['spawn_allowed']}")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

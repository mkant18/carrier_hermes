#!/usr/bin/env python3
"""
helm_input_watchdog.py — Monitor script for the Helm Human-Input Resolver cron.

Runs as a `monitor_script` (no_agent=True compatible) every N minutes.
Stable output → hash-suppressed (agent not triggered).
Changed output → agent wakes up to dispatch Probe or resolve completed research.

Exit codes:
  0  — normal (stdout may be empty = no change, or JSON = changes detected)
  1  — fatal error (written to stderr)
"""

import json
import sqlite3
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
HERMES_HOME  = Path(r"C:\Users\micha\AppData\Local\hermes")
KANBAN_DB    = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"
CARRIER_DIR  = HERMES_HOME / "carrier"
QUEUE_FILE   = CARRIER_DIR / "human_input_queue.json"
RESPONSE_DIR = CARRIER_DIR / "human_input_responses"

# A task must be blocked for this many seconds before we escalate.
THRESHOLD_SECONDS = 3600  # 1 hour

# ── Helpers ─────────────────────────────────────────────────────────────────

def load_queue() -> dict:
    """Load the persistent escalation queue. Returns {} if missing."""
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def overdue_blocked_tasks(conn: sqlite3.Connection, now: int) -> list[dict]:
    """
    Return tasks that are:
      - status='blocked', block_kind='needs_input'
      - The most recent run ended at least THRESHOLD_SECONDS ago
        (falls back to started_at, then created_at if no run exists)

    Each dict: {id, title, assignee, body, summary, blocked_since, age_h}
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id,
               t.title,
               t.assignee,
               SUBSTR(t.body, 1, 4000)                AS body_excerpt,
               r.ended_at,
               r.summary,
               t.started_at,
               t.created_at
        FROM   tasks t
        LEFT JOIN task_runs r
               ON r.id = (
                   SELECT id FROM task_runs
                   WHERE task_id = t.id
                   ORDER BY started_at DESC LIMIT 1
               )
        WHERE  t.status     = 'blocked'
        AND    t.block_kind = 'needs_input'
    """)
    rows = cur.fetchall()

    result = []
    for (tid, title, assignee, body, ended_at, summary,
         started_at, created_at) in rows:
        blocked_since = ended_at or started_at or created_at or now
        age_h = (now - blocked_since) / 3600
        if blocked_since <= now - THRESHOLD_SECONDS:
            result.append({
                "id":            tid,
                "title":         title,
                "assignee":      assignee,
                "body_excerpt":  body or "",
                "summary":       summary or "",
                "blocked_since": blocked_since,
                "age_h":         round(age_h, 1),
            })
    return result


def main():
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
    now   = int(time.time())
    queue = load_queue()

    if not KANBAN_DB.exists():
        print(json.dumps({"needs_dispatch": [], "research_complete": []}))
        return

    conn = sqlite3.connect(str(KANBAN_DB))
    try:
        overdue = overdue_blocked_tasks(conn, now)
    finally:
        conn.close()

    # Tasks not yet in queue → need dispatch
    needs_dispatch = [
        t for t in overdue
        if t["id"] not in queue
        or queue[t["id"]].get("status") not in ("dispatched", "resolved")
    ]

    # Tasks dispatched → check if Probe wrote a response file
    research_complete = []
    for tid, entry in queue.items():
        if entry.get("status") == "dispatched":
            resp = RESPONSE_DIR / f"{tid}.json"
            if resp.exists():
                try:
                    data = json.loads(resp.read_text(encoding="utf-8"))
                    research_complete.append({
                        "id":               tid,
                        "title":            entry.get("title", ""),
                        "assignee":         entry.get("assignee", ""),
                        "recommendation":   data.get("recommendation", ""),
                        "confidence":       data.get("confidence", "medium"),
                        "research_summary": data.get("research_summary", ""),
                    })
                except Exception as exc:
                    # Malformed response — leave for next run
                    import sys
                    print(f"[watchdog] malformed response for {tid}: {exc}",
                          file=sys.stderr)

    output = {
        "needs_dispatch":    needs_dispatch,
        "research_complete": research_complete,
    }

    if needs_dispatch or research_complete:
        print(json.dumps(output, ensure_ascii=False))
    else:
        # Stable empty output → monitor hash unchanged → agent not triggered
        print(json.dumps({"needs_dispatch": [], "research_complete": []}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
coding_stall_watcher.py — Zero-LLM stall detector for the Coding Wing.

Runs as a no_agent=True cron every 30 minutes. Queries the carrier Kanban DB
for Mate tasks that have been running or blocked for > 30 minutes, then writes
an AIPass message to Wrench's inbox so Wrench can diagnose and unblock.

stdout contract (for cron hash-suppression):
  - No stalls: prints nothing → cron is silent (no delivery)
  - Stalls found: prints a one-line summary per stall → cron delivers to Wrench's bot-chat
"""

import sqlite3
import time
import json
import os
from pathlib import Path
from datetime import datetime, timezone

CARRIER_DB  = Path(r"C:\Users\micha\AppData\Local\hermes\kanban\boards\carrier\kanban.db")
WRENCH_INBOX = Path(r"C:\Users\micha\AppData\Local\hermes\profiles\coding_lt\home\_agent\mailbox\coding_lt\inbox")
MATE_LOG     = Path(r"C:\Users\micha\AppData\Local\hermes\profiles\firstmate\logs\agent.log")
STALL_MINUTES = 30
STALL_SECONDS = STALL_MINUTES * 60


def get_stalled_tasks():
    if not CARRIER_DB.exists():
        return []
    conn = sqlite3.connect(str(CARRIER_DB))
    threshold = int(time.time()) - STALL_SECONDS
    rows = conn.execute(
        "SELECT id, title, status, assignee, started_at, last_failure_error, consecutive_failures "
        "FROM tasks "
        "WHERE assignee='firstmate' "
        "AND status IN ('running', 'blocked') "
        "AND started_at IS NOT NULL "
        "AND started_at < ?",
        (threshold,)
    ).fetchall()
    conn.close()
    return rows


def get_mate_log_tail(lines=30):
    if not MATE_LOG.exists():
        return "(agent.log not found)"
    try:
        text = MATE_LOG.read_text(encoding="utf-8", errors="replace")
        tail = text.splitlines()[-lines:]
        return "\n".join(tail)
    except Exception as e:
        return f"(could not read agent.log: {e})"


def write_aipass(stalled_tasks):
    WRENCH_INBOX.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = WRENCH_INBOX / f"{ts}-stall-watcher-alert.md"

    task_lines = []
    for tid, title, status, assignee, started_at, last_error, failures in stalled_tasks:
        age_min = int((time.time() - started_at) / 60) if started_at else 0
        task_lines.append(
            f"- **{tid}** | `{status}` | {age_min}min stalled | failures={failures}\n"
            f"  Title: {title}\n"
            f"  Last error: {(last_error or 'none')[:200]}"
        )

    log_tail = get_mate_log_tail()
    body = "\n".join(task_lines)

    content = f"""---
from: coding_stall_watcher
to: coding_lt
type: stall_alert
status: unread
stalled_count: {len(stalled_tasks)}
generated_at: {ts}
---

## ⚠️ Stall Alert — {len(stalled_tasks)} Mate task(s) stalled > {STALL_MINUTES} minutes

{body}

---

### Mate agent.log tail (last 30 lines)

```
{log_tail}
```

---

**Recommended action:** Review each stalled task. Write a clarifying AIPass to Mate's inbox
and reset the task to `ready`, or escalate to Helm if a human gate is required.

Kanban DB: `{CARRIER_DB}`
Reset command (per task):
```python
import sqlite3
conn = sqlite3.connect(r'{CARRIER_DB}')
conn.execute("UPDATE tasks SET status='ready', consecutive_failures=0, last_failure_error=NULL WHERE id='<task_id>'")
conn.commit()
```
"""
    fname.write_text(content, encoding="utf-8")
    return fname


def main():
    stalled = get_stalled_tasks()
    if not stalled:
        # Silent — no output → cron hash-suppression keeps this tick quiet
        return

    # Write AIPass to Wrench
    aipass_path = write_aipass(stalled)

    # Print summary — cron delivers this as the message body to Wrench
    print(f"⚠️ STALL ALERT | coding_stall_watcher | {len(stalled)} task(s) stalled > {STALL_MINUTES}min")
    for tid, title, status, assignee, started_at, last_error, failures in stalled:
        age_min = int((time.time() - started_at) / 60) if started_at else 0
        print(f"  • {tid} | {status} | {age_min}min | {title[:60]}")
    print(f"\nAIPass written to Wrench: {aipass_path.name}")
    print("Action required: check coding_lt inbox and diagnose.")


if __name__ == "__main__":
    main()

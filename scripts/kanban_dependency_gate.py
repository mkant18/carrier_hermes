"""
kanban_dependency_gate.py — zero-LLM carrier board dependency promoter.

Runs on a cron schedule (no_agent=True). Checks every task on the carrier board
that is in 'blocked' status and has task_links parents. If ALL parents are in a
terminal state ('done' or 'completed'), promotes the child to 'ready'.

Stdout contract (hash-suppressed by cron):
- PROMOTED lines only when something actually changes
- SUPPRESSED: no_promotions_needed — when nothing to do (stable output = no cron tick)
"""

import sqlite3
import time
import sys

DB = r'C:\Users\micha\AppData\Local\hermes\kanban\boards\carrier\kanban.db'
TERMINAL = {'done', 'completed'}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Find all blocked tasks that have at least one parent link
cur.execute("""
    SELECT DISTINCT t.id, t.title, t.assignee
    FROM tasks t
    JOIN task_links tl ON tl.child_id = t.id
    WHERE t.status = 'blocked'
""")
blocked_with_parents = cur.fetchall()

promoted = []

for task in blocked_with_parents:
    child_id = task['id']

    # Get all parent statuses for this child
    cur.execute("""
        SELECT t.id, t.status
        FROM tasks t
        JOIN task_links tl ON tl.parent_id = t.id
        WHERE tl.child_id = ?
    """, (child_id,))
    parents = cur.fetchall()

    if not parents:
        continue

    all_terminal = all(p['status'] in TERMINAL for p in parents)

    if all_terminal:
        cur.execute("""
            UPDATE tasks
            SET status = 'ready',
                consecutive_failures = 0,
                last_failure_error = NULL,
                started_at = NULL,
                worker_pid = NULL,
                current_run_id = NULL
            WHERE id = ?
        """, (child_id,))
        promoted.append((child_id, task['title'][:60], task['assignee']))
        cur.execute(
            "INSERT INTO task_comments (task_id, body, author, created_at) VALUES (?, ?, ?, ?)",
            (child_id,
             "Auto-promoted to ready: all parent tasks reached terminal state.",
             'kanban_dependency_gate',
             int(time.time()))
        )

conn.commit()
conn.close()

if promoted:
    for task_id, title, assignee in promoted:
        print(f"PROMOTED {task_id} -> ready | {assignee} | {title}")
else:
    print("SUPPRESSED: no_promotions_needed")

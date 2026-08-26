"""
carrier_vm_task_runner.py — Runs Kanban tasks inside bot Docker containers.

Accepts a Kanban task dict, executes it inside the assigned bot's container,
updates the Kanban DB with output, and registers with the carrier-peers broker.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.carrier_vm_manager import (  # noqa: E402
    ensure_bot_vm_running,
    exec_in_bot_vm,
    ALL_BOT_IDS,
)

# ── Constants ────────────────────────────────────────────────────────────────

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
KANBAN_DB = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"
PEERS_BROKER_URL = os.environ.get("CARRIER_PEERS_BROKER_URL", "http://localhost:9876")


# ── Kanban helpers ────────────────────────────────────────────────────────────

def _kanban_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(KANBAN_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _add_task_comment(task_id: str, body: str, author: str = "vm_task_runner") -> None:
    """Append a comment to a Kanban task."""
    try:
        conn = _kanban_connect()
        conn.execute(
            "INSERT INTO task_comments (task_id, body, author, created_at) VALUES (?, ?, ?, ?)",
            (task_id, body[:4000], author, int(time.time())),
        )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[vm_task_runner] Comment write failed for {task_id}: {exc}")


def _update_task_status(task_id: str, status: str, result: str | None = None) -> None:
    """Update task status in Kanban DB."""
    try:
        conn = _kanban_connect()
        if result is not None:
            conn.execute(
                "UPDATE tasks SET status=?, completed_at=?, result=? WHERE id=?",
                (status, int(time.time()), result[:8000], task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status=? WHERE id=?",
                (status, task_id),
            )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[vm_task_runner] Status update failed for {task_id}: {exc}")


def _update_task_running(task_id: str, pid: int = 0) -> None:
    """Mark task as running in Kanban."""
    try:
        conn = _kanban_connect()
        conn.execute(
            "UPDATE tasks SET status='running', started_at=?, worker_pid=? WHERE id=?",
            (int(time.time()), pid, task_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[vm_task_runner] Running update failed for {task_id}: {exc}")


# ── Broker registration ───────────────────────────────────────────────────────

def _register_with_broker(bot_id: str, task_id: str) -> bool:
    """Register this task runner with the carrier-peers broker."""
    payload = json.dumps({
        "bot_id": bot_id,
        "task_id": task_id,
        "registered_at": time.time(),
        "pid": os.getpid(),
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{PEERS_BROKER_URL}/register",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "carrier-vm-task-runner/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as exc:  # noqa: BLE001
        print(f"[vm_task_runner] Broker registration failed: {exc}")
        return False


# ── Worktree mount helper ────────────────────────────────────────────────────

def _build_exec_command(task: dict) -> str:
    """
    Build the shell command to run inside the container.
    If workspace_kind == 'worktree', the worktree path is passed as cwd.
    """
    task_id = task.get("id", "unknown")
    title = task.get("title", "")
    body = task.get("body", "")
    workspace_kind = task.get("workspace_kind", "scratch")
    workspace_path = task.get("workspace_path", "")
    assignee = task.get("assignee", "unknown")

    # Build a safe task description for the agent entrypoint
    task_json = json.dumps({
        "task_id": task_id,
        "title": title,
        "body": body,
        "assignee": assignee,
        "workspace_kind": workspace_kind,
    }, ensure_ascii=False)

    # Escape single quotes for shell
    task_json_escaped = task_json.replace("'", "'\"'\"'")

    if workspace_kind == "worktree" and workspace_path:
        # Convert Windows path to container path
        # Repo is mounted at /repo in the container
        container_path = "/repo"
        if workspace_path and "carrier_hermes" in workspace_path:
            # Try to map worktree path relative to repo
            repo_str = str(REPO_ROOT).replace("\\", "/")
            ws_str = workspace_path.replace("\\", "/")
            if ws_str.startswith(repo_str):
                relative = ws_str[len(repo_str):].lstrip("/")
                container_path = f"/repo/{relative}"

        return (
            f"cd {container_path} && "
            f"echo 'TASK_JSON={task_json_escaped}' > /tmp/task.env && "
            f"python /repo/scripts/run_local.py --task-json '{task_json_escaped}' 2>&1 || "
            f"echo 'Task execution completed with code '$?"
        )
    else:
        return (
            f"echo 'TASK_JSON={task_json_escaped}' > /tmp/task.env && "
            f"python /repo/scripts/run_local.py --task-json '{task_json_escaped}' 2>&1 || "
            f"echo 'Task execution completed with code '$?"
        )


# ── Main entry point ──────────────────────────────────────────────────────────

def run_task_in_vm(task: dict) -> dict:
    """
    Run a Kanban task inside its assigned bot's Docker container.

    Args:
        task: Kanban task dict with keys: id, title, body, assignee,
              workspace_kind, workspace_path, priority, etc.

    Returns:
        {
            'success': bool,
            'task_id': str,
            'bot_id': str,
            'returncode': int,
            'output': str,
        }
    """
    task_id = task.get("id", "unknown")
    bot_id = task.get("assignee", "")

    if not bot_id or bot_id not in ALL_BOT_IDS:
        msg = f"Unknown or missing assignee: {bot_id!r}"
        print(f"[vm_task_runner] ERROR: {msg}")
        _add_task_comment(task_id, f"❌ VM task runner error: {msg}")
        return {"success": False, "task_id": task_id, "bot_id": bot_id,
                "returncode": 1, "output": msg}

    print(f"[vm_task_runner] Starting task {task_id} for {bot_id}")

    # 1. Register with peers broker
    _register_with_broker(bot_id, task_id)

    # 2. Ensure container is running
    _add_task_comment(task_id, f"🐳 Ensuring {bot_id} container is running...")
    if not ensure_bot_vm_running(bot_id):
        msg = f"Failed to start container for {bot_id}"
        print(f"[vm_task_runner] ERROR: {msg}")
        _add_task_comment(task_id, f"❌ {msg}")
        _update_task_status(task_id, "blocked", result=msg)
        return {"success": False, "task_id": task_id, "bot_id": bot_id,
                "returncode": 1, "output": msg}

    # 3. Mark running
    _update_task_running(task_id)
    _add_task_comment(task_id, f"▶ Running in carrier-{bot_id} container")

    # 4. Build and run command
    cmd = _build_exec_command(task)
    print(f"[vm_task_runner] Exec in {bot_id}: {cmd[:100]}...")
    start_time = time.time()

    rc, output = exec_in_bot_vm(bot_id, cmd)
    elapsed = time.time() - start_time

    # 5. Record output as comment
    comment_body = (
        f"**VM exec completed** in {elapsed:.1f}s (rc={rc})\n\n"
        f"```\n{output[-3000:] if len(output) > 3000 else output}\n```"
    )
    _add_task_comment(task_id, comment_body)

    # 6. Update task status
    success = rc == 0
    final_status = "done" if success else "blocked"
    result_summary = (
        f"Completed via {bot_id} container in {elapsed:.1f}s. Exit code: {rc}. "
        f"Output:\n{output[-1000:]}"
    )
    _update_task_status(task_id, final_status, result=result_summary)

    print(f"[vm_task_runner] Task {task_id} {'done' if success else 'failed'} (rc={rc})")
    return {
        "success": success,
        "task_id": task_id,
        "bot_id": bot_id,
        "returncode": rc,
        "output": output,
    }


# ── CLI shim ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carrier VM Task Runner")
    parser.add_argument("task_json", help="JSON string of the Kanban task dict")
    args = parser.parse_args()

    try:
        task = json.loads(args.task_json)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    result = run_task_in_vm(task)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)

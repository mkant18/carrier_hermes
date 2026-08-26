#!/usr/bin/env python3
"""maintenance_dispatch.py — Shipwright Wing Kanban pipeline dispatcher.

Called by Bosun's cron when preflight passes. Inserts the full Shipwright
pipeline as dependency-linked Kanban tasks in the carrier board.

Pipeline: Diver (A) → Bosun review (B) → Rigger (C) → Bosun review (D)
          → Caulker (E) → Surveyor (F)

Usage:
    python maintenance_dispatch.py [--date YYYY-MM-DD]
"""

import argparse
import json
import os
import sqlite3
import urllib.request
import uuid
from datetime import date, datetime, timezone
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────────

KANBAN_DB = r"C:\Users\micha\AppData\Local\hermes\kanban\boards\carrier\kanban.db"
MANIFEST_DIR = (
    r"C:\Users\micha\AppData\Local\hermes\profiles\maintenance_lt"
    r"\home\_agent\maintenance_lt"
)
REPO_PATH = r"C:\Users\micha\carrier_hermes"
ENV_FILE  = r"C:\Users\micha\AppData\Local\hermes\.env"

MAINTENANCE_CHANNEL = "1542052741889663077"  # #maintenance
FLEET_CHANNEL       = "1541866443765977138"  # #fleet

CREATED_BY = "bosun_dispatch"
PRIORITY = 2
MAX_RETRIES = 2

# Callsign display names for handoff messages
CALLSIGNS = {
    "code_auditor":   "Diver 🤿",
    "maintenance_lt": "Bosun 🛠️",
    "repair_planner": "Rigger 🪢",
    "patch_writer":   "Caulker ⚒️",
    "pr_reviewer":    "Surveyor 🧭",
    "git_yeoman":     "Yeoman 📋",
}


# ── Discord helper ──────────────────────────────────────────────────────────────

def _read_env(path: str) -> dict:
    result: dict = {}
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    except Exception:
        pass
    return result


def discord_post(channel_id: str, text: str, token: str | None = None) -> bool:
    """Post to a Discord channel. Silently skips if no token available."""
    if token is None:
        env = _read_env(ENV_FILE)
        token = env.get("SHIPWRIGHT_DISCORD_TOKEN") or env.get("DISCORD_FLEET_BOT_TOKEN", "")
    if not token:
        return False
    payload = json.dumps({"content": text[:2000]}).encode()
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            # Required — Cloudflare blocks Python's default UA with 403/1010
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:
        print(f"  [discord] post failed: {exc}", flush=True)
        return False


# ── Task definitions ───────────────────────────────────────────────────────────

def build_pipeline(run_date: str) -> list[dict]:
    """Return the ordered pipeline task definitions for the given date."""
    return [
        {
            "key": "A",
            "title": f"[Shipwright {run_date}] Diver audit run",
            "body": (
                f"Code-health audit of carrier_hermes repo for {run_date}. "
                "Crawl repo with rg/ruff/pylint, inspect all agent logs and state.db files, "
                "check carrier kanban.db for failed tasks. "
                f"Write audit_report_{run_date}.md to _agent/maintenance/."
            ),
            "assignee": "code_auditor",
            "status": "ready",
            "workspace_kind": "worktree",
            "workspace_path": REPO_PATH,
        },
        {
            "key": "B",
            "title": f"[Shipwright {run_date}] Bosun review of audit report",
            "body": (
                f"Review Diver's audit_report_{run_date}.md. "
                "Validate completeness, mark any false-positives, then dispatch Rigger "
                "with the report path via AIPass."
            ),
            "assignee": "maintenance_lt",
            "status": "todo",
            "workspace_kind": "scratch",
            "workspace_path": None,
        },
        {
            "key": "C",
            "title": f"[Shipwright {run_date}] Rigger fix plan",
            "body": (
                f"Read audit_report_{run_date}.md. Group issues by root-cause and severity. "
                "Design exact, safe, minimal fixes (file + line range + approach + test plan). "
                f"Write fix_plan_{run_date}.md to _agent/maintenance/."
            ),
            "assignee": "repair_planner",
            "status": "todo",
            "workspace_kind": "scratch",
            "workspace_path": None,
        },
        {
            "key": "D",
            "title": f"[Shipwright {run_date}] Bosun review of fix plan",
            "body": (
                f"Review Rigger's fix_plan_{run_date}.md. "
                "Gate: ensure fixes are safe, scoped, no breaking changes. "
                "Dispatch Caulker with fix_plan path via AIPass."
            ),
            "assignee": "maintenance_lt",
            "status": "todo",
            "workspace_kind": "scratch",
            "workspace_path": None,
        },
        {
            "key": "E",
            "title": f"[Shipwright {run_date}] Caulker implementation",
            "body": (
                f"Implement all fixes from fix_plan_{run_date}.md. "
                f"Branch: maint/{run_date}/fixes. "
                "Commit each fix atomically with 'maint:' prefix. "
                "Request Yeoman to open PR when complete. Notify Bosun via AIPass with PR URL."
            ),
            "assignee": "patch_writer",
            "status": "todo",
            "workspace_kind": "worktree",
            "workspace_path": REPO_PATH,
        },
        {
            "key": "F",
            "title": f"[Shipwright {run_date}] Surveyor PR review",
            "body": (
                f"Review the Caulker PR for {run_date}. "
                "Check: all fixes implemented, no billing violations, ruff passes, CI green. "
                "If changes needed: write fix_requests and AIPass Caulker. "
                "If approved: AIPass Yeoman to merge, then AIPass Bosun with merge summary."
            ),
            "assignee": "pr_reviewer",
            "status": "todo",
            "workspace_kind": "scratch",
            "workspace_path": None,
        },
    ]


# ── DB helpers ─────────────────────────────────────────────────────────────────

def insert_tasks(conn: sqlite3.Connection, tasks: list[dict], run_date: str) -> dict[str, str]:
    """Insert pipeline tasks and return {key: task_id} mapping."""
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    key_to_id: dict[str, str] = {}

    cur = conn.cursor()
    for task in tasks:
        task_id = str(uuid.uuid4())
        key_to_id[task["key"]] = task_id

        cur.execute(
            """
            INSERT INTO tasks (
                id, title, body, assignee, status,
                priority, created_by, created_at,
                workspace_kind, workspace_path,
                max_retries
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?
            )
            """,
            (
                task_id,
                task["title"],
                task["body"],
                task["assignee"],
                task["status"],
                PRIORITY,
                CREATED_BY,
                now_ts,
                task["workspace_kind"],
                task["workspace_path"],
                MAX_RETRIES,
            ),
        )
        print(f"  [{task['key']}] {task_id}  {task['title'][:55]}")

    conn.commit()
    return key_to_id


def insert_links(conn: sqlite3.Connection, key_to_id: dict[str, str]) -> None:
    """Insert A→B→C→D→E→F dependency chain into task_links."""
    chain = ["A", "B", "C", "D", "E", "F"]
    cur = conn.cursor()
    for parent_key, child_key in zip(chain, chain[1:]):
        cur.execute(
            "INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)",
            (key_to_id[parent_key], key_to_id[child_key]),
        )
        print(f"  link: {parent_key} ({key_to_id[parent_key][:8]}…)"
              f" → {child_key} ({key_to_id[child_key][:8]}…)")
    conn.commit()


def write_manifest(key_to_id: dict[str, str], run_date: str) -> Path:
    """Write run manifest JSON and return its path."""
    manifest_dir = Path(MANIFEST_DIR)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = manifest_dir / f"run_manifest_{run_date}.json"
    manifest = {
        "run_date": run_date,
        "dispatched_at": datetime.now(tz=timezone.utc).isoformat(),
        "created_by": CREATED_BY,
        "pipeline": {
            key: {
                "task_id": task_id,
                "description": desc,
            }
            for (key, task_id), desc in zip(
                key_to_id.items(),
                [
                    "Diver audit run",
                    "Bosun review of audit",
                    "Rigger fix plan",
                    "Bosun review of fix plan",
                    "Caulker implementation",
                    "Surveyor PR review",
                ],
            )
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert Shipwright maintenance pipeline tasks into the carrier Kanban board."
    )
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Run date in YYYY-MM-DD format (defaults to today).",
    )
    args = parser.parse_args()
    run_date: str = args.date

    print(f"\n=== Shipwright Maintenance Dispatch — {run_date} ===\n")

    pipeline = build_pipeline(run_date)

    print("Inserting tasks into carrier Kanban board…")
    with sqlite3.connect(KANBAN_DB) as conn:
        key_to_id = insert_tasks(conn, pipeline, run_date)

        print("\nInserting dependency links…")
        insert_links(conn, key_to_id)

    print("\nWriting run manifest…")
    manifest_path = write_manifest(key_to_id, run_date)
    print(f"  → {manifest_path}")

    print("\n=== Dispatch complete ===")
    print(f"Run date : {run_date}")
    print(f"Tasks    : {len(key_to_id)}")
    print(f"Manifest : {manifest_path}")
    print("\nTask ID summary:")
    labels = {
        "A": "Diver audit         (code_auditor)    [ready]",
        "B": "Bosun audit review  (maintenance_lt)  [todo]",
        "C": "Rigger fix plan     (repair_planner)  [todo]",
        "D": "Bosun plan review   (maintenance_lt)  [todo]",
        "E": "Caulker implement   (patch_writer)    [todo]",
        "F": "Surveyor PR review  (pr_reviewer)     [todo]",
    }
    for key, task_id in key_to_id.items():
        print(f"  {key}: {task_id}  {labels[key]}")

    # ── Discord handoff announcement ──────────────────────────────────────────
    env = _read_env(ENV_FILE)
    sw_token  = env.get("SHIPWRIGHT_DISCORD_TOKEN", "")
    fw_token  = env.get("DISCORD_FLEET_BOT_TOKEN", "")

    maintenance_msg = (
        f"🛠️ **Shipwright** — maintenance pipeline launched for `{run_date}`\n"
        f"📋 **Diver 🤿** deploying now for repo crawl + log audit\n"
        f"Pipeline: Diver 🤿 → Bosun 🛠️ review → Rigger 🪢 → Bosun 🛠️ review "
        f"→ Caulker ⚒️ → Surveyor 🧭 → Yeoman 📋"
    )
    discord_post(MAINTENANCE_CHANNEL, maintenance_msg, token=sw_token)

    fleet_msg = f"🛠️ **Shipwright Wing** — maintenance pipeline active for `{run_date}` · 6 tasks queued"
    discord_post(FLEET_CHANNEL, fleet_msg, token=fw_token)


if __name__ == "__main__":
    main()

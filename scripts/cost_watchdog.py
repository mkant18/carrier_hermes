#!/usr/bin/env python3
"""
cost_watchdog.py — Hard budget cap + loud failure monitor for kanban tasks.

Monitors one or more kanban task IDs. For each task:
  1. Polls state.db session_model_usage for actual + estimated spend
  2. If spend > --budget-usd threshold: kills worker process + fires loud alerts
  3. If task crashes/blocks unexpectedly: fires loud alerts
  4. Exits 0 (all tasks done cleanly) or 1 (budget exceeded / crash detected)

Alerts fire to:
  - Helm (chief_of_staff) AIPass inbox
  - Discord #maintenance channel via First Watch REST token
  - A HALT marker file that the worker's prompt can check

Usage:
  python cost_watchdog.py --tasks t_abc123 t_def456 --budget-usd 0.15 --poll 30
"""

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME   = Path(r"C:\Users\micha\AppData\Local\hermes")
KANBAN_DB     = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"
GLOBAL_STATE  = HERMES_HOME / "state.db"
HALT_DIR      = HERMES_HOME / "carrier" / "budget_halts"
DISCORD_CHAN  = "1542052741889663077"   # #maintenance channel
HELM_INBOX    = HERMES_HOME / "profiles" / "chief_of_staff" / "home" / "_agent" / "mailbox" / "chief_of_staff" / "inbox"

TERMINAL_STATUSES = {"done", "failed", "archived", "cancelled"}


# ---------------------------------------------------------------------------
# Discord alert
# ---------------------------------------------------------------------------
def _discord_post(text: str) -> bool:
    env_file = HERMES_HOME / ".env"
    env: dict = {}
    try:
        for line in env_file.read_text(errors="replace").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except Exception:
        pass

    token = env.get("FIRST_WATCH_TOKEN") or env.get("DISCORD_FLEET_BOT_TOKEN", "")
    if not token:
        print("[watchdog] WARNING: no Discord token — alert not sent", flush=True)
        return False
    try:
        payload = json.dumps({"content": text[:2000]}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{DISCORD_CHAN}/messages",
            data=payload,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (carrier_hermes, 1.0)",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:
        print(f"[watchdog] Discord post failed: {exc}", flush=True)
        return False


# ---------------------------------------------------------------------------
# Helm AIPass alert
# ---------------------------------------------------------------------------
def _helm_alert(subject: str, body: str) -> None:
    try:
        HELM_INBOX.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fname = HELM_INBOX / f"URGENT-watchdog-{ts}.md"
        fname.write_text(
            f"---\nfrom: cost_watchdog\nto: chief_of_staff\ntype: urgent_alert\npriority: CRITICAL\n---\n\n"
            f"# 🚨 {subject}\n\n{body}\n",
            encoding="utf-8",
        )
        print(f"[watchdog] Helm alert written: {fname}", flush=True)
    except Exception as exc:
        print(f"[watchdog] Helm alert failed: {exc}", flush=True)


# ---------------------------------------------------------------------------
# HALT marker
# ---------------------------------------------------------------------------
def _write_halt(task_id: str, reason: str) -> Path:
    HALT_DIR.mkdir(parents=True, exist_ok=True)
    marker = HALT_DIR / f"{task_id}.halt"
    marker.write_text(
        json.dumps({"task_id": task_id, "reason": reason, "ts": time.time()}),
        encoding="utf-8",
    )
    return marker


# ---------------------------------------------------------------------------
# Kill worker
# ---------------------------------------------------------------------------
def _kill_worker(pid: int, task_id: str) -> str:
    if not pid:
        return "no pid"
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)
        try:
            os.kill(pid, 9)  # SIGKILL (portable int)
        except ProcessLookupError:
            pass
        return f"killed pid {pid}"
    except ProcessLookupError:
        return f"pid {pid} already gone"
    except Exception as exc:
        return f"kill failed: {exc}"


# ---------------------------------------------------------------------------
# Cost query
# ---------------------------------------------------------------------------
def _get_task_cost(task_id: str) -> dict:
    """
    Returns {'session_id', 'worker_pid', 'status', 'profile',
             'or_cost_usd', 'total_cost_usd', 'rows'}
    """
    result = {
        "session_id": None, "worker_pid": None, "status": None, "profile": None,
        "or_cost_usd": 0.0, "total_cost_usd": 0.0, "rows": [],
    }

    try:
        conn = sqlite3.connect(str(KANBAN_DB))
        row = conn.execute(
            "SELECT session_id, worker_pid, status, assignee FROM tasks WHERE id=?",
            (task_id,)
        ).fetchone()
        conn.close()
    except Exception as exc:
        print(f"[watchdog] kanban read error: {exc}", flush=True)
        return result

    if not row:
        return result

    session_id, worker_pid, status, assignee = row
    result.update({"session_id": session_id, "worker_pid": worker_pid,
                   "status": status, "profile": assignee})

    if not session_id:
        return result

    # Try profile state.db first, then global
    dbs_to_try = []
    if assignee:
        profile_db = HERMES_HOME / "profiles" / assignee / "state.db"
        if profile_db.exists():
            dbs_to_try.append(profile_db)
    dbs_to_try.append(GLOBAL_STATE)

    for db_path in dbs_to_try:
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                """SELECT billing_provider, model,
                          ROUND(COALESCE(estimated_cost_usd,0),8) as est,
                          ROUND(COALESCE(actual_cost_usd,0),8) as act,
                          input_tokens, output_tokens
                   FROM session_model_usage WHERE session_id=?""",
                (session_id,)
            ).fetchall()
            conn.close()
            if rows:
                result["rows"] = rows
                for r in rows:
                    provider, model, est, act, in_tok, out_tok = r
                    cost = act if act else est
                    result["total_cost_usd"] += cost
                    if (provider or "").startswith("openrouter"):
                        result["or_cost_usd"] += cost
                break
        except Exception:
            continue

    return result


# ---------------------------------------------------------------------------
# Main watch loop
# ---------------------------------------------------------------------------
def watch(task_ids: list, budget_usd: float, poll_s: int, verbose: bool) -> int:
    print(
        f"[watchdog] Monitoring {task_ids} | budget=${budget_usd:.4f} | poll={poll_s}s",
        flush=True,
    )

    exceeded: set = set()
    crashed: set = set()
    done_clean: set = set()

    while True:
        all_terminal = True

        for task_id in task_ids:
            if task_id in done_clean or task_id in exceeded or task_id in crashed:
                continue

            info = _get_task_cost(task_id)
            status = info["status"] or "unknown"
            total  = info["total_cost_usd"]
            or_cost = info["or_cost_usd"]
            pid    = info["worker_pid"]

            if verbose:
                print(
                    f"[watchdog] {task_id} status={status} "
                    f"total=${total:.6f} or=${or_cost:.6f} pid={pid}",
                    flush=True,
                )

            # ── Budget exceeded ──────────────────────────────────────────
            if total > budget_usd:
                exceeded.add(task_id)
                kill_msg = _kill_worker(pid, task_id)
                halt = _write_halt(task_id, f"budget_exceeded ${total:.4f} > ${budget_usd:.4f}")

                subject = f"🚨 BUDGET EXCEEDED — {task_id} (${total:.4f} > ${budget_usd:.4f} cap)"
                body = (
                    f"**Task:** `{task_id}`  \n"
                    f"**Assignee:** {info['profile']}  \n"
                    f"**Spent:** ${total:.6f} (OR portion: ${or_cost:.6f})  \n"
                    f"**Cap:** ${budget_usd:.4f}  \n"
                    f"**Worker:** {kill_msg}  \n"
                    f"**Halt marker:** `{halt}`  \n\n"
                    f"The worker has been killed. The task will need human review before restart.\n"
                    f"Check `hermes kanban --board carrier show {task_id}` for details."
                )

                print(f"\n{'='*70}", flush=True)
                print(f"🚨 BUDGET EXCEEDED: {task_id} spent ${total:.6f}", flush=True)
                print(f"{'='*70}\n", flush=True)
                _helm_alert(subject, body)
                _discord_post(
                    f"🚨 **BUDGET WATCHDOG — HARD STOP**\n"
                    f"Task `{task_id}` ({info['profile']}) spent **${total:.4f}** — cap is **${budget_usd:.4f}**\n"
                    f"Worker {kill_msg}. Task requires human review before restart.\n"
                    f"Halt marker: `{halt.name}`"
                )
                continue

            # ── Task crashed / unexpectedly blocked ─────────────────────
            if status in ("failed", "blocked") and task_id not in crashed:
                crashed.add(task_id)
                subject = f"🔴 LOCAL TASK FAILED — {task_id} [{status}]"
                body = (
                    f"**Task:** `{task_id}`  \n"
                    f"**Assignee:** {info['profile']}  \n"
                    f"**Status:** {status}  \n"
                    f"**Spent so far:** ${total:.6f}  \n\n"
                    f"Action: check logs at  \n"
                    f"`C:/Users/micha/AppData/Local/hermes/kanban/boards/carrier/logs/{task_id}.log`\n\n"
                    f"To retry: `hermes kanban --board carrier unblock {task_id}`"
                )
                print(f"\n{'='*70}", flush=True)
                print(f"🔴 TASK CRASHED: {task_id} status={status}", flush=True)
                print(f"{'='*70}\n", flush=True)
                _helm_alert(subject, body)
                _discord_post(
                    f"🔴 **TASK FAILURE ALERT**\n"
                    f"Task `{task_id}` ({info['profile']}) is now **{status}**.\n"
                    f"Spent: ${total:.4f} | pid was: {pid}\n"
                    f"Check logs, then: `hermes kanban --board carrier unblock {task_id}`"
                )
                continue

            # ── Clean completion ─────────────────────────────────────────
            if status == "done":
                done_clean.add(task_id)
                print(f"[watchdog] ✅ {task_id} completed cleanly (${total:.6f})", flush=True)
                continue

            # Still running
            all_terminal = False

        # Exit when all tasks reached a terminal state
        still_live = [t for t in task_ids if t not in done_clean | exceeded | crashed]
        if not still_live:
            break

        # Also exit if all tasks are terminal status in the DB even if not tracked above
        try:
            conn = sqlite3.connect(str(KANBAN_DB))
            live = conn.execute(
                f"SELECT COUNT(*) FROM tasks WHERE id IN ({','.join('?'*len(task_ids))}) "
                f"AND status NOT IN ('done','failed','archived','cancelled')",
                task_ids
            ).fetchone()[0]
            conn.close()
            if live == 0:
                break
        except Exception:
            pass

        time.sleep(poll_s)

    n_ok = len(done_clean)
    n_bad = len(exceeded) + len(crashed)
    print(
        f"\n[watchdog] Done. {n_ok} clean, {len(exceeded)} budget-exceeded, {len(crashed)} crashed.",
        flush=True,
    )
    return 1 if n_bad else 0


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kanban task cost + failure watchdog")
    ap.add_argument("--tasks", nargs="+", required=True, help="Task IDs to watch")
    ap.add_argument("--budget-usd", type=float, default=0.15, help="Hard spend cap in USD (default 0.15)")
    ap.add_argument("--poll", type=int, default=30, help="Poll interval seconds (default 30)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    sys.exit(watch(args.tasks, args.budget_usd, args.poll, args.verbose))

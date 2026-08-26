#!/usr/bin/env python3
"""
blocked_task_watchdog.py — Zero-LLM human-input unblock prompter.

Polls the carrier Kanban DB for tasks blocked on human input
(block_kind='human'). Sends escalating prompts on all three platforms
(Discord #fleet, Buzz #command, Telegram Fleet Command) using the same
zero-LLM broadcast pattern as fleet_checkin.py.

Escalation ladder (measured from task created_at):
  0-10 min  : no prompt (fresh block, give the human a moment)
 10-30 min  : 1st nudge  🔔
 30-45 min  : 2nd nudge  🔔🔔
 45-60 min  : 3rd nudge  🔔🔔🔔
 60+ min    : defer to Helm — flags task for chief_of_staff review
              (writes AIPass msg + sends ⚠️ escalation notice)

Designed to run every 5 minutes as a no_agent cron (no LLM, no quota drain).
State is tracked in a tiny SQLite sidecar DB so each nudge fires ONCE per tier.

Usage:
  python blocked_task_watchdog.py [--dry-run]
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

HERMES_HOME  = Path(r"C:\Users\micha\AppData\Local\hermes")
REPO         = Path(r"C:\Users\micha\carrier_hermes")
KANBAN_DB    = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"
SIDECAR_DB   = HERMES_HOME / "carrier" / "watchdog_state.db"
SCRIPTS_DIR  = REPO / "scripts"

BUZZ_CHANNELS_FILE = REPO / "buzz" / "buzz_channels.json"
BUZZ_SIGNAL_PY     = SCRIPTS_DIR / "buzz_signal.py"
HPY                = str(HERMES_HOME / "hermes-agent" / "venv" / "Scripts" / "python.exe")

# Telegram
CHIEF_ENV         = HERMES_HOME / "profiles" / "chief_of_staff" / ".env"
TG_CHAT_ID        = "-5577918772"   # Fleet Command group
TG_MENTION_UID    = "8816949993"    # Michael's Telegram user ID

# Discord
DISCORD_ENV_FILE  = HERMES_HOME / ".env"
FLEET_CHANNEL_ID  = "1541866443765977138"   # #fleet
DISCORD_MENTION   = "<@174349224870150144>"  # Michael's Discord ID

# Escalation thresholds in seconds from task created_at
TIER_1_SECS  = 10 * 60   # 10 min  → first nudge
TIER_2_SECS  = 30 * 60   # 30 min  → second nudge
TIER_3_SECS  = 45 * 60   # 45 min  → third nudge
TIER_HELM_S  = 60 * 60   # 60 min  → defer to Helm

# AIPass mailbox for chief_of_staff
HELM_INBOX   = (
    HERMES_HOME
    / "profiles" / "chief_of_staff"
    / "home" / "_agent" / "mailbox" / "chief_of_staff" / "inbox"
)

DRY_RUN = "--dry-run" in sys.argv

# ── Sidecar state DB ──────────────────────────────────────────────────────────

def init_sidecar() -> sqlite3.Connection:
    """Create/open the tiny sidecar DB that tracks which tier fired per task."""
    SIDECAR_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SIDECAR_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchdog_tiers (
            task_id   TEXT NOT NULL,
            tier      INTEGER NOT NULL,
            fired_at  INTEGER NOT NULL,
            PRIMARY KEY (task_id, tier)
        )
    """)
    conn.commit()
    return conn


def tier_already_fired(conn: sqlite3.Connection, task_id: str, tier: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM watchdog_tiers WHERE task_id=? AND tier=?",
        (task_id, tier),
    ).fetchone()
    return row is not None


def mark_tier_fired(conn: sqlite3.Connection, task_id: str, tier: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO watchdog_tiers (task_id, tier, fired_at) VALUES (?, ?, ?)",
        (task_id, tier, int(time.time())),
    )
    conn.commit()


def cleanup_done_tasks(conn: sqlite3.Connection) -> None:
    """Remove sidecar rows for tasks no longer blocked (resolved / done / archived)."""
    kanban = sqlite3.connect(str(KANBAN_DB))
    blocked_ids = {
        r[0] for r in kanban.execute(
            "SELECT id FROM tasks WHERE status='blocked' AND (block_kind='human' OR block_kind IS NULL)"
        ).fetchall()
    }
    kanban.close()
    all_tracked = {r[0] for r in conn.execute("SELECT DISTINCT task_id FROM watchdog_tiers").fetchall()}
    stale = all_tracked - blocked_ids
    if stale:
        for tid in stale:
            conn.execute("DELETE FROM watchdog_tiers WHERE task_id=?", (tid,))
        conn.commit()

# ── Blocked task query ────────────────────────────────────────────────────────

def get_blocked_tasks() -> list[dict]:
    """Return all tasks blocked waiting on human input."""
    conn = sqlite3.connect(str(KANBAN_DB))
    conn.row_factory = sqlite3.Row
    # block_kind='human' OR block_kind IS NULL (old tasks might not have block_kind set)
    rows = conn.execute(
        """SELECT id, title, assignee, created_at, block_kind
           FROM tasks
           WHERE status='blocked'
             AND (block_kind='human' OR block_kind IS NULL)
           ORDER BY created_at ASC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Token helpers ─────────────────────────────────────────────────────────────

def _read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_discord_token() -> str:
    return _read_env_file(DISCORD_ENV_FILE).get("DISCORD_FLEET_BOT_TOKEN", "")


def get_telegram_token() -> str:
    return _read_env_file(CHIEF_ENV).get("TELEGRAM_BOT_TOKEN", "")

# ── Broadcast helpers ─────────────────────────────────────────────────────────

def discord_post(token: str, channel_id: str, text: str) -> bool:
    if not token:
        print("  [discord] no token — skipping", file=sys.stderr)
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status in (200, 201)
            print(f"  [discord] → {'OK' if ok else 'FAIL'} ({resp.status})")
            return ok
    except urllib.error.HTTPError as e:
        print(f"  [discord] HTTPError {e.code}: {e.read()[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [discord] Error: {e}", file=sys.stderr)
        return False


def telegram_post(token: str, chat_id: str, text: str, mention_uid: str = "") -> bool:
    if not token or not chat_id:
        print("  [telegram] no token/chat_id — skipping", file=sys.stderr)
        return False
    body = html.escape(text.replace("**", ""))
    if mention_uid:
        tg_text = f'<a href="tg://user?id={mention_uid}">👋</a>\n{body}'
    else:
        tg_text = body
    payload = json.dumps({
        "chat_id": str(chat_id),
        "text": tg_text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read())
            ok = d.get("ok", False)
            msg_id = d.get("result", {}).get("message_id", "?")
            print(f"  [telegram] → {'OK' if ok else 'FAIL'} msg_id={msg_id}")
            return ok
    except urllib.error.HTTPError as e:
        print(f"  [telegram] HTTPError {e.code}: {e.read()[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [telegram] Error: {e}", file=sys.stderr)
        return False


def buzz_post(bot_id: str, text: str, channel: str = "command") -> bool:
    if not BUZZ_SIGNAL_PY.exists():
        print(f"  [buzz] buzz_signal.py not found — skipping", file=sys.stderr)
        return False
    try:
        r = subprocess.run(
            [HPY, str(BUZZ_SIGNAL_PY), "RAW", bot_id, text, channel],
            capture_output=True, text=True, timeout=30,
        )
        ok = r.returncode == 0
        print(f"  [buzz] → {'OK' if ok else 'FAIL'}: {r.stdout.strip()[:100]}")
        return ok
    except Exception as e:
        print(f"  [buzz] Error: {e}", file=sys.stderr)
        return False


def broadcast(text: str, discord_token: str, tg_token: str) -> None:
    """Fire-and-forget to all three platforms."""
    if DRY_RUN:
        print(f"  [DRY-RUN] Would broadcast:\n    {text[:200]}")
        return
    discord_post(discord_token, FLEET_CHANNEL_ID, text)
    buzz_post("marshal", text.replace("**", "").replace("`", ""), "command")
    telegram_post(tg_token, TG_CHAT_ID, text, TG_MENTION_UID)

# ── Helm AIPass escalation ───────────────────────────────────────────────────

def write_helm_aipass(task: dict) -> None:
    """Write an AIPass message to Helm's inbox for 60-min escalation."""
    if DRY_RUN:
        print(f"  [DRY-RUN] Would write Helm AIPass for {task['id']}")
        return
    HELM_INBOX.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    msg_file = HELM_INBOX / f"watchdog-escalation-{ts}.md"
    age_min = int((time.time() - task["created_at"]) / 60)
    content = f"""---
from: watchdog
to: chief_of_staff
type: human_block_escalation
kanban_task: {task['id']}
---
## ⚠️ Human-blocked task — 60 min elapsed, needs your review

Task **{task['id']}** (`{task['title'][:80]}`) has been blocked waiting for
human input for **{age_min} minutes** with no response.

Assignee: `{task['assignee']}`

Please review this task and either:
1. Provide the required input to unblock it, OR
2. Mark it cancelled if it is no longer relevant, OR
3. Reassign it with updated instructions

To unblock:
  hermes kanban --board carrier show {task['id']}
  hermes kanban --board carrier unblock {task['id']}
"""
    msg_file.write_text(content, encoding="utf-8")
    print(f"  [helm-aipass] wrote {msg_file.name}")

# ── Message composers ─────────────────────────────────────────────────────────

TIER_EMOJI = {1: "🔔", 2: "🔔🔔", 3: "🔔🔔🔔", 4: "⚠️"}
TIER_LABEL = {
    1: "needs your input (10 min)",
    2: "still waiting on you (30 min)",
    3: "urgent — no response yet (45 min)",
    4: "DEFERRED TO HELM — 60+ min unresolved",
}


def compose_message(task: dict, tier: int, age_min: int) -> str:
    emoji = TIER_EMOJI[tier]
    label = TIER_LABEL[tier]
    discord_user = DISCORD_MENTION
    task_id = task["id"]
    title = task["title"][:70]
    assignee = task["assignee"]

    lines = [
        f"{emoji} **Blocked task {label}**",
        f"",
        f"**Task:** `{task_id}` — {title}",
        f"**Assignee:** `{assignee}` · **Blocked:** {age_min} min ago",
        f"",
    ]

    if tier < 4:
        lines += [
            f"👉 {discord_user} — reply on any platform to unblock:",
            f"  `hermes kanban --board carrier show {task_id}`",
            f"  `hermes kanban --board carrier unblock {task_id}`",
            f"",
            f"Or just reply here with what the bot needs and I'll relay it.",
        ]
    else:
        lines += [
            f"⚠️ {discord_user} — No response in 60 min. **Helm has been notified** to review and handle.",
            f"  Task: `{task_id}` · Assignee: `{assignee}`",
        ]

    return "\n".join(lines)

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"[watchdog] {'DRY-RUN — ' if DRY_RUN else ''}start {time.strftime('%Y-%m-%dT%H:%M:%S')}")

    discord_token = get_discord_token()
    tg_token      = get_telegram_token()

    if not discord_token:
        print("[watchdog] WARNING: no DISCORD_FLEET_BOT_TOKEN found", file=sys.stderr)
    if not tg_token:
        print("[watchdog] WARNING: no TELEGRAM_BOT_TOKEN found in chief_of_staff .env", file=sys.stderr)

    tasks = get_blocked_tasks()
    print(f"[watchdog] {len(tasks)} human-blocked task(s) found")

    if not tasks:
        return 0

    sidecar = init_sidecar()
    cleanup_done_tasks(sidecar)

    now = time.time()
    fired_any = False

    for task in tasks:
        task_id  = task["id"]
        age_secs = now - task["created_at"]
        age_min  = int(age_secs / 60)

        # Determine which tier this task is currently in
        if age_secs >= TIER_HELM_S:
            tier = 4
        elif age_secs >= TIER_3_SECS:
            tier = 3
        elif age_secs >= TIER_2_SECS:
            tier = 2
        elif age_secs >= TIER_1_SECS:
            tier = 1
        else:
            # Too fresh — don't bother yet
            print(f"  [{task_id}] {age_min} min old — below 10-min threshold, skipping")
            continue

        if tier_already_fired(sidecar, task_id, tier):
            print(f"  [{task_id}] tier {tier} already fired — skipping")
            continue

        print(f"  [{task_id}] {age_min} min old → firing tier {tier}")
        msg = compose_message(task, tier, age_min)

        broadcast(msg, discord_token, tg_token)

        if tier == 4:
            write_helm_aipass(task)

        mark_tier_fired(sidecar, task_id, tier)
        fired_any = True

    sidecar.close()

    if not fired_any:
        print("[watchdog] all tasks already notified for their current tier — nothing to do")

    print(f"[watchdog] done {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

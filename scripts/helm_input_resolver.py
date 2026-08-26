#!/usr/bin/env python3
"""
helm_input_resolver.py — Agent helper for the Helm Human-Input Resolver cron.

Called from the cron's agent prompt (not directly from cron no_agent mode).
The cron agent reads the monitor JSON, then calls this script with:

    python helm_input_resolver.py dispatch   <task_json_file>
    python helm_input_resolver.py resolve    <task_id>
    python helm_input_resolver.py cleanup    <task_id>

dispatch:
    - Records the task in human_input_queue.json as 'dispatched'
    - Creates a Probe brief file in human_input_responses/<task_id>_brief.md
    - Writes an AIPass message to research_agent's inbox
    - Posts a Discord + Telegram alert so Michael knows Helm is auto-resolving

resolve:
    - Reads the completed response from human_input_responses/<task_id>.json
    - Comments the decision onto the Kanban card
    - Calls `hermes kanban --board carrier unblock <task_id>`
    - Updates queue entry to 'resolved'
    - Posts confirmation to Discord + Telegram

cleanup:
    - Removes resolved tasks from human_input_queue.json that are >24h old
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
HERMES_HOME  = Path(r"C:\Users\micha\AppData\Local\hermes")
CARRIER_DIR  = HERMES_HOME / "carrier"
QUEUE_FILE   = CARRIER_DIR / "human_input_queue.json"
RESPONSE_DIR = CARRIER_DIR / "human_input_responses"
REPO_ROOT    = Path(r"C:\Users\micha\carrier_hermes")

# Fleet comms
DISCORD_FLEET_CHANNEL = "1541866443765977138"   # #fleet
TELEGRAM_FLEET_CHAT   = "-5577918772"           # Fleet Command group
MICHAEL_DISCORD_ID    = "174349224870150144"
MICHAEL_TG_ID         = "8816949993"

# ── Queue helpers ───────────────────────────────────────────────────────────

def load_queue() -> dict:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_queue(q: dict):
    QUEUE_FILE.write_text(json.dumps(q, indent=2, ensure_ascii=False),
                          encoding="utf-8")


# ── Fleet comms ─────────────────────────────────────────────────────────────

def _load_env_file(path: Path) -> dict:
    """Load a .env file, stripping quotes — same pattern as fleet_checkin."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _env():
    """Read fleet comms tokens from .env files (same as fleet_checkin)."""
    e = dict(os.environ)
    # Default home .env — has DISCORD_FLEET_BOT_TOKEN
    default_env = _load_env_file(HERMES_HOME / ".env")
    e.update(default_env)
    # chief_of_staff .env — has TELEGRAM_BOT_TOKEN
    cos_env = _load_env_file(HERMES_HOME / "profiles" / "chief_of_staff" / ".env")
    e.update(cos_env)
    return e


def discord_post(message: str, env: dict):
    """POST to #fleet via First Watch REST."""
    token = env.get("DISCORD_FLEET_BOT_TOKEN", "")
    if not token:
        print("[resolver] no DISCORD_FLEET_BOT_TOKEN, skipping Discord", file=sys.stderr)
        return
    import urllib.request, urllib.error
    payload = json.dumps({
        "content": message[:1990],
        "allowed_mentions": {"parse": ["users"]},
    }).encode()
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{DISCORD_FLEET_CHANNEL}/messages",
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            # Required: Cloudflare blocks Python's default UA with 403
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[resolver] discord → {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"[resolver] discord HTTP {exc.code}: {exc.read()[:200]}", file=sys.stderr)
    except Exception as exc:
        print(f"[resolver] discord error: {exc}", file=sys.stderr)


def telegram_post(message: str, env: dict | None = None):
    """Send via Telegram Bot API directly (same as fleet_checkin)."""
    if env is None:
        env = _env()
    tg_token  = env.get("TELEGRAM_BOT_TOKEN", "")
    if not tg_token:
        print("[resolver] no TELEGRAM_BOT_TOKEN, skipping Telegram", file=sys.stderr)
        return
    import urllib.request
    payload = json.dumps({
        "chat_id": TELEGRAM_FLEET_CHAT,
        "text": message[:4096],
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tg_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[resolver] telegram → {resp.status}")
    except Exception as exc:
        print(f"[resolver] telegram error: {exc}", file=sys.stderr)


def aipass_message(bot_id: str, from_bot: str, msg_type: str, body: str):
    """Write to a bot's AIPass inbox."""
    inbox = (HERMES_HOME / "profiles" / bot_id
             / "home" / "_agent" / "mailbox" / bot_id / "inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    fname = f"helm-resolver-{int(time.time())}.md"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    content = f"""---
from: {from_bot}
to: {bot_id}
type: {msg_type}
created_at: {ts}
---
{body}
"""
    (inbox / fname).write_text(content, encoding="utf-8")
    print(f"[resolver] AIPass → {bot_id}/inbox/{fname}")


def kanban_comment(task_id: str, text: str, author: str = "chief_of_staff"):
    r = subprocess.run(
        ["hermes", "kanban", "--board", "carrier",
         "comment", "--author", author, task_id, text],
        capture_output=True, text=True, timeout=30
    )
    print(f"[resolver] kanban comment → exit {r.returncode}")
    if r.returncode != 0:
        print(f"[resolver] comment stderr: {r.stderr[:300]}", file=sys.stderr)


def kanban_unblock(task_id: str, reason: str):
    r = subprocess.run(
        ["hermes", "kanban", "--board", "carrier",
         "unblock", "--reason", reason[:500], task_id],
        capture_output=True, text=True, timeout=30
    )
    print(f"[resolver] kanban unblock → exit {r.returncode}")
    if r.returncode != 0:
        print(f"[resolver] unblock stderr: {r.stderr[:300]}", file=sys.stderr)
    return r.returncode == 0


# ── Sub-commands ─────────────────────────────────────────────────────────────

def cmd_dispatch(task_json_path: str):
    """
    Record task in queue, write Probe brief, send AIPass, alert fleet.
    task_json_path: path to a JSON file containing one task dict from the monitor.
    """
    task = json.loads(Path(task_json_path).read_text(encoding="utf-8"))
    tid   = task["id"]
    title = task["title"]

    queue = load_queue()
    if queue.get(tid, {}).get("status") in ("dispatched", "resolved"):
        print(f"[resolver] {tid} already {queue[tid]['status']}, skip")
        return

    # ── 1. Write Probe brief ───────────────────────────────────────────────
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = RESPONSE_DIR / f"{tid}_brief.md"
    brief_content = f"""# Helm Auto-Resolver — Research Brief

## Task Requiring Human Input
- **ID:** `{tid}`
- **Title:** {title}
- **Assignee:** {task.get('assignee', 'unknown')}
- **Blocked for:** {task.get('age_h', '?')}h

## What the Bot Reported
The assignee bot blocked this task with the following blocker:

```
{task.get('summary', 'No summary recorded. See task body.')[:2000]}
```

## Task Context (excerpt)
```
{task.get('body_excerpt', '')[:3000]}
```

## Your Mission (Probe)

Research this blocker and produce a concrete recommendation so Helm can
unblock the task WITHOUT requiring Michael's manual input.

Write your response to:
  `C:/Users/micha/AppData/Local/hermes/carrier/human_input_responses/{tid}.json`

Response file format (JSON):
```json
{{
  "task_id": "{tid}",
  "recommendation": "<Specific actionable answer to give the bot — 2-5 sentences. This will be posted as a Kanban comment and used to unblock.>",
  "confidence": "high|medium|low",
  "research_summary": "<Brief explanation of what you found and why this recommendation is correct — 3-8 sentences.>"
}}
```

If confidence is `low`, still provide the best available recommendation and note the uncertainty.
Do NOT leave the file empty or skip writing it — Helm is waiting on this output.
"""
    brief_path.write_text(brief_content, encoding="utf-8")
    print(f"[resolver] brief written: {brief_path}")

    # ── 2. AIPass to research_agent ────────────────────────────────────────
    aipass_body = f"""## Helm Auto-Resolver Request

Helm has detected that a Kanban task has been blocked waiting on human input
for over 1 hour. You are being dispatched to research the blocker and produce
a recommendation.

**Task:** `{tid}` — {title}
**Blocked for:** {task.get('age_h', '?')}h
**Assignee bot:** {task.get('assignee', 'unknown')}

### Blocker Summary
{task.get('summary', 'No summary. Read the full brief.')[:1000]}

### Full Brief
Read the complete research brief at:
`{brief_path}`

Write your JSON response to:
`{RESPONSE_DIR / f"{tid}.json"}`

Response format is in the brief. This is a time-sensitive request — the task
has been blocked for over an hour. Helm will poll for your response and unblock
the card automatically once it arrives.
"""
    aipass_message(
        bot_id="research_agent",
        from_bot="chief_of_staff",
        msg_type="helm_input_resolution_request",
        body=aipass_body,
    )

    # ── 3. Update queue ────────────────────────────────────────────────────
    queue[tid] = {
        "status":       "dispatched",
        "title":        title,
        "assignee":     task.get("assignee", ""),
        "age_h":        task.get("age_h"),
        "dispatched_at": int(time.time()),
        "brief_path":   str(brief_path),
    }
    save_queue(queue)
    print(f"[resolver] queue updated: {tid} → dispatched")

    # ── 4. Fleet alert ─────────────────────────────────────────────────────
    env = _env()
    age_h = task.get("age_h", "?")
    msg = (
        f"**Helm 🎖️ — Auto-Resolver** <@{MICHAEL_DISCORD_ID}>\n"
        f"Task `{tid}` has been blocked for **{age_h}h** awaiting human input.\n"
        f"📤 Dispatching **Probe** to research the blocker and recommend a decision.\n"
        f"Helm will unblock automatically once Probe responds.\n"
        f"> **Card:** {title[:100]}\n"
        f"> **Blocker:** {task.get('summary','')[:200]}"
    )
    discord_post(msg, env)

    tg_msg = (
        f"🤖 <b>Helm Auto-Resolver</b> "
        f"<a href=\"tg://user?id={MICHAEL_TG_ID}\">Michael</a>\n"
        f"Task <code>{tid}</code> blocked {age_h}h — dispatching Probe to research & recommend.\n"
        f"<b>{title[:100]}</b>"
    )
    telegram_post(tg_msg, env)

    print(f"[resolver] dispatch complete for {tid}")


def cmd_resolve(task_id: str):
    """
    Read Probe's response, comment + unblock the Kanban card, update queue.
    """
    queue = load_queue()
    entry = queue.get(task_id, {})

    resp_path = RESPONSE_DIR / f"{task_id}.json"
    if not resp_path.exists():
        print(f"[resolver] no response file for {task_id}, aborting", file=sys.stderr)
        sys.exit(1)

    resp = json.loads(resp_path.read_text(encoding="utf-8"))
    recommendation   = resp.get("recommendation", "")
    confidence       = resp.get("confidence", "medium")
    research_summary = resp.get("research_summary", "")

    title    = entry.get("title", task_id)
    assignee = entry.get("assignee", "")
    age_h    = entry.get("age_h", "?")

    if not recommendation:
        print(f"[resolver] empty recommendation in {resp_path}, aborting", file=sys.stderr)
        sys.exit(1)

    # ── 1. Kanban comment with Probe's recommendation ──────────────────────
    comment_body = f"""## 🤖 Helm Auto-Resolver — Decision

Helm detected this card was blocked for **{age_h}h** awaiting human input.
Probe 🔭 was dispatched to research the blocker.

**Probe's Recommendation** (confidence: {confidence}):
{recommendation}

**Research Summary:**
{research_summary}

*This decision was produced autonomously by Probe and applied by Helm's
auto-resolver. If this is incorrect, Michael can re-block and override.*
"""
    kanban_comment(task_id, comment_body, author="chief_of_staff")

    # ── 2. Unblock the card ────────────────────────────────────────────────
    unblock_reason = (
        f"Auto-resolved by Helm after {age_h}h. "
        f"Probe recommendation (confidence={confidence}): {recommendation[:200]}"
    )
    ok = kanban_unblock(task_id, unblock_reason)

    # ── 3. Update queue ────────────────────────────────────────────────────
    queue[task_id]["status"]      = "resolved"
    queue[task_id]["resolved_at"] = int(time.time())
    queue[task_id]["confidence"]  = confidence
    save_queue(queue)
    print(f"[resolver] queue updated: {task_id} → resolved")

    # ── 4. Fleet confirmation ──────────────────────────────────────────────
    env = _env()
    status_icon = "✅" if ok else "⚠️"
    msg = (
        f"**Helm 🎖️ — Auto-Resolver** {status_icon}\n"
        f"Task `{task_id}` unblocked after **{age_h}h**.\n"
        f"📋 **{title[:100]}** (assignee: {assignee})\n"
        f"🔭 Probe's answer (confidence: {confidence}):\n"
        f"> {recommendation[:350]}\n"
        f"Card is now `ready` — the bot will resume on next dispatch."
    )
    discord_post(msg, env)

    tg_msg = (
        f"✅ <b>Helm Auto-Resolver — Resolved</b>\n"
        f"Task <code>{task_id}</code> unblocked after {age_h}h.\n"
        f"<b>{title[:100]}</b>\n"
        f"Probe (confidence: {confidence}): {recommendation[:250]}"
    )
    telegram_post(tg_msg, env)

    print(f"[resolver] resolve complete for {task_id}")


def cmd_cleanup():
    """Remove resolved entries older than 24h from the queue."""
    queue = load_queue()
    cutoff = int(time.time()) - 86400
    removed = []
    for tid in list(queue.keys()):
        entry = queue[tid]
        if entry.get("status") == "resolved":
            ra = entry.get("resolved_at", 0)
            if ra < cutoff:
                del queue[tid]
                removed.append(tid)
    save_queue(queue)
    print(f"[resolver] cleanup: removed {len(removed)} old entries: {removed}")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: helm_input_resolver.py <dispatch|resolve|cleanup> [arg]",
              file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "dispatch" and len(sys.argv) >= 3:
        cmd_dispatch(sys.argv[2])
    elif cmd == "resolve" and len(sys.argv) >= 3:
        cmd_resolve(sys.argv[2])
    elif cmd == "cleanup":
        cmd_cleanup()
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

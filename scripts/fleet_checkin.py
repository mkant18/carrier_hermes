#!/usr/bin/env python3
"""
fleet_checkin.py — Hourly Fleet Check-in
==========================================
Runs as a Hermes cron (no_agent=True). Mines all 20 bot state.db files for
sessions in the last 65 minutes, then calls ONE OpenRouter gemini-2.5-flash-lite
call PER ACTIVE WING (the LT "writes" a 2-3 sentence wing summary). Idle wings
get zero LLM calls. Broadcasts the assembled report to Discord, Buzz, and Telegram.

Cost: ~$0.0001/run for active wings (essentially $0). Zero tokens from subscription.

Posted as:
  Discord:  **Marshal 🎖️** → #fleet (First Watch REST)
  Buzz:     marshal key → fleet channel (nak kind:9)
  Telegram: hermes send → Fleet Command group

Author: fleet_checkin cron (carrier_hermes)
"""
from __future__ import annotations
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
REPO = Path(r"C:\Users\micha\carrier_hermes")
CARRIER = HOME / "carrier"
NAK = str(CARRIER / "bin" / "nak.exe")
KEYDIR = CARRIER / "buzz-keys"
ENV_FILE = HOME / ".env"
DISPATCH_LOCK = CARRIER / "DISPATCH_LOCK"
SPEND_HALT = CARRIER / "SPEND_HALT"

BUZZ_RELAY = os.environ.get("CARRIER_BUZZ_RELAY", "ws://mks-pc.taileda46c.ts.net:3000")
BUZZ_CHANNELS = json.loads((REPO / "buzz" / "buzz_channels.json").read_text(encoding="utf-8"))
BUZZ_IDENT = json.loads((REPO / "buzz" / "buzz_identities.json").read_text(encoding="utf-8"))
FLEET_BUZZ_UUID = BUZZ_CHANNELS["fleet"]["uuid"]

# ── Wing topology ──────────────────────────────────────────────────────────────
WINGS = [
    {
        "key":      "coding",
        "lt":       "coding_lt",
        "callsign": "Wrench 🔧",
        "emoji":    "🔧",
        "label":    "Coding Wing",
        "bots":     ["coding_lt", "firstmate", "git_yeoman"],
    },
    {
        "key":      "ops",
        "lt":       "ops_lt",
        "callsign": "Deck 🛫",
        "emoji":    "🛫",
        "label":    "Ops Wing",
        "bots":     ["ops_lt", "email_reader", "email_drafter",
                     "calendar_manager", "todoist_manager", "finance_reader"],
    },
    {
        "key":      "knowledge",
        "lt":       "knowledge_lt",
        "callsign": "Stacks 📚",
        "emoji":    "📚",
        "label":    "Knowledge Wing",
        "bots":     ["knowledge_lt", "vault_librarian", "obsidian_archivist"],
    },
    {
        "key":      "recon",
        "lt":       "hermes_ai_explorer",
        "callsign": "Chart 🗺️",
        "emoji":    "🗺️",
        "label":    "Recon Wing",
        "bots":     ["hermes_ai_explorer", "passive_watch", "research_agent"],
    },
]

# Command bots (not LT-wrapped): we mine but don't LLM-summarize
COMMAND_BOTS = ["marshal", "subscription_watcher", "api_watcher", "lockbox"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def mine_bot(bot_id: str, since_ts: float) -> list[dict[str, str]]:
    """Return list of {title, last_msg} for sessions started since since_ts."""
    db_path = HOME / "profiles" / bot_id / "state.db"
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        sessions = conn.execute(
            "SELECT id, title, started_at, ended_at FROM sessions "
            "WHERE started_at > ? ORDER BY started_at ASC",
            (since_ts,),
        ).fetchall()
        results = []
        for s in sessions:
            sid = s["id"]
            last = conn.execute(
                "SELECT content FROM messages WHERE session_id=? AND role='assistant' "
                "ORDER BY id DESC LIMIT 1",
                (sid,),
            ).fetchone()
            last_text = (last["content"] or "").strip() if last else ""
            results.append({
                "title":    (s["title"] or "(untitled)").strip(),
                "last_msg": last_text,
            })
        conn.close()
        return results
    except Exception as e:
        print(f"  [mine_bot] {bot_id}: {e}", file=sys.stderr)
        return []


def build_wing_data(wing: dict, since_ts: float) -> dict[str, Any]:
    """Mine all bots in a wing. Returns {bot_id: [sessions]} dict."""
    data: dict[str, list] = {}
    for bot in wing["bots"]:
        sessions = mine_bot(bot, since_ts)
        if sessions:
            data[bot] = sessions
    return data


def callsign_for(bot_id: str) -> str:
    b = BUZZ_IDENT.get(bot_id, {})
    return f"{b.get('callsign', bot_id)} {b.get('emoji', '')}".strip()


def or_flash_summarize(wing_label: str, lt_callsign: str, wing_data: dict[str, Any],
                       or_key: str, kanban: dict[str, dict]) -> str:
    """
    Call OpenRouter gemini-2.5-flash-lite to have the Lt 'write' a compact
    wing summary. Returns a 2-3 sentence summary string, or falls back gracefully.

    Model: google/gemini-2.5-flash-lite (~$0.015/M in, $0.04/M out → <$0.0001/call)
    This is on the OR allowlist and costs essentially nothing at this scale.
    """
    # Build compact structured input — enrich with kanban title + run_summary
    bot_lines: list[str] = []
    for bot_id, sessions in wing_data.items():
        cs = callsign_for(bot_id)
        for s in sessions:
            title = s["title"]
            # Extract task IDs from this session and enrich
            task_ids = _TASK_ID_RE.findall(title + " " + s.get("last_msg", "")[:300])
            task_detail_parts: list[str] = []
            for tid in task_ids:
                kb = kanban.get(tid)
                if kb:
                    task_detail_parts.append(
                        f'[{tid} "{kb["title"]}" status={kb["status"]}'
                        + (f' outcome: {kb["run_summary"][:200]}' if kb["run_summary"] else "")
                        + "]"
                    )
            # Fall back to last_msg if no kanban detail
            if task_detail_parts:
                detail = " | ".join(task_detail_parts)
            else:
                msg = s.get("last_msg", "")
                if msg and "\n" in msg:
                    lines_clean = [ln.strip() for ln in msg.splitlines()
                                   if ln.strip() and not (ln.strip().startswith("**") and len(ln.strip()) < 60)]
                    detail = " ".join(lines_clean)[:500]
                else:
                    detail = msg[:500]
            bot_lines.append(f"- {cs}: {detail}" if detail else f"- {cs}: [{title}]")

    activity_block = "\n".join(bot_lines) if bot_lines else "(no sessions this hour)"

    system = (
        f"You are {lt_callsign}, Lt of the {wing_label} in a multi-agent AI fleet. "
        "Write a concise 2-3 sentence wing status report. "
        "CRITICAL RULES: Only mention task IDs and outcomes that appear VERBATIM in the activity data below. "
        "Do NOT invent or infer any task names, project names, or outcomes not present in the data. "
        "If the last message is unclear, describe the task ID and status only. "
        "Write in first-person plural (e.g. 'We completed...'). No bullet points. No markdown headers. "
        "No model names or token counts. Speak as the wing lead summarising for the captain."
    )
    user = (
        f"Activity from the past hour in {wing_label} (use ONLY this data — do not infer or invent):\n\n"
        f"{activity_block}\n\n"
        "Write your 2-3 sentence wing summary now, citing only what is stated above."
    )

    payload = json.dumps({
        "model": "google/gemini-2.5-flash-lite",
        "max_tokens": 150,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {or_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://carrier-hermes/fleet-checkin",
            "X-Title": "Fleet Checkin",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [or_summarize] {wing_label}: {e}", file=sys.stderr)
        # Graceful fallback: just list bot titles
        titles = "; ".join(
            s["title"] for sessions in wing_data.values() for s in sessions
        )
        return f"Active this hour: {titles}."


def get_ledger_snapshot() -> dict[str, Any]:
    """Read the ledger probe snapshot JSON written by api_watcher."""
    vault = Path(os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        r"C:\Users\micha\Documents\Obsidian Vault"
    ))
    snap = vault / "_agent" / "api_watcher" / "ledger-snapshot.json"
    if snap.exists():
        try:
            return json.loads(snap.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def format_spend_block(ledger: dict, dispatch_lock: bool, spend_halt: bool) -> str:
    """Build the 📊 Spend & Subs block."""
    lines: list[str] = []

    # Lock/halt status
    lock_str = "🔴 LOCK ACTIVE" if dispatch_lock else "✅ No lock"
    halt_str = "🔴 HALT ACTIVE" if spend_halt else "✅ No halt"
    lines.append(f"• Vigil 📡: {lock_str} | Ledger 📒: {halt_str}")

    # OR spend
    or_data = ledger.get("openrouter", {})
    or_today = or_data.get("usage_today_usd", 0.0)
    or_month = or_data.get("usage_month_usd", 0.0)
    or_remain = or_data.get("limit_remaining_usd")
    if or_today is not None or or_month is not None:
        spend_parts = []
        if or_today is not None:
            spend_parts.append(f"today ${or_today:.2f}")
        if or_month is not None:
            spend_parts.append(f"mo ${or_month:.2f}")
        if or_remain is not None:
            spend_parts.append(f"${or_remain:.2f} remaining")
        lines.append("• OR spend: " + " / ".join(spend_parts))
    else:
        lines.append("• OR spend: (no snapshot yet)")

    # Sub headroom from session_model_usage estimated costs (proxy only)
    anthro_est = ledger.get("anthropic_estimated_usd_today", None)
    xai_est    = ledger.get("xai_estimated_usd_today", None)
    sub_parts: list[str] = []
    if anthro_est is not None:
        sub_parts.append(f"Claude Max ~${anthro_est:.2f} est list-price")
    if xai_est is not None:
        sub_parts.append(f"SuperGrok ~${xai_est:.2f} est list-price")
    if sub_parts:
        lines.append("• Sub usage (est, actual=$0): " + " | ".join(sub_parts))

    return "\n".join(lines)


# ── Kanban enrichment ─────────────────────────────────────────────────────────

KANBAN_DB = HOME / "kanban" / "boards" / "carrier" / "kanban.db"
import re as _re
_TASK_ID_RE = _re.compile(r"\bt_[a-f0-9]{8}\b")


def kanban_enrich(task_ids: list[str]) -> dict[str, dict]:
    """
    Given a list of task IDs, return {task_id: {title, body_short, run_summary,
    status, assignee, trace}} from the carrier kanban.db.
    trace is a compact one-liner: "🛫 claimed → 🛬 done (Xm Ys) by <bot>"
    """
    if not task_ids or not KANBAN_DB.exists():
        return {}
    try:
        conn = sqlite3.connect(str(KANBAN_DB))
        conn.row_factory = sqlite3.Row
        result: dict[str, dict] = {}
        for tid in task_ids:
            task = conn.execute(
                "SELECT id, title, body, assignee, status FROM tasks WHERE id=?", (tid,)
            ).fetchone()
            if not task:
                continue
            # Best run: last completed/blocked run with a summary
            run = conn.execute(
                "SELECT profile, outcome, summary, started_at, ended_at, metadata "
                "FROM task_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (tid,)
            ).fetchone()
            # Build trace from task_events
            events = conn.execute(
                "SELECT kind, payload, created_at FROM task_events "
                "WHERE task_id=? ORDER BY created_at ASC", (tid,)
            ).fetchall()
            trace = _build_trace(events, run)
            run_summary = (run["summary"] or "") if run else ""
            result[tid] = {
                "title":       task["title"] or tid,
                "body_short":  (task["body"] or "")[:120].replace("\n", " "),
                "status":      task["status"],
                "assignee":    task["assignee"],
                "run_summary": run_summary[:400],
                "trace":       trace,
            }
        conn.close()
        return result
    except Exception as e:
        print(f"  [kanban_enrich] {e}", file=sys.stderr)
        return {}


def _build_trace(events, run) -> str:
    """Build a compact trace string from task_events + run timing."""
    icons = {"created": "📋", "assigned": "👤", "claimed": "🛫",
             "spawned": "⚙️", "completed": "🛬", "blocked": "🚧",
             "reclaimed": "♻️", "commented": "💬"}
    key_kinds = {"claimed", "completed", "blocked", "reclaimed", "assigned"}
    parts: list[str] = []
    for e in events:
        kind = e["kind"]
        if kind not in key_kinds:
            continue
        icon = icons.get(kind, "•")
        parts.append(f"{icon} {kind}")
    # Duration from run
    if run and run["started_at"] and run["ended_at"]:
        secs = int(run["ended_at"] - run["started_at"])
        dur = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
        assignee = run["profile"] or ""
        parts.append(f"({dur}, {assignee})")
    return " → ".join(parts) if parts else ""


def extract_task_ids(sessions: list[dict]) -> list[str]:
    """Pull all kanban task IDs out of session titles and last messages."""
    ids: set[str] = set()
    for s in sessions:
        ids.update(_TASK_ID_RE.findall(s.get("title", "")))
        ids.update(_TASK_ID_RE.findall(s.get("last_msg", "")[:300]))
    return list(ids)


def discord_post(token: str, channel_id: str, content: str) -> bool:
    """POST to Discord REST. Returns True on success."""
    # Discord 2000-char limit; trim if needed (shouldn't happen with tight summaries)
    if len(content) > 1990:
        content = content[:1987] + "…"
    payload = json.dumps({
        "content": content,
        "allowed_mentions": {"parse": ["users"]},  # allow user pings only
    }).encode()
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
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.status
        print(f"  [discord] #fleet POST → {code}")
        return code in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"  [discord] HTTPError {e.code}: {e.read()[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [discord] Error: {e}", file=sys.stderr)
        return False


# ── Buzz ──────────────────────────────────────────────────────────────────────

def buzz_post(bot_id: str, text: str, channel: str = "fleet") -> bool:
    """Post a RAW kind:9 message to a Buzz channel as the given bot."""
    sk_path = KEYDIR / f"{bot_id}.sk"
    if not sk_path.exists():
        print(f"  [buzz] no key for {bot_id}", file=sys.stderr)
        return False
    sk = sk_path.read_text().strip()
    uuid = BUZZ_CHANNELS.get(channel, {}).get("uuid")
    if not uuid:
        print(f"  [buzz] unknown channel: {channel}", file=sys.stderr)
        return False
    cmd = [NAK, "event", "-k", "9", "-c", text,
           "--tag", f"h={uuid}", "--sec", sk, "--auth", BUZZ_RELAY]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        out = (r.stdout or "") + (r.stderr or "")
        ok = "success" in out.lower() or r.returncode == 0
        print(f"  [buzz] #{channel} → {'OK' if ok else 'FAIL'}: {out.strip()[:120]}")
        return ok
    except Exception as e:
        print(f"  [buzz] Error: {e}", file=sys.stderr)
        return False


# ── Telegram ──────────────────────────────────────────────────────────────────

def telegram_send(chat_id: str | int, text: str, tg_token: str,
                  mention_uid: str = "") -> bool:
    """Send via Telegram Bot API directly (token from chief_of_staff profile).
    Prepends an inline @mention if mention_uid is set (HTML parse mode)."""
    if not chat_id or not tg_token:
        print(f"  [telegram] missing chat_id or token — skipping", file=sys.stderr)
        return False
    # HTML-escape the body (strip Discord ** markdown, escape HTML special chars)
    import html
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
        f"https://api.telegram.org/bot{tg_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read())
            ok = d.get("ok", False)
            msg_id = d.get("result", {}).get("message_id", "?")
            print(f"  [telegram] send → {'OK' if ok else 'FAIL'} msg_id={msg_id}")
            return ok
    except urllib.error.HTTPError as e:
        print(f"  [telegram] HTTPError {e.code}: {e.read()[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [telegram] Error: {e}", file=sys.stderr)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    now_ts   = time.time()
    since_ts = now_ts - (65 * 60)  # 65-minute window
    env      = load_env()

    or_key           = env.get("OPENROUTER_API_KEY", "")
    discord_token    = env.get("DISCORD_FLEET_BOT_TOKEN", "")
    fleet_channel_id = "1541866443765977138"  # #fleet
    tg_chat_id       = BUZZ_CHANNELS.get("command", {}).get("telegram_chat_id", "")
    michael_uid      = "174349224870150144"

    # Telegram token + user ID for mention — both in chief_of_staff profile
    cos_env_path = HOME / "profiles" / "chief_of_staff" / ".env"
    tg_token = ""
    tg_mention_uid = ""
    if cos_env_path.exists():
        for line in cos_env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tg_token = line.partition("=")[2].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_ALLOWED_USERS="):
                # first user ID in the comma-separated list = Michael
                tg_mention_uid = line.partition("=")[2].strip().split(",")[0].strip()

    now_dt   = datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone(
        timezone(timedelta(hours=-4))  # EDT
    )
    ts_label = now_dt.strftime("%H:%M EDT")

    print(f"[fleet_checkin] {ts_label} | window: last 65 min | since={since_ts:.0f}")

    # ── Phase 1: Mine wing data ────────────────────────────────────────────────
    wing_results: list[dict[str, Any]] = []
    for wing in WINGS:
        data = build_wing_data(wing, since_ts)
        wing_results.append({"wing": wing, "data": data, "active": bool(data)})
        status = f"{len(data)} bots active" if data else "idle"
        print(f"  [mine] {wing['label']}: {status}")

    # Command bots
    command_data: dict[str, list] = {}
    for bot in COMMAND_BOTS:
        sessions = mine_bot(bot, since_ts)
        if sessions:
            command_data[bot] = sessions

    dispatch_lock = DISPATCH_LOCK.exists()
    spend_halt    = SPEND_HALT.exists()
    ledger        = get_ledger_snapshot()

    # ── Phase 2: Collect all task IDs and enrich from kanban ──────────────────
    all_task_ids: list[str] = []
    for wr in wing_results:
        for sessions in wr["data"].values():
            all_task_ids.extend(extract_task_ids(sessions))
    for sessions in command_data.values():
        all_task_ids.extend(extract_task_ids(sessions))
    kanban = kanban_enrich(list(set(all_task_ids)))
    print(f"  [kanban] enriched {len(kanban)}/{len(set(all_task_ids))} task IDs")

    # ── Phase 3: LT summaries (cheap LLM per active wing) ─────────────────────
    if not or_key:
        print("  [warn] OPENROUTER_API_KEY not found — falling back to title-only summaries")

    for wr in wing_results:
        if not wr["active"]:
            wr["summary"] = None  # idle
            continue
        wing = wr["wing"]
        print(f"  [llm] Summarizing {wing['label']} via gemini-2.5-flash-lite ...")
        if or_key:
            wr["summary"] = or_flash_summarize(
                wing["label"], wing["callsign"], wr["data"], or_key, kanban
            )
        else:
            # No key: list titles
            titles = "; ".join(
                s["title"] for sessions in wr["data"].values() for s in sessions
            )
            wr["summary"] = f"Active this hour: {titles}."

    # ── Phase 3: Compose message ───────────────────────────────────────────────
    header = f"**Marshal 🎖️** ⏰ Fleet Check-in | {ts_label} | <@{michael_uid}>\n"

    wing_lines: list[str] = []
    for wr in wing_results:
        wing = wr["wing"]
        bots_str = " · ".join(callsign_for(b) for b in wing["bots"])
        label_line = f"{wing['emoji']} **{wing['label']}** — {bots_str}"
        if wr["active"] and wr.get("summary"):
            # Collect traces for all tasks this wing touched — deduplicated
            seen_tids: set[str] = set()
            trace_lines: list[str] = []
            for sessions in wr["data"].values():
                for tid in extract_task_ids(sessions):
                    if tid in seen_tids:
                        continue
                    seen_tids.add(tid)
                    kb = kanban.get(tid)
                    if kb and kb.get("trace"):
                        short_title = kb["title"][:55] + "…" if len(kb["title"]) > 55 else kb["title"]
                        trace_lines.append(
                            f'  `{tid}` **{short_title}** [{kb["status"]}]\n'
                            f'  ↳ {kb["trace"]}'
                        )
            trace_block = ("\n" + "\n".join(trace_lines)) if trace_lines else ""
            wing_lines.append(f"{label_line}\n{wr['summary']}{trace_block}")
        else:
            wing_lines.append(f"{label_line}\n✅ All quiet this hour.")

    # Command status
    cmd_parts: list[str] = []
    if command_data:
        for bot, sessions in command_data.items():
            cs = callsign_for(bot)
            titles = ", ".join(s["title"] for s in sessions)
            cmd_parts.append(f"• {cs}: {titles}")
    else:
        cmd_parts.append("• Marshal · LockBox: idle")
    cmd_parts_str = "\n".join(cmd_parts)

    spend_block = format_spend_block(ledger, dispatch_lock, spend_halt)

    # Assemble
    sections = [
        header,
        "\n\n".join(wing_lines),
        f"⚓ **Command** — Marshal · Vigil · Ledger · LockBox\n{cmd_parts_str}",
        f"📊 **Spend & Subs**\n{spend_block}",
        "> 🤖 `google/gemini-2.5-flash-lite` · openrouter · ~$0.00",
    ]
    message = "\n\n".join(sections)

    print(f"\n--- COMPOSED MESSAGE ({len(message)} chars) ---")
    print(message)
    print("--- END ---\n")

    # ── Phase 4–6: Broadcast ──────────────────────────────────────────────────
    ok_discord  = False
    ok_buzz     = False
    ok_telegram = False

    # Discord
    if discord_token:
        ok_discord = discord_post(discord_token, fleet_channel_id, message)
    else:
        print("  [discord] no DISCORD_FLEET_BOT_TOKEN — skipping")

    # Buzz — plain text (no Discord markdown for Nostr)
    buzz_text = message.replace("**", "").replace("`", "")
    ok_buzz = buzz_post("marshal", buzz_text, "fleet")

    # Telegram
    if tg_chat_id:
        ok_telegram = telegram_send(tg_chat_id, message, tg_token, tg_mention_uid)
    else:
        print("  [telegram] no chat_id in buzz_channels.json — skipping")

    summary = (
        f"[fleet_checkin] done | discord={'OK' if ok_discord else 'FAIL'} | "
        f"buzz={'OK' if ok_buzz else 'FAIL'} | telegram={'OK' if ok_telegram else 'FAIL'}"
    )
    print(summary)
    return 0 if (ok_discord or ok_buzz or ok_telegram) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
cmd_trace.py — respond to `!trace` and `!trace <flight_id>`

With no argument: shows the 5 most recent flights (closed or open),
with their full event chains (who touched, when, handoffs).

With a flight_id argument: shows that specific flight's full event chain.

Reads: _agent/flights/flights.jsonl  (event log)
       _agent/flights/active_flights.json  (live state for status tag)

Output: Discord-ready message (≤2000 chars per block, or prints multiple
        blocks separated by a blank line — Helm pastes each as a separate
        Discord message if needed).

Usage:
  python3 cmd_trace.py                  # last 5 flights
  python3 cmd_trace.py CODE-20260825-X  # specific flight

Exit 0 on success.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "carrier_hermes"
JSONL_PATH = REPO / "_agent/flights/flights.jsonl"
ACTIVE_PATH = REPO / "_agent/flights/active_flights.json"

BOT_DISPLAY = {
    "chief_of_staff":       "Helm ⚓️",
    "marshal":              "Marshal 🎖️",
    "subscription_watcher": "Vigil 📡",
    "api_watcher":          "Ledger 💵",
    "lockbox":              "LockBox 🔒",
    "coding_lt":            "Wrench 🔧",
    "firstmate":            "Mate ⚙️",
    "git_yeoman":           "Yeoman 📋",
    "ops_lt":               "Deck 🛫",
    "email_reader":         "Inbox 📬",
    "email_drafter":        "Quill 🪶",
    "calendar_manager":     "Chronos 🕰️",
    "todoist_manager":      "Tasker ✅",
    "finance_reader":       "Purse 👛",
    "knowledge_lt":         "Stacks 📚",
    "vault_librarian":      "Librarian 📖",
    "obsidian_archivist":   "Clerk 🗄️",
    "hermes_ai_explorer":   "Chart 🗺️",
    "passive_watch":        "Sonar 🌊",
    "research_agent":       "Probe 🔭",
}

EVENT_ICONS = {
    "OPEN":    "🛫",
    "HANDOFF": "🔄",
    "UPDATE":  "📝",
    "CLOSE":   "🛬",
    "NOTE":    "💬",
}

DEFAULT_N = 5


def _fmt_ts(ts_str: str) -> str:
    """Format ISO ts for display: short UTC."""
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return ts_str


def _age_str(ts_str: str | None) -> str:
    if not ts_str:
        return "?"
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s ago"
        elif s < 3600:
            return f"{s // 60}m ago"
        elif s < 86400:
            return f"{s // 3600}h ago"
        else:
            return f"{s // 86400}d ago"
    except Exception:
        return "?"


def _load_events() -> list[dict]:
    if not JSONL_PATH.exists():
        return []
    events = []
    with open(JSONL_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _load_active() -> dict:
    if not ACTIVE_PATH.exists():
        return {}
    try:
        with open(ACTIVE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _group_by_flight(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by flight_id, preserving insertion order."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        groups[e["flight_id"]].append(e)
    return groups


def _render_flight(flight_id: str, events: list[dict], active: dict) -> str:
    """Render one flight's trace block."""
    # Title from first OPEN event or active map
    title = active.get(flight_id, {}).get("title", "")
    for e in events:
        if e.get("event") == "OPEN" and e.get("title"):
            title = e["title"]
            break
    if not title:
        title = flight_id

    # Status
    is_active = flight_id in active
    if is_active:
        current_bot = active[flight_id].get("current_bot", "?")
        status_str = f"🟡 IN PROGRESS · ball with **{BOT_DISPLAY.get(current_bot, current_bot)}**"
    else:
        status_str = "🛬 CLOSED"

    lines = [
        f"**{flight_id}** — {title}",
        f"Status: {status_str}",
        "",
    ]

    for e in events:
        icon = EVENT_ICONS.get(e.get("event", ""), "▸")
        ts_fmt = _fmt_ts(e.get("ts", ""))
        bot = e.get("bot_id", "?")
        bot_disp = BOT_DISPLAY.get(bot, bot)
        ev_type = e.get("event", "?")
        summary = e.get("summary", "")
        to_bot = e.get("to_bot_id")

        if ev_type == "HANDOFF" and to_bot:
            to_disp = BOT_DISPLAY.get(to_bot, to_bot)
            lines.append(f"  {icon} `{ts_fmt}` **{bot_disp}** → **{to_disp}** · {summary}")
        else:
            lines.append(f"  {icon} `{ts_fmt}` **{bot_disp}** [{ev_type}] · {summary}")

    if events:
        last_ts = events[-1].get("ts")
        lines.append(f"\n  _last event {_age_str(last_ts)}_")

    return "\n".join(lines)


def _recent_flight_ids(groups: dict[str, list[dict]], n: int) -> list[str]:
    """Return up to n flight_ids sorted by their most recent event (desc)."""
    last_ts = {}
    for fid, evs in groups.items():
        last_ts[fid] = max(e.get("ts", "") for e in evs)
    return sorted(groups.keys(), key=lambda x: last_ts[x], reverse=True)[:n]


def main() -> None:
    target_id = sys.argv[1] if len(sys.argv) > 1 else None

    events = _load_events()
    active = _load_active()
    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not events:
        print(f"**Helm ⚓️ !trace** — no flights logged yet. Event log is empty. `{ts_now}`")
        return

    groups = _group_by_flight(events)

    if target_id:
        # Try exact match first, then case-insensitive substring
        matched = None
        if target_id in groups:
            matched = target_id
        else:
            target_lower = target_id.lower()
            for fid in groups:
                if target_lower in fid.lower():
                    matched = fid
                    break
        if not matched:
            print(f"**Helm ⚓️ !trace** — no flight matching `{target_id}` found.")
            print(f"Known flights: {', '.join(sorted(groups.keys()))}")
            return
        header = f"**Helm ⚓️ !trace** `{matched}` — `{ts_now}`\n"
        block = _render_flight(matched, groups[matched], active)
        msg = header + "\n" + block
    else:
        recent_ids = _recent_flight_ids(groups, DEFAULT_N)
        header = f"**Helm ⚓️ !trace** — last {len(recent_ids)} flight(s) `{ts_now}`\n"
        blocks = []
        for fid in recent_ids:
            blocks.append(_render_flight(fid, groups[fid], active))
        msg = header + "\n\n---\n\n".join(blocks)

    # Discord limit check — if over, truncate with note
    if len(msg) > 1980:
        msg = msg[:1940] + "\n…\n_[trace truncated — use `!trace <flight_id>` for one flight]_"

    print(msg)


if __name__ == "__main__":
    main()

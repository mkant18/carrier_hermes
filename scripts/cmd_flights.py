#!/usr/bin/env python3
"""
cmd_flights.py — respond to `!flights`

Reads _agent/flights/active_flights.json and renders a Discord-ready
summary of all in-progress flights and which bot currently holds the ball.

Exit 0 on success.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "carrier_hermes"
ACTIVE_PATH = REPO / "_agent/flights/active_flights.json"

# Callsign lookup for display
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


def _age_str(ts_str: str | None) -> str:
    if not ts_str:
        return "unknown"
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s"
        elif s < 3600:
            return f"{s // 60}m"
        elif s < 86400:
            return f"{s // 3600}h"
        else:
            return f"{s // 86400}d"
    except Exception:
        return "?"


def main() -> None:
    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not ACTIVE_PATH.exists():
        print(f"**Helm ⚓️ !flights** — no active flights on the board. Skies clear. `{ts_now}`")
        return

    try:
        with open(ACTIVE_PATH) as f:
            active: dict = json.load(f)
    except Exception as e:
        print(f"**Helm ⚓️ !flights** — ERROR reading active_flights.json: {e}")
        sys.exit(1)

    if not active:
        print(f"**Helm ⚓️ !flights** — no active flights on the board. Skies clear. `{ts_now}`")
        return

    lines = [f"**Helm ⚓️ !flights** — {len(active)} active sortie(s) `{ts_now}`", ""]

    for flight_id, flight in sorted(active.items(), key=lambda x: x[1].get("opened_at", "")):
        title = flight.get("title", flight_id)
        current_bot = flight.get("current_bot", "?")
        display = BOT_DISPLAY.get(current_bot, current_bot)
        opened_at = flight.get("opened_at")
        last_event = flight.get("last_event_ts")
        job_id = flight.get("job_id") or ""
        age = _age_str(opened_at)
        last_ago = _age_str(last_event)

        job_str = f" · `{job_id}`" if job_id else ""
        lines.append(f"🛫 **{flight_id}**{job_str}")
        lines.append(f"   {title}")
        lines.append(f"   Ball: **{display}** · opened {age} ago · last event {last_ago} ago")
        lines.append("")

    msg = "\n".join(lines).rstrip()

    if len(msg) > 1980:
        msg = msg[:1977] + "…"

    print(msg)


if __name__ == "__main__":
    main()

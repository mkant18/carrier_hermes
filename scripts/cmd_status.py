#!/usr/bin/env python3
"""
cmd_status.py — respond to `!status`

Pings each bot by inspecting:
  1. Their state.json (if any) for last updated_at
  2. Their _agent/<id>/state.json for current mission/phase
  3. Whether DISPATCH_LOCK or SPEND_HALT is set (command tier check)

Output: one Discord message (≤2000 chars) with per-bot status lines.
Helm posts this to #command via fleet_signal or its own gateway.

Exit 0 on success.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path.home() / "carrier_hermes"
CARRIER_HOME = Path.home() / ".hermes" / "carrier"

# Map bot_id → display identity
ROSTER = [
    # (bot_id, callsign, emoji, state_path_relative_to_repo)
    ("chief_of_staff",        "Helm",      "⚓️",  None),
    ("marshal",               "Marshal",   "🎖️",  "_agent/marshal/state.json"),
    ("subscription_watcher",  "Vigil",     "📡",  None),
    ("api_watcher",           "Ledger",    "💵",  "_agent/api_watcher/state.json"),
    ("lockbox",               "LockBox",   "🔒",  None),
    ("coding_lt",             "Wrench",    "🔧",  "_agent/coding_lt/state.json"),
    ("firstmate",             "Mate",      "⚙️",  "_agent/state/firstmate-fleet.json"),
    ("git_yeoman",            "Yeoman",    "📋",  "_agent/git_yeoman/state.json"),
    ("ops_lt",                "Deck",      "🛫",  "_agent/ops_lt/state.json"),
    ("email_reader",          "Inbox",     "📬",  "_agent/email/state.json"),
    ("email_drafter",         "Quill",     "🪶",  None),
    ("calendar_manager",      "Chronos",   "🕰️",  "_agent/calendar/state.json"),
    ("todoist_manager",       "Tasker",    "✅",  "_agent/todoist/state.json"),
    ("finance_reader",        "Purse",     "👛",  None),
    ("knowledge_lt",          "Stacks",    "📚",  "_agent/knowledge_lt/state.json"),
    ("vault_librarian",       "Librarian", "📖",  None),
    ("obsidian_archivist",    "Clerk",     "🗄️",  None),
    ("hermes_ai_explorer",    "Chart",     "🗺️",  "_agent/explorer/state.json"),
    ("passive_watch",         "Sonar",     "🌊",  "_agent/signal_watch/state.json"),
    ("research_agent",        "Probe",     "🔭",  "_agent/research/state.json"),
]

STALE_HOURS = 24  # a state file older than this is "stale"


def _load_json(path: Path) -> dict | None:
    if path and path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _age_str(ts_str: str | None) -> str:
    """Return human-readable age like '2h ago' or 'unknown'."""
    if not ts_str:
        return "unknown"
    try:
        # Accept Z or +00:00
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


def _bot_status(bot_id: str, callsign: str, emoji: str, rel_state: str | None) -> str:
    """Return a single status line for this bot."""
    # Check for profile home existence
    profile_home = Path.home() / ".hermes" / "profiles" / bot_id
    if not profile_home.exists():
        return f"{emoji} **{callsign}** — ⚠️ no profile home"

    state_data = None
    last_seen = None

    if rel_state:
        state_path = REPO / rel_state
        state_data = _load_json(state_path)
        if state_data:
            last_seen = (state_data.get("updated_at")
                         or state_data.get("last_updated")
                         or state_data.get("started_at"))

    # Determine status tag
    if state_data is None:
        tag = "🟢 STANDBY"
        detail = "no active state"
    else:
        phase = state_data.get("phase") or state_data.get("status") or "active"
        mission = state_data.get("mission") or state_data.get("job_id") or ""
        age = _age_str(last_seen)
        blockers = state_data.get("blockers", [])
        if blockers:
            tag = "🔴 BLOCKED"
        elif phase in ("complete", "done", "closed", "trap"):
            tag = "🟢 STANDBY"
            detail = f"last: {mission} ({age})"
        else:
            tag = "🟡 ON STATION"
        detail = f"{mission} [{phase}] — {age}"

    line = f"{emoji} **{callsign}** — {tag}"
    if state_data and "detail" not in locals():
        detail = f"{state_data.get('mission') or state_data.get('job_id', '')} [{state_data.get('phase') or state_data.get('status', 'active')}] — {_age_str(last_seen)}"
    if state_data:
        line += f" · {detail}"

    return line


def _check_locks() -> list[str]:
    """Check DISPATCH_LOCK and SPEND_HALT."""
    warnings = []
    lock = CARRIER_HOME / "DISPATCH_LOCK"
    halt = CARRIER_HOME / "SPEND_HALT"
    if lock.exists():
        try:
            reason = lock.read_text().strip()
        except Exception:
            reason = "reason unknown"
        warnings.append(f"🔴 **DISPATCH_LOCK** SET — {reason}")
    if halt.exists():
        try:
            reason = halt.read_text().strip()
        except Exception:
            reason = "reason unknown"
        warnings.append(f"🔴 **SPEND_HALT** SET — {reason}")
    return warnings


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"**Helm ⚓️ !status** — fleet ping `{ts}`", ""]

    locks = _check_locks()
    if locks:
        lines += locks
        lines.append("")

    for (bot_id, callsign, emoji, rel_state) in ROSTER:
        lines.append(_bot_status(bot_id, callsign, emoji, rel_state))

    msg = "\n".join(lines)

    # Discord hard limit: 2000 chars
    if len(msg) > 1980:
        msg = msg[:1977] + "…"

    print(msg)


if __name__ == "__main__":
    main()

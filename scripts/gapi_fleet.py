#!/usr/bin/env python3
"""Fleet-safe Google Workspace CLI gate for Inbox / Chronos.

Wraps Hermes google-workspace google_api.py and blocks disallowed verbs.
Never enables mail send/reply/forward.

Usage:
  gapi_fleet.py inbox gmail search 'is:unread' --max 5
  gapi_fleet.py inbox gmail get MESSAGE_ID
  gapi_fleet.py chronos calendar list
  gapi_fleet.py chronos calendar create --summary '...' --start ... --end ...
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SKILL_API = (
    Path.home()
    / ".hermes"
    / "skills"
    / "productivity"
    / "google-workspace"
    / "scripts"
    / "google_api.py"
)

# role -> service -> allowed subcommands
ALLOW = {
    "inbox": {
        "gmail": {"search", "get", "labels"},
    },
    "chronos": {
        "calendar": {"list", "create", "delete"},
    },
}

BLOCKED_ANYWHERE = {
    "send",
    "reply",
    "forward",
    "draft",
}


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(
            "Usage: gapi_fleet.py <inbox|chronos> <gmail|calendar> <verb> [args...]",
            file=sys.stderr,
        )
        return 2

    role, service, verb, *rest = argv[1], argv[2], argv[3], argv[4:]
    role = role.lower()
    service = service.lower()
    verb = verb.lower()

    if verb in BLOCKED_ANYWHERE or any(b in verb for b in BLOCKED_ANYWHERE):
        print(f"BLOCKED: '{verb}' is not allowed on the fleet (no mail send path).", file=sys.stderr)
        return 3

    allowed = ALLOW.get(role, {}).get(service)
    if not allowed:
        print(f"BLOCKED: role={role} cannot use service={service}", file=sys.stderr)
        return 3
    if verb not in allowed:
        print(
            f"BLOCKED: {role} {service} allows only: {', '.join(sorted(allowed))}",
            file=sys.stderr,
        )
        return 3

    if not SKILL_API.exists():
        print(f"ERROR: google_api.py missing at {SKILL_API}", file=sys.stderr)
        return 1

    # Prefer profile HERMES_HOME when set by hermes -p; else shared root.
    env = os.environ.copy()
    if not env.get("HERMES_HOME"):
        # Default to shared ~/.hermes so token/secret resolve.
        env["HERMES_HOME"] = str(Path.home() / ".hermes")

    cmd = [sys.executable, str(SKILL_API), service, verb, *rest]
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

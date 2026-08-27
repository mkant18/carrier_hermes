#!/usr/bin/env python3
"""
omb_composio_health.py — Composio gate polarity health check.

Standalone, not part of the billing-guard scripts. Detects the Moss-style
hazard from the Phase 2A pilot: `bot.composio !== false` means "on" in OMB
(opt-out, not opt-in), so any bot created without an explicit `composio`
field is silently Composio-enabled. This script flags that gap so it can be
caught before a bot with tool-calling capability is put on a real model.

Zero LLM calls. Reads bots.json directly — no network beyond the local
filesystem (localhost:8799 is OMB's own API, not needed here since bots.json
is the same data OMB itself reads/writes).

Exit codes: 0 = every bot has an explicit composio field, 1 = at least one
bot is missing it, 2 = bots.json not found/unreadable.

Usage:
    python3 scripts/omb_composio_health.py [--bots-json PATH]
"""
import sys
import os
import json
import argparse

DEFAULT_BOTS_JSON = os.path.join(os.path.expanduser("~"), ".openmausbot", "bots.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bots-json", default=DEFAULT_BOTS_JSON, help="Path to OMB's bots.json")
    args = parser.parse_args()

    if not os.path.isfile(args.bots_json):
        print(f"[ERROR] bots.json not found: {args.bots_json}", file=sys.stderr)
        sys.exit(2)

    try:
        with open(args.bots_json, "r", encoding="utf-8") as f:
            bots = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] could not read/parse bots.json: {e}", file=sys.stderr)
        sys.exit(2)

    missing = [b for b in bots if "composio" not in b]
    enabled = [b for b in bots if b.get("composio") is True]

    print(f"Checked {len(bots)} bot(s) in {args.bots_json}\n")

    if enabled:
        print(f"composio=true ({len(enabled)}):")
        for b in enabled:
            print(f"  - {b.get('name', '?')} ({b.get('id', '?')})")
    else:
        print("composio=true (0): none")

    print()
    if missing:
        print(f"⚠️  MISSING explicit composio field ({len(missing)}) — silently enabled (opt-out polarity):")
        for b in missing:
            print(f"  - {b.get('name', '?')} ({b.get('id', '?')})")
        print("\n→ Set composio:false explicitly on each bot above unless it is meant to be enabled.")
        sys.exit(1)

    print("✅ Every bot has an explicit composio field. No silent-enablement hazard.")
    sys.exit(0)


if __name__ == "__main__":
    main()

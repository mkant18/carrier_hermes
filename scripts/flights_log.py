#!/usr/bin/env python3
"""
flights_log.py — append a flight event to _agent/flights/flights.jsonl
and maintain the active_flights.json live-state map.

Usage:
  python3 flights_log.py --flight-id ID --event OPEN|HANDOFF|UPDATE|CLOSE|NOTE
                         --bot <bot_id> [--to <to_bot_id>]
                         --summary "≤80 chars"
                         [--job-id <todoist_or_kanban_id>]
                         [--title "human title"]   # only needed on OPEN

Events:
  OPEN     — new flight created; --title required; sets current_bot to --bot
  HANDOFF  — custody transfer; --to required; sets current_bot to --to
  UPDATE   — status note; no custody change
  CLOSE    — flight complete; removes from active_flights.json
  NOTE     — free-form annotation; no custody change

Exit 0 on success, non-zero on error. Writes two files atomically (JSONL
append + JSON rewrite via tempfile rename).
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

REPO = os.path.expanduser("~/carrier_hermes")
FLIGHTS_DIR = os.path.join(REPO, "_agent/flights")
JSONL_PATH = os.path.join(FLIGHTS_DIR, "flights.jsonl")
ACTIVE_PATH = os.path.join(FLIGHTS_DIR, "active_flights.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_active() -> dict:
    if not os.path.exists(ACTIVE_PATH):
        return {}
    with open(ACTIVE_PATH) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_active(active: dict) -> None:
    os.makedirs(FLIGHTS_DIR, exist_ok=True)
    tmp = ACTIVE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(active, f, indent=2)
        f.write("\n")
    os.replace(tmp, ACTIVE_PATH)


def append_event(event_obj: dict) -> None:
    os.makedirs(FLIGHTS_DIR, exist_ok=True)
    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(event_obj) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a Carrier Hermes flight event")
    parser.add_argument("--flight-id", required=True, help="Unique flight identifier")
    parser.add_argument("--event", required=True,
                        choices=["OPEN", "HANDOFF", "UPDATE", "CLOSE", "NOTE"],
                        help="Event type")
    parser.add_argument("--bot", required=True, help="bot_id emitting this event")
    parser.add_argument("--to", dest="to_bot", default=None,
                        help="Target bot_id (HANDOFF only)")
    parser.add_argument("--summary", required=True,
                        help="≤80 char human-readable summary")
    parser.add_argument("--job-id", default=None,
                        help="Todoist or Kanban task id (optional)")
    parser.add_argument("--title", default=None,
                        help="Human title (required on OPEN, optional elsewhere)")
    args = parser.parse_args()

    ts = now_iso()

    # --- Validate ---
    if args.event == "OPEN" and not args.title:
        print("ERROR: --title is required for OPEN events", file=sys.stderr)
        sys.exit(1)
    if args.event == "HANDOFF" and not args.to_bot:
        print("ERROR: --to is required for HANDOFF events", file=sys.stderr)
        sys.exit(1)

    # --- Build event record ---
    event_obj: dict = {
        "ts": ts,
        "flight_id": args.flight_id,
        "event": args.event,
        "bot_id": args.bot,
        "summary": args.summary[:160],  # hard cap
    }
    if args.to_bot:
        event_obj["to_bot_id"] = args.to_bot
    if args.job_id:
        event_obj["job_id"] = args.job_id
    if args.title:
        event_obj["title"] = args.title

    # --- Append to JSONL ---
    append_event(event_obj)

    # --- Update active_flights.json ---
    active = load_active()

    if args.event == "OPEN":
        active[args.flight_id] = {
            "flight_id": args.flight_id,
            "title": args.title,
            "status": "in_progress",
            "opened_at": ts,
            "opened_by": args.bot,
            "current_bot": args.bot,
            "last_event_ts": ts,
            "job_id": args.job_id,
        }
    elif args.event == "HANDOFF" and args.flight_id in active:
        active[args.flight_id]["current_bot"] = args.to_bot
        active[args.flight_id]["last_event_ts"] = ts
    elif args.event == "CLOSE" and args.flight_id in active:
        del active[args.flight_id]
    elif args.event in ("UPDATE", "NOTE") and args.flight_id in active:
        active[args.flight_id]["last_event_ts"] = ts

    save_active(active)

    print(f"flights_log: [{args.event}] {args.flight_id} by {args.bot}"
          + (f" → {args.to_bot}" if args.to_bot else ""))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
maintenance_merge_hook.py — called after Yeoman confirms a PR merge.

Usage:
    python maintenance_merge_hook.py --pr <number> --title <title> --sha <sha> --fixes <count>

Appends a JSON line to the merge log so fleet_checkin.py can broadcast it.
"""

import argparse
import json
import os
import time

MERGE_LOG_PATH = (
    r"C:\Users\micha\AppData\Local\hermes\profiles\maintenance_lt"
    r"\home\_agent\maintenance\merge_log.jsonl"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a confirmed PR merge.")
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--title", type=str, required=True, help="PR title")
    parser.add_argument("--sha", type=str, required=True, help="Merge commit SHA")
    parser.add_argument("--fixes", type=int, required=True, help="Number of fixes in PR")
    args = parser.parse_args()

    entry = {
        "ts": int(time.time()),
        "pr": args.pr,
        "title": args.title,
        "sha": args.sha,
        "fixes": args.fixes,
        "wing": "shipwright",
        "announced": False,
    }

    log_dir = os.path.dirname(MERGE_LOG_PATH)
    os.makedirs(log_dir, exist_ok=True)

    with open(MERGE_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    print(f"merge_hook: logged PR #{args.pr} to merge_log.jsonl")


if __name__ == "__main__":
    main()

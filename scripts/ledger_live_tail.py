#!/usr/bin/env python3
"""
Ledger Live Tail — real-time view of Hermes API calls across all profiles.
Tails all ~/.hermes/profiles/*/logs/agent.log simultaneously.
Prints new API call lines as they appear, with per-profile color codes.

Usage:
  python3 ledger_live_tail.py               # follow mode (Ctrl+C to stop)
  python3 ledger_live_tail.py --last 100    # dump last N calls and exit
  python3 ledger_live_tail.py --summary     # running summary every 30s
"""

from __future__ import annotations
import argparse
import glob
import os
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROFILES_DIR = HOME / ".hermes" / "profiles"

LOG_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO "
    r"\[(?P<session>[^\]]+)\] agent\.conversation_loop: "
    r"API call #(?P<num>\d+): model=(?P<model>\S+) provider=(?P<provider>\S+) "
    r"in=(?P<inp>\d+) out=(?P<out>\d+) total=(?P<total>\d+) latency=(?P<lat>[0-9.]+)s"
    r"(?:.*cache=(?P<cache_read>\d+)/\d+)?"
)

# ANSI color palette per profile
PROFILE_COLORS = [
    "\033[36m",   # cyan
    "\033[33m",   # yellow
    "\033[32m",   # green
    "\033[35m",   # magenta
    "\033[34m",   # blue
    "\033[91m",   # bright red
    "\033[92m",   # bright green
    "\033[93m",   # bright yellow
    "\033[94m",   # bright blue
    "\033[95m",   # bright magenta
]
RESET = "\033[0m"
BOLD = "\033[1m"


def get_log_paths() -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(PROFILES_DIR / "*/logs/agent.log")))


def parse_calls_from(log_path: Path, from_line: int = 0) -> tuple[list[dict], int]:
    """Read new lines from log_path starting at from_line. Returns (new_calls, new_line_count)."""
    calls = []
    profile = log_path.parent.parent.name
    try:
        lines = log_path.read_text(errors="replace").splitlines()
        new_lines = lines[from_line:]
        for line in new_lines:
            m = LOG_RE.search(line)
            if m:
                calls.append({
                    "ts": m.group("ts"),
                    "profile": profile,
                    "session_id": m.group("session"),
                    "call_num": int(m.group("num")),
                    "model": m.group("model"),
                    "provider": m.group("provider"),
                    "inp": int(m.group("inp")),
                    "out": int(m.group("out")),
                    "total": int(m.group("total")),
                    "lat": float(m.group("lat")),
                    "cache_read": int(m.group("cache_read") or 0),
                })
        return calls, len(lines)
    except Exception:
        return [], from_line


def format_call(c: dict, color: str = "") -> str:
    model_short = c["model"].split("/")[-1][:22]
    cache_pct = f"{c['cache_read']*100//(c['inp'] or 1)}%cache" if c["cache_read"] else ""
    return (
        f"{color}{c['ts']} "
        f"[{c['profile']:20s}] "
        f"{model_short:22s} "
        f"in={c['inp']:>7,} out={c['out']:>6,} "
        f"lat={c['lat']:>5.1f}s "
        f"{cache_pct}{RESET}"
    )


def dump_last_n(n: int = 100) -> None:
    logs = get_log_paths()
    all_calls = []
    profile_list = sorted({l.parent.parent.name for l in logs})
    color_map = {p: PROFILE_COLORS[i % len(PROFILE_COLORS)] for i, p in enumerate(profile_list)}

    for log in logs:
        calls, _ = parse_calls_from(log, from_line=0)
        all_calls.extend(calls)

    all_calls.sort(key=lambda x: x["ts"])
    recent = all_calls[-n:]

    print(f"{BOLD}=== Last {len(recent)} API calls across {len(logs)} profiles ==={RESET}")
    for c in recent:
        print(format_call(c, color_map.get(c["profile"], "")))

    # Summary
    by_profile: dict[str, dict] = defaultdict(lambda: dict(calls=0, inp=0, out=0))
    for c in all_calls:
        by_profile[c["profile"]]["calls"] += 1
        by_profile[c["profile"]]["inp"] += c["inp"]
        by_profile[c["profile"]]["out"] += c["out"]

    print(f"\n{BOLD}Fleet summary (all-time today):{RESET}")
    for p, d in sorted(by_profile.items(), key=lambda x: x[1]["inp"] + x[1]["out"], reverse=True):
        clr = color_map.get(p, "")
        print(f"  {clr}{p:25s}{RESET} | {d['calls']:4d} calls | {d['inp']+d['out']:>10,} tok")


def follow_mode(summary_interval: int = 0) -> None:
    """Follow all log files and print new API calls as they appear."""
    logs = get_log_paths()
    line_offsets: dict[Path, int] = {}
    profile_list = sorted({l.parent.parent.name for l in logs})
    color_map = {p: PROFILE_COLORS[i % len(PROFILE_COLORS)] for i, p in enumerate(profile_list)}

    # Initialize offsets to current end
    for log in logs:
        try:
            count = len(log.read_text(errors="replace").splitlines())
        except Exception:
            count = 0
        line_offsets[log] = count

    print(f"{BOLD}🔍 Ledger live tail — watching {len(logs)} profiles. Ctrl+C to stop.{RESET}")
    last_summary = time.time()

    running_totals: dict[str, dict] = defaultdict(lambda: dict(calls=0, inp=0, out=0, lat=0.0))

    try:
        while True:
            time.sleep(2)
            for log in logs:
                if not log.exists():
                    continue
                new_calls, new_count = parse_calls_from(log, from_line=line_offsets[log])
                line_offsets[log] = new_count
                for c in new_calls:
                    rt = running_totals[c["profile"]]
                    rt["calls"] += 1
                    rt["inp"] += c["inp"]
                    rt["out"] += c["out"]
                    rt["lat"] += c["lat"]
                    print(format_call(c, color_map.get(c["profile"], "")), flush=True)

            if summary_interval and (time.time() - last_summary) >= summary_interval:
                last_summary = time.time()
                print(f"\n{BOLD}--- Running session totals ---{RESET}")
                for p, d in sorted(running_totals.items(), key=lambda x: x[1]["inp"] + x[1]["out"], reverse=True):
                    if d["calls"]:
                        avg_lat = d["lat"] / d["calls"]
                        clr = color_map.get(p, "")
                        print(f"  {clr}{p:25s}{RESET} | {d['calls']} calls | {d['inp']+d['out']:,} tok | avg lat {avg_lat:.1f}s")
                print()

    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopped.{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ledger live tail")
    parser.add_argument("--last", type=int, default=0, help="Dump last N calls and exit")
    parser.add_argument("--summary", action="store_true", help="Print summary every 30s in follow mode")
    args = parser.parse_args()

    if args.last:
        dump_last_n(args.last)
    else:
        follow_mode(summary_interval=30 if args.summary else 0)

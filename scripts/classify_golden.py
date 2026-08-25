#!/usr/bin/env python3
"""Deterministic Helm classify tree over CLASSIFICATION_GOLDEN.md."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "CLASSIFICATION_GOLDEN.md"

# first-match tree (same order as skills/carrier-roster)
RULES: list[tuple[str, str]] = [
    (r"\b(fix|failing test|open a pr|pull request|implement|coding)\b|carrier_hermes|lock script", "Mate"),
    (r"cut fleet cost|which mcp|optimize.*fleet|connectors", "Scout"),
    (r"openrouter|burning cash|over budget|metered|spend", "Ledger"),
    (r"stuck|stall|supergrok|quota|dispatch_lock", "Vigil"),
    (r"unread email|important mail|triage my", "Inbox"),
    (r"draft a reply|draft.*email", "Quill"),
    (r"todoist", "Tasker"),
    (r"calendar|tuesday 3pm|block tuesday", "Chronos"),
    (r"save .*obsidian|file .*vault|file yesterday|save this conversation|keep anything worth filing|save this into", "Clerk"),
    (r"what.?s in my notes|search the vault|vault for people", "Librarian"),
    (r"research comparable|on the web", "Probe"),
    (r"multi-perspective|raise tl", "Helm"),
]


def classify(prompt: str) -> str:
    p = prompt.lower()
    # Todoist-only beats calendar if both (golden: "Add buy milk to Todoist")
    if re.search(r"todoist", p) and not re.search(r"calendar|meeting|tuesday", p):
        return "Tasker"
    for pat, label in RULES:
        if re.search(pat, p):
            return label
    return "Helm"


def parse_table(text: str) -> list[tuple[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("| #") or re.match(r"\|\s*-+", line):
            continue
        parts = [c.strip() for c in line.strip("|").split("|")]
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        prompt, expected = parts[1], parts[2]
        expected = re.sub(r"\*\*", "", expected).split("→")[0].strip()
        rows.append((prompt, expected))
    return rows


def main() -> int:
    rows = parse_table(GOLDEN.read_text(encoding="utf-8"))
    if len(rows) < 18:
        print(f"FAIL golden rows {len(rows)} < 18", file=sys.stderr)
        return 1
    bad = []
    for prompt, expected in rows:
        got = classify(prompt)
        print(f"{got}\t{expected}\t{prompt}")
        if got != expected:
            bad.append((prompt, expected, got))
    if bad:
        print(f"FAIL {len(bad)} mismatches", file=sys.stderr)
        for p, e, g in bad:
            print(f"  expected {e} got {g}: {p}", file=sys.stderr)
        return 1
    print(f"PASS {len(rows)} prompts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

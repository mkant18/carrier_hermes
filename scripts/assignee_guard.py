#!/usr/bin/env python3
"""
assignee_guard.py — refuse to assign BUILD/EXECUTION Kanban work to bots that
BOT_MATRIX bars from execution tools (monitoring/advisement-only bots).

Rule (BOT_MATRIX.md line ~25): "deliberately barred from execution tools so
they cannot do their squadron's work." Watchers + read-only advisers must never
be given coding/implementation tasks. Command flow for build work is:
    Helm -> Wrench (coding_lt) -> Mate (firstmate)      [code]
    Helm -> Stacks (knowledge_lt) -> Librarian/Clerk    [knowledge]
    Helm -> Deck (ops_lt) -> ops workers                [ops]

BUILD-INELIGIBLE bots (cannot be assignee of an execution/coding task):
  subscription_watcher (Vigil), api_watcher (Ledger)  — monitoring only
  lockbox (LockBox)                                    — secrets broker only
  passive_watch (Sonar)                                — passive feeder only
  research_agent (Probe), hermes_ai_explorer (Chart)   — read-only recon
  vault_librarian (Librarian)                          — query-out only
  email_reader (Inbox), finance_reader (Purse)         — read-only

These bots may still OWN/CONSUME a capability — they just can't BUILD it.

Usage:
  assignee_guard.py <assignee_bot_id> [--kind build|analysis|route]
Exit 0 = allowed; exit 3 = REFUSED (with reason on stderr). analysis/route are
always allowed (Lts route; watchers analyse). Only 'build' is gated.
"""
from __future__ import annotations
import sys

# Bots that must NEVER be the assignee of a BUILD/EXECUTION task.
BUILD_INELIGIBLE = {
    "subscription_watcher": "Vigil — monitoring/advisement only (no delegation/terminal/code_execution)",
    "api_watcher":          "Ledger — spend monitoring only (narrow terminal, no code_execution/delegation)",
    "lockbox":              "LockBox — secrets broker only",
    "passive_watch":        "Sonar — passive ecosystem feeder only",
    "research_agent":       "Probe — read-only research",
    "hermes_ai_explorer":   "Chart — read-only recon/synthesis",
    "vault_librarian":      "Librarian — vault query-out only",
    "email_reader":         "Inbox — Gmail read/triage only",
    "finance_reader":       "Purse — read-only Monarch",
}

# Where build work SHOULD go.
BUILD_TARGETS = "coding_lt (Wrench) -> firstmate (Mate) for code; ops_lt/knowledge_lt for their domains"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: assignee_guard.py <assignee_bot_id> [--kind build|analysis|route]", file=sys.stderr)
        return 2
    assignee = argv[1]
    kind = "build"
    if "--kind" in argv:
        i = argv.index("--kind")
        if i + 1 < len(argv):
            kind = argv[i + 1].lower()

    if kind in ("analysis", "route", "monitor", "advise"):
        print(f"assignee_guard: OK — '{assignee}' may receive {kind} work")
        return 0

    if assignee in BUILD_INELIGIBLE:
        print(
            f"assignee_guard: REFUSE — '{assignee}' is BUILD-INELIGIBLE: "
            f"{BUILD_INELIGIBLE[assignee]}.\n"
            f"  Build/execution work must go to: {BUILD_TARGETS}.\n"
            f"  This bot may OWN/CONSUME the capability, not BUILD it.",
            file=sys.stderr,
        )
        return 3

    print(f"assignee_guard: OK — '{assignee}' may receive build work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

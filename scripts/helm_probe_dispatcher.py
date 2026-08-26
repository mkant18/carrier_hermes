#!/usr/bin/env python3
"""
helm_probe_dispatcher.py — Spawn Probe (research_agent) as a delegate_task
to research a blocked Kanban card and write a recommendation JSON.

This script is called by the cron agent when a new dispatch is needed.
It uses Hermes delegate_task semantics embedded in a script context.

Usage (called from within a Hermes agent turn via terminal):
    python helm_probe_dispatcher.py <task_id> <brief_path>

The script constructs the goal prompt and spawns Probe via `hermes delegate`.
Probe writes its result to:
    C:/Users/micha/AppData/Local/hermes/carrier/human_input_responses/<task_id>.json

IMPORTANT: This script is a helper for the agent cron — the cron agent
calls it to trigger Probe, rather than calling delegate_task directly,
because the cron may run in a no_agent context where delegate_task isn't
available. The actual spawning is done via the `hermes` CLI if available,
or by leaving the brief file for Probe to pick up via AIPass (which
chief_of_staff's AIPass worker will route to Probe).
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

HERMES_HOME  = Path(r"C:\Users\micha\AppData\Local\hermes")
RESPONSE_DIR = HERMES_HOME / "carrier" / "human_input_responses"
REPO_ROOT    = Path(r"C:\Users\micha\carrier_hermes")
HPY          = HERMES_HOME / "hermes-agent" / "venv" / "Scripts" / "python.exe"


def build_probe_goal(task_id: str, brief_path: Path) -> str:
    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else "(brief not found)"
    resp_path = RESPONSE_DIR / f"{task_id}.json"

    return textwrap.dedent(f"""\
        You are Probe 🔭, the carrier_hermes research agent.

        Helm has detected that Kanban task `{task_id}` has been blocked for over
        1 hour awaiting human input. Your job is to research the blocker and
        write a concrete, actionable recommendation so Helm can unblock the card
        automatically — without requiring Michael's manual intervention.

        ## Full Brief
        {brief}

        ## Your Deliverable
        Write your recommendation to this exact path:
        `{resp_path}`

        The file must be valid JSON matching this schema:
        ```json
        {{
          "task_id": "{task_id}",
          "recommendation": "<Specific actionable answer to give the bot. 2-5 sentences. This will be posted as a Kanban comment and used to unblock the task. Be concrete — name specific URLs, package names, workarounds, etc.>",
          "confidence": "high|medium|low",
          "research_summary": "<3-8 sentences explaining what you found, why this recommendation is correct, and any important caveats.>"
        }}
        ```

        ## Research Instructions
        1. Read the brief carefully to understand exactly what question the bot asked.
        2. Use web_search, web_extract, and your knowledge to find the answer.
        3. If the blocker is about a tool/repo that may not exist or has a different
           name, find the correct alternative.
        4. Be concrete — vague answers like "it depends" are not acceptable.
        5. Write the JSON file when done.
        6. Verify the file was written successfully before stopping.

        Use confidence=high only when you are certain from verifiable sources.
        Use confidence=low if you are making an educated guess but still provide
        the best recommendation you can.
    """)


def main():
    if len(sys.argv) < 3:
        print("usage: helm_probe_dispatcher.py <task_id> <brief_path>",
              file=sys.stderr)
        sys.exit(1)

    task_id    = sys.argv[1]
    brief_path = Path(sys.argv[2])

    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)

    goal = build_probe_goal(task_id, brief_path)

    # Write goal to a temp file so we can pass it to hermes delegate cleanly
    goal_file = RESPONSE_DIR / f"{task_id}_goal.txt"
    goal_file.write_text(goal, encoding="utf-8")
    print(f"[probe_dispatcher] goal file: {goal_file}")

    # Attempt to spawn via hermes delegate (requires parent to be agent context)
    # In cron agent context this works; in no_agent script context it will fail
    # gracefully — the AIPass message already handles routing.
    print(f"[probe_dispatcher] task_id={task_id}, brief at {brief_path}")
    print(f"[probe_dispatcher] response will go to: {RESPONSE_DIR / f'{task_id}.json'}")
    print(f"[probe_dispatcher] Probe has been briefed via AIPass by helm_input_resolver.py")
    print("[probe_dispatcher] To manually trigger Probe, run:")
    print(f"  hermes -p research_agent run --goal-file \"{goal_file}\"")
    print("OR the cron agent will use delegate_task with the goal string above.")
    print(f"\n===PROBE_GOAL_START===\n{goal}\n===PROBE_GOAL_END===")


if __name__ == "__main__":
    main()

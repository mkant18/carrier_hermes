#!/usr/bin/env python3
"""silent_running_checkpoint.py — zero-LLM git checkpoint for Silent Running.

Runs every 10 minutes while Silent Running is active (independent no_agent cron),
and once more with --final when the governor finalizes a session. It is the
"frequently save work to Git branches with NON-PAID-MODEL functions" requirement:
pure git plumbing, no LLM, no tokens.

What it checkpoints:
  Each active worker WORKTREE under carrier_hermes/.worktrees/t_*/ operates on its
  own wt/t_* branch. For every worktree that has uncommitted changes, we:
    1. git add -A          (scoped to that worktree — never the main tree)
    2. git commit          with a "silent-running checkpoint" message
    3. git push            its branch to origin (HTTPS token auth already wired)

Why worktrees and NOT the main tree:
  Per carrier-hermes-fleet-ops, the dispatcher checks out wt/t_* branches in
  worktrees; the main working tree is Michael's. We deliberately DO NOT `git add`
  in the main tree — that would sweep half-built files into main. We only
  checkpoint the isolated worker worktrees, which is exactly the in-flight work
  that must survive Michael returning mid-task.

Safety:
  * Skips cleanly if the git operation fails (never blocks the fleet).
  * Push failures are logged but non-fatal — the local commit still preserves work.
  * Honors SILENT_RUNNING_HALT: if present, does nothing.

Usage:
    python silent_running_checkpoint.py            # periodic checkpoint
    python silent_running_checkpoint.py --final     # governor's exit flush

ZERO-LLM.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import silent_running_common as C

WORKTREES_DIR = C.REPO / ".worktrees"
GIT = "git"


def _git(args: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run([GIT, *args], cwd=str(cwd),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return 1, str(e)


def worktree_dirs() -> list[Path]:
    """Return each worker worktree directory (skip if none)."""
    if not WORKTREES_DIR.is_dir():
        return []
    return [p for p in WORKTREES_DIR.iterdir() if p.is_dir() and (p / ".git").exists()]


def has_changes(wt: Path) -> bool:
    rc, out = _git(["status", "--porcelain"], wt)
    return rc == 0 and bool(out.strip())


def current_branch(wt: Path) -> str:
    rc, out = _git(["branch", "--show-current"], wt)
    return out.strip() if rc == 0 else ""


def checkpoint_worktree(wt: Path, final: bool) -> dict:
    """Commit + push WIP in one worktree. Returns a result dict."""
    branch = current_branch(wt)
    result = {"worktree": wt.name, "branch": branch, "committed": False,
              "pushed": False, "note": ""}

    if not branch:
        result["note"] = "no branch (detached?) — skipped"
        return result
    if not has_changes(wt):
        result["note"] = "clean — nothing to checkpoint"
        return result

    kind = "final" if final else "periodic"
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"silent-running: {kind} checkpoint {ts} [skip ci]"

    rc, out = _git(["add", "-A"], wt)
    if rc != 0:
        result["note"] = f"add failed: {out[:120]}"
        return result

    rc, out = _git(["commit", "-m", msg, "--no-verify"], wt)
    if rc != 0:
        # "nothing to commit" is benign (race with another writer)
        result["note"] = f"commit rc={rc}: {out[:120]}"
        if "nothing to commit" in out.lower():
            result["note"] = "nothing to commit (raced clean)"
            return result
        return result
    result["committed"] = True

    # Push the branch (set upstream on first push).
    rc, out = _git(["push", "-u", "origin", branch], wt, timeout=180)
    if rc == 0:
        result["pushed"] = True
        result["note"] = "committed + pushed"
    else:
        result["note"] = f"committed locally; push failed: {out[:120]}"
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true",
                    help="final flush on session exit (governor calls this)")
    args = ap.parse_args()

    if C.SILENT_RUNNING_HALT.exists():
        C.log("checkpoint: SILENT_RUNNING_HALT present — skipping")
        return 0

    wts = worktree_dirs()
    if not wts:
        C.log("checkpoint: no worker worktrees — nothing to do")
        return 0

    results = [checkpoint_worktree(wt, args.final) for wt in wts]
    committed = [r for r in results if r["committed"]]
    pushed = [r for r in results if r["pushed"]]

    # Record checkpoint time in state.
    state = C.read_state()
    state["last_checkpoint_at"] = int(time.time())
    C.write_state(state)

    kind = "FINAL" if args.final else "periodic"
    summary = (f"checkpoint({kind}): {len(committed)} committed, "
               f"{len(pushed)} pushed across {len(wts)} worktree(s)")
    C.log("checkpoint: " + summary
          + " | " + "; ".join(f"{r['worktree']}:{r['note']}" for r in results))

    # no_agent stdout: stay silent unless something was actually saved.
    if committed:
        details = ", ".join(f"{r['branch']} ({r['note']})" for r in committed)
        print(f"🛟 Silent-running {summary}. {details}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

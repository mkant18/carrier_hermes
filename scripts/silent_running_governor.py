#!/usr/bin/env python3
"""silent_running_governor.py — zero-LLM capacity governor for Silent Running.

Runs on a FAST cadence (independent no_agent cron, ~2 min) as the real-time
safety valve BETWEEN Helm's slower 15-min orchestration ticks. It never spends a
token. Two jobs:

  1. CAPACITY CEILING (the 80% hard cap). If CPU or GPU is at/above RUN_CEILING_PCT
     (80%), or the user returned, drop a DISPATCH_LOCK-equivalent brake so no new
     worker units spawn, and if we're mid-session flip the phase to `exiting`.
     When capacity recovers below the ceiling and the user is still idle, lift the
     brake.

  2. EXIT FINALIZE. When phase is `exiting` (set by the gate when the user returns
     or by rule 1), trigger a FINAL git checkpoint of all in-flight work, then set
     phase back to `standby` and clear the session cycle. This is what makes work
     survive the user coming back mid-task.

The governor's brake is a dedicated file, SILENT_RUNNING_BRAKE, NOT the global
DISPATCH_LOCK — so it can't accidentally wedge the daytime fleet. The gate and the
Helm orchestration both honor it via silent_running_common.spawn_allowed().

This is deliberately conservative: on ANY capacity read error the helpers in
silent_running_common return 100.0, which trips the brake (fail-safe toward NOT
spawning). ZERO-LLM.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import silent_running_common as C

BRAKE_FILE = C.CARRIER_DIR / "SILENT_RUNNING_BRAKE"
CHECKPOINT_SCRIPT = C.REPO / "scripts" / "silent_running_checkpoint.py"
HPY = r"C:\Users\micha\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"


def set_brake(reason: str) -> None:
    if not BRAKE_FILE.exists():
        BRAKE_FILE.write_text(f"{int(time.time())} {reason}\n", encoding="utf-8")
        C.log(f"governor: BRAKE set ({reason}) — new worker spawns paused")


def clear_brake() -> None:
    if BRAKE_FILE.exists():
        try:
            BRAKE_FILE.unlink()
            C.log("governor: brake cleared — capacity recovered, spawns allowed")
        except Exception:
            pass


def run_final_checkpoint() -> None:
    """Invoke the zero-LLM git checkpoint script for a final flush on exit."""
    if not CHECKPOINT_SCRIPT.exists():
        C.log("governor: checkpoint script missing — skipping final flush")
        return
    try:
        r = subprocess.run(
            [HPY, str(CHECKPOINT_SCRIPT), "--final"],
            capture_output=True, text=True, timeout=300,
            cwd=str(C.REPO),
        )
        C.log(f"governor: final checkpoint rc={r.returncode} "
              f"{(r.stdout or '').strip()[:200]}")
    except Exception as e:
        C.log(f"governor: final checkpoint error: {e}")


def main() -> int:
    state = C.read_state()
    phase = state.get("phase", C.PHASE_STANDBY)
    cap = C.read_capacity()
    lock = C.locks_present()

    over_ceiling = not cap["ceiling_ok"]
    user_back = not cap["idle_ok"]

    # ── Rule 1: capacity ceiling / user-return brake ──────────────────────────
    if lock:
        set_brake(f"lock:{lock}")
    elif over_ceiling:
        set_brake(f"ceiling cpu={cap['cpu']} gpu={cap['gpu']}")
    elif user_back:
        set_brake("user_active")
    else:
        # Idle and under the ceiling → safe to allow spawns again.
        clear_brake()

    # ── Rule 2: drive the phase machine toward a clean exit ───────────────────
    if phase in (C.PHASE_ENTERING, C.PHASE_RUNNING):
        if user_back or lock:
            state["phase"] = C.PHASE_EXITING
            C.write_state(state)
            C.log(f"governor: phase -> exiting (user_back={user_back} lock={lock})")
            phase = C.PHASE_EXITING

    if phase == C.PHASE_EXITING:
        # Finalize: last checkpoint, then return to standby.
        run_final_checkpoint()
        state["phase"] = C.PHASE_STANDBY
        state["cycle"] = 0
        state["exited_at"] = int(time.time())
        state["last_capacity"] = cap
        C.write_state(state)
        C.log("governor: session finalized -> standby")

    # Emit a compact status line (this script is no_agent → stdout delivered
    # verbatim ONLY if non-empty; keep it empty on the common no-op path to stay
    # silent per the watchdog pattern).
    if phase == C.PHASE_EXITING or over_ceiling or user_back:
        print(f"silent-running governor: phase={state.get('phase')} "
              f"brake={'on' if BRAKE_FILE.exists() else 'off'} "
              f"cpu={cap['cpu']}% gpu={cap['gpu']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

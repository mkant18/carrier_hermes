#!/usr/bin/env python3
"""silent_running_gate.py — Silent Running eligibility gate (cron monitor_script).

Runs FIRST on every tick of the Silent Running cron. Hermes hashes this script's
stdout each tick: UNCHANGED output suppresses the Helm agent turn entirely (no
LLM, no tokens); CHANGED output fires Helm's orchestration turn.

Contract we exploit:
  * When NOT eligible (PC active, over-capacity, locked, or Ollama down) we print
    a STABLE one-line reason. Repeated identical → suppressed → Helm never wakes.
  * When eligible we print a line containing the incrementing CYCLE number, so it
    differs every eligible tick → Helm fires every cadence tick to advance the
    priority ladder.

CRITICAL: raw CPU/GPU numbers are NEVER put in stdout — their jitter would change
the hash every tick and wake Helm even during standby. Capacity is written to the
state file + log only. stdout is intentionally low-cardinality.

Eligibility to BEGIN / CONTINUE (locked policy 2026-08-26):
  input idle >= 10 min  AND  cpu < 40%  AND  gpu < 40%
  AND no DISPATCH_LOCK / SPEND_HALT / SILENT_RUNNING_HALT
  AND Ollama up with qwen2.5:7b-instruct-q4_K_M loaded

Phase transitions written to silent_running_state.json:
  standby  -> entering : first eligible tick (Helm broadcasts "Silent Running, EMCON")
  entering -> running  : subsequent eligible ticks (Helm advances the ladder)
  running  -> exiting  : activity/over-capacity returns (governor finalizes + lifts)
  exiting  -> standby  : written by the governor after final checkpoint

Exit code is always 0; the SUPPRESS/FIRE decision is made by Hermes on the stdout
hash, not the exit code. ZERO-LLM.
"""

from __future__ import annotations

import sys
import time

import silent_running_common as C


def eligibility() -> tuple[bool, str, dict]:
    """Return (eligible, reason, capacity_snapshot)."""
    lock = C.locks_present()
    if lock:
        return False, lock, {}

    cap = C.read_capacity()

    if not C.ollama_ready():
        return False, "ollama_not_ready", cap
    if not cap["idle_ok"]:
        return False, "input_active", cap
    if not cap["headroom_ok"]:
        return False, "insufficient_headroom", cap

    return True, "eligible", cap


def main() -> int:
    eligible, reason, cap = eligibility()
    state = C.read_state()
    phase = state.get("phase", C.PHASE_STANDBY)

    # Persist the capacity snapshot for the governor/ladder (never in stdout).
    if cap:
        state["last_capacity"] = cap

    if eligible:
        cycle = int(state.get("cycle", 0)) + 1
        state["cycle"] = cycle
        if phase in (C.PHASE_STANDBY, C.PHASE_EXITING):
            state["phase"] = C.PHASE_ENTERING
            state["entered_at"] = int(time.time())
            state["cycle"] = cycle = 1  # fresh session — restart cycle count
            new_phase = C.PHASE_ENTERING
        else:
            state["phase"] = C.PHASE_RUNNING
            new_phase = C.PHASE_RUNNING
        C.write_state(state)
        C.log(f"gate: ELIGIBLE cycle={cycle} phase={new_phase} "
              f"cpu={cap['cpu']} gpu={cap['gpu']} idle={cap['idle_s']}s")
        # CHANGING line (cycle increments) -> fires Helm every eligible tick.
        print(f"SILENT_RUNNING: {new_phase.upper()} cycle={cycle}")
        return 0

    # Not eligible. If we were active, hand off to the governor to finalize/exit.
    if phase in (C.PHASE_ENTERING, C.PHASE_RUNNING):
        state["phase"] = C.PHASE_EXITING
        C.write_state(state)
        C.log(f"gate: became INELIGIBLE ({reason}) -> phase=exiting "
              f"(governor will finalize)")
    elif phase == C.PHASE_EXITING:
        # Governor hasn't finalized yet; leave as exiting.
        pass
    else:
        # Already standby — keep capacity fresh but don't churn phase.
        state["phase"] = C.PHASE_STANDBY
        C.write_state(state)

    # STABLE line (reason only, no numbers) -> identical while ineligible -> suppressed.
    print(f"SILENT_RUNNING: STANDBY reason={reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

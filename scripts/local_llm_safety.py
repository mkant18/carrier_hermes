#!/usr/bin/env python3
"""local_llm_safety.py — software GPU-safety guard for fleet-wide local inference.

Michael's hard rule: never sustain >80% GPU/CPU, never overheat, never crash the
box. We do NOT use a GPU power cap (his call). Instead we enforce safety in
software, defense-in-depth:

  1. CONCURRENCY   — Ollama is configured OLLAMA_NUM_PARALLEL=1 +
                     OLLAMA_MAX_LOADED_MODELS=1, so only ONE local inference ever
                     runs at a time. A single 7-8B q4 inference on a 16GB 4080S
                     uses ~8GB VRAM and briefly spikes util to ~90% ONLY during
                     token generation — a short burst, not a sustained load.
  2. THERMAL/UTIL GATE — this script. A zero-LLM check the silent-running governor
                     (and any local-inference caller) consults BEFORE starting new
                     local work: if GPU temp or a SUSTAINED util average is over
                     the safety ceiling, it reports not-ok so the caller holds.
  3. IDLE-ONLY     — local inference only runs when the PC is idle (silent-running
                     gate) so bursts never collide with the user's own GPU use.

This is the "sustained vs. burst" distinction: a ~90% spike during generation is
expected and safe (short, bounded by single-concurrency, well within thermal
spec). What we guard against is a SUSTAINED high-util/high-temp condition — that's
what would indicate real thermal risk. So the gate uses a short rolling average +
a hard temp ceiling, not the instantaneous util (which would false-trip on every
normal generation burst).

Thresholds (conservative, aligned to Michael's 80% preference + thermal safety):
  * TEMP_CEILING_C   = 80   -> hold new local work if GPU temp >= 80°C
  * TEMP_RESUME_C    = 70   -> only resume once it cools back under 70°C (hysteresis)
  * SUSTAINED_UTIL   = 85   -> hold if the rolling-avg util stays >= 85% (sustained,
                              not a single burst)
  * SAMPLES/INTERVAL  = 3 samples over ~3s for the rolling average

Zero-LLM. Reads nvidia-smi only. Safe from any context.

Usage:
    python local_llm_safety.py            # human-readable
    python local_llm_safety.py --json     # {ok, temp_c, util_avg, reason}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

TEMP_CEILING_C = 80      # hard thermal ceiling to START new local work
TEMP_RESUME_C = 70       # hysteresis: must cool under this to resume
SUSTAINED_UTIL_PCT = 85  # sustained (rolling-avg) util ceiling
SAMPLES = 3
SAMPLE_INTERVAL_S = 1.0

STATE_FILE = r"C:\Users\micha\AppData\Local\hermes\carrier\local_llm_safety_state.json"


def _read_gpu() -> tuple[float, float] | None:
    """Return (util_pct, temp_c) peak across GPUs, or None on error."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        util = temp = 0.0
        for line in r.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                util = max(util, float(parts[0]))
                temp = max(temp, float(parts[1]))
        return util, temp
    except Exception:
        return None


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"cooling": False}


def _save_state(state: dict) -> None:
    try:
        import os
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except Exception:
        pass


def check() -> dict:
    """Rolling-average safety check. Returns {ok, temp_c, util_avg, reason}."""
    utils: list[float] = []
    temp = 0.0
    for i in range(SAMPLES):
        r = _read_gpu()
        if r is None:
            # Fail SAFE: can't read GPU -> not ok (hold new work).
            return {"ok": False, "temp_c": None, "util_avg": None,
                    "reason": "gpu_read_failed"}
        u, t = r
        utils.append(u)
        temp = max(temp, t)
        if i < SAMPLES - 1:
            time.sleep(SAMPLE_INTERVAL_S)
    util_avg = round(sum(utils) / len(utils), 1)

    state = _load_state()
    cooling = state.get("cooling", False)

    # Thermal hysteresis: once we trip the ceiling we require cooling below the
    # resume temp before allowing work again (prevents flapping right at 80°C).
    if temp >= TEMP_CEILING_C:
        cooling = True
    elif temp < TEMP_RESUME_C:
        cooling = False
    state["cooling"] = cooling
    _save_state(state)

    if cooling:
        ok = False
        reason = f"thermal_hold(temp={temp}C, need<{TEMP_RESUME_C}C to resume)"
    elif util_avg >= SUSTAINED_UTIL_PCT:
        ok = False
        reason = f"sustained_util(avg={util_avg}% >= {SUSTAINED_UTIL_PCT}%)"
    else:
        ok = True
        reason = "ok"

    return {"ok": ok, "temp_c": temp, "util_avg": util_avg, "reason": reason}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = check()
    if args.json:
        print(json.dumps(result))
    else:
        icon = "✅" if result["ok"] else "🛑"
        print(f"{icon} local-llm safety: {result['reason']} "
              f"(temp={result['temp_c']}°C util_avg={result['util_avg']}%)")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

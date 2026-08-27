#!/usr/bin/env python3
"""silent_running_common.py — shared primitives for the Silent Running subsystem.

Silent Running ("EMCON") is the AFK autonomous-work mode for the carrier_hermes
fleet. When Michael's PC is idle and has spare capacity, the fleet works down a
fixed 6-tier priority ladder using PRIMARILY local LLMs (Ollama/Qwen2.5-7B),
frequently checkpointing to git with NON-PAID (zero-LLM) functions, and reaching
for OAuth models only for high-level decisions / tool calls.

This module is the single source of truth for:
  * capacity reading   — CPU (psutil) + GPU (nvidia-smi CLI, since pynvml is not
                         in the Hermes venv) + input-idle (GetLastInputInfo)
  * threshold policy    — START headroom (40%), RUN ceiling (80% hard cap)
  * the shared state file (silent_running_state.json) + phase machine
  * lock-file / ollama / spend-halt gating

All functions here are ZERO-LLM and safe to call from cron monitor_scripts and
no_agent scripts. Nothing here spends a token.

Design decisions (locked with Michael 2026-08-26):
  * START gate    : input idle >= 10 min AND cpu < 40% AND gpu < 40%
  * RUN ceiling   : hard cap 80% — governor pauses new spawns at/above this
  * pacing        : capacity-gated, up to 2 concurrent worker units
  * Helm cadence  : every 15 min while eligible (the cron schedule)
  * checkpoint    : every 10 min while active (git_yeoman, zero-LLM)
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
CARRIER_DIR = HERMES_HOME / "carrier"
REPO = Path(r"C:\Users\micha\carrier_hermes")

STATE_FILE = CARRIER_DIR / "silent_running_state.json"
LOG_FILE = HERMES_HOME / "logs" / "silent_running.log"

DISPATCH_LOCK = CARRIER_DIR / "DISPATCH_LOCK"
SPEND_HALT = CARRIER_DIR / "SPEND_HALT"
# A manual off-switch for silent-running specifically (create to disable, delete to allow).
SILENT_RUNNING_HALT = CARRIER_DIR / "SILENT_RUNNING_HALT"

KANBAN_DB = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
REQUIRED_MODEL = "llama3.1:8b-instruct-q4_K_M"

# ─── Threshold policy ─────────────────────────────────────────────────────────

IDLE_START_S = 10 * 60      # 10 minutes input-idle required to BEGIN
START_HEADROOM_PCT = 40     # both CPU and GPU must be below this to BEGIN
RUN_CEILING_PCT = 80        # hard cap: never exceed this; governor pauses spawns
MAX_CONCURRENT_UNITS = 2    # capacity-gated concurrency of worker units
CHECKPOINT_INTERVAL_S = 10 * 60   # git checkpoint cadence while active
CPU_SAMPLE_S = 1.0          # psutil cpu_percent sampling window

# Phase machine values written to the state file.
PHASE_STANDBY = "standby"     # not eligible; fleet quiet
PHASE_ENTERING = "entering"   # first eligible tick — Helm should broadcast EMCON
PHASE_RUNNING = "running"     # actively working the ladder
PHASE_EXITING = "exiting"     # activity returned — Helm should do final checkpoint + lift


# ─── Capacity reading ─────────────────────────────────────────────────────────

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_input_idle_seconds() -> float:
    """Seconds since last keyboard/mouse input (system-wide, Win32)."""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0  # fail-safe: assume active
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (tick - lii.dwTime) / 1000.0)
    except Exception:
        return 0.0  # fail-safe: assume active (not idle)


def get_cpu_percent() -> float:
    """Whole-system CPU utilization %, sampled over CPU_SAMPLE_S."""
    try:
        import psutil
        return float(psutil.cpu_percent(interval=CPU_SAMPLE_S))
    except Exception:
        # Fail-safe: report a high value so we DON'T start on a bad reading.
        return 100.0


def get_gpu_percent() -> float:
    """Peak GPU utilization % across all NVIDIA GPUs via nvidia-smi CLI.

    pynvml is not installed in the Hermes venv, so we shell out to nvidia-smi
    (always present with the NVIDIA driver). Returns the max across GPUs.
    Fail-safe: returns 100.0 on any error so we won't start on a bad reading.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return 100.0
        vals = [int(x.strip()) for x in r.stdout.splitlines() if x.strip().isdigit()]
        return float(max(vals)) if vals else 100.0
    except Exception:
        return 100.0


def read_capacity() -> dict:
    """One-shot snapshot of all capacity signals.

    Returns {cpu, gpu, idle_s, headroom_ok, ceiling_ok}.
      headroom_ok — both CPU and GPU strictly below START_HEADROOM_PCT (to BEGIN)
      ceiling_ok  — both CPU and GPU strictly below RUN_CEILING_PCT   (to CONTINUE)
    """
    cpu = get_cpu_percent()
    gpu = get_gpu_percent()
    idle_s = get_input_idle_seconds()
    return {
        "cpu": round(cpu, 1),
        "gpu": round(gpu, 1),
        "idle_s": int(idle_s),
        "idle_ok": idle_s >= IDLE_START_S,
        "headroom_ok": cpu < START_HEADROOM_PCT and gpu < START_HEADROOM_PCT,
        "ceiling_ok": cpu < RUN_CEILING_PCT and gpu < RUN_CEILING_PCT,
    }


# ─── Gating checks ────────────────────────────────────────────────────────────

def locks_present() -> str | None:
    """Return the name of the first blocking lock file present, else None."""
    if SILENT_RUNNING_HALT.exists():
        return "silent_running_halt"
    if DISPATCH_LOCK.exists():
        return "dispatch_lock"
    if SPEND_HALT.exists():
        return "spend_halt"
    return None


# The governor's fast-cadence capacity brake (distinct from DISPATCH_LOCK so it
# never wedges the daytime fleet). Present == pause new silent-running spawns.
SILENT_RUNNING_BRAKE = CARRIER_DIR / "SILENT_RUNNING_BRAKE"


def brake_present() -> bool:
    """True if the governor has engaged the silent-running capacity brake."""
    return SILENT_RUNNING_BRAKE.exists()


def ollama_ready() -> bool:
    """True if Ollama is up AND the required local model is loaded."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
    except Exception:
        return False
    names = [m.get("name", "") for m in body.get("models", [])]
    return any(n == REQUIRED_MODEL or n.startswith(REQUIRED_MODEL + ":") for n in names)


# ─── State file ───────────────────────────────────────────────────────────────

def read_state() -> dict:
    """Read the silent-running state file, or a fresh standby default."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "phase": PHASE_STANDBY,
        "cycle": 0,
        "entered_at": None,
        "last_checkpoint_at": None,
        "updated_at": None,
    }


def write_state(state: dict) -> None:
    """Atomically persist the state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = int(time.time())
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def log(msg: str) -> None:
    """Append a timestamped line to the silent-running log (best-effort)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts}  {msg}\n")
    except Exception:
        pass

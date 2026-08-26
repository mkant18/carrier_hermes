#!/usr/bin/env python3
"""Local LLM idle watcher — starts/stops the HermesOllama Windows service
based on dual-signal idle detection (input idle + GPU idle).

Idle definition:
    GetLastInputInfo idle time >= IDLE_THRESHOLD_S (900s / 15 min)
    AND
    GPU utilization <= GPU_IDLE_PCT (30%) as a 60s rolling average
      (2 consecutive 30s poll samples averaged together)

Debounce:
    Polls every POLL_INTERVAL_S (30s). Requires CONSECUTIVE_NEEDED (2)
    consecutive idle checks before starting the service (i.e. idle must
    hold for a full poll cycle beyond the instantaneous check).

On idle -> `sc start HermesOllama`, then poll GET /api/tags until it
returns 200 (up to 60s), then write status=online to the state file.

On activity (either signal goes non-idle) -> `sc stop HermesOllama`
immediately, and reset the idle streak counter.

State file: C:/Users/micha/AppData/Local/hermes/carrier/local_llm_state.json
    {"status": "online"|"offline"|"starting", "model": "...", "started_at": <unix int>}

Log file: C:/Users/micha/AppData/Local/hermes/logs/local_llm_watcher.log
    Rotating, 10MB max, 3 backups.

pip dependency: pynvml (pip install pynvml)
"""

from __future__ import annotations

import ctypes
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    import pynvml
except ImportError:
    print("ERROR: pynvml not installed. Run: pip install pynvml", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATE_FILE = "C:/Users/micha/AppData/Local/hermes/carrier/local_llm_state.json"
LOG_FILE = "C:/Users/micha/AppData/Local/hermes/logs/local_llm_watcher.log"
MODEL = "qwen2.5:7b-instruct-q4_K_M"
SERVICE_NAME = "HermesOllama"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

IDLE_THRESHOLD_S = 900   # 15 minutes of no keyboard/mouse input
GPU_IDLE_PCT = 30        # GPU utilization below this % counts as idle
POLL_INTERVAL_S = 30     # poll every 30s
CONSECUTIVE_NEEDED = 2   # 2 consecutive idle polls before starting the service
GPU_ROLLING_SAMPLES = 2  # 2 samples * 30s poll interval = 60s rolling average
STARTUP_POLL_TIMEOUT_S = 60
STARTUP_POLL_INTERVAL_S = 2


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("local_llm_watcher")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        str(log_path), maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)

    # Also echo to stdout for interactive debugging / NSSM console capture.
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(stream)
    return logger


log = setup_logging()


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------
def write_state(status: str, started_at: int | None = None) -> None:
    state_path = Path(STATE_FILE)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "model": MODEL,
        "started_at": started_at if started_at is not None else int(time.time()),
    }
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(state_path)


# ---------------------------------------------------------------------------
# Idle signal: keyboard/mouse (GetLastInputInfo)
# ---------------------------------------------------------------------------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        # Fail safe: assume active (not idle) if we can't read it.
        return 0.0
    millis_since_boot = ctypes.windll.kernel32.GetTickCount()
    idle_millis = millis_since_boot - lii.dwTime
    return idle_millis / 1000.0


# ---------------------------------------------------------------------------
# Idle signal: GPU utilization (pynvml), 60s rolling average
# ---------------------------------------------------------------------------
class GpuMonitor:
    def __init__(self) -> None:
        pynvml.nvmlInit()
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self._samples: deque[float] = deque(maxlen=GPU_ROLLING_SAMPLES)

    def sample(self) -> float:
        util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
        self._samples.append(float(util.gpu))
        return sum(self._samples) / len(self._samples)

    def shutdown(self) -> None:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------
def sc_start_service() -> None:
    log.info("Starting service %s ...", SERVICE_NAME)
    subprocess.run(["sc", "start", SERVICE_NAME], capture_output=True, text=True)


def sc_stop_service() -> None:
    log.info("Stopping service %s ...", SERVICE_NAME)
    subprocess.run(["sc", "stop", SERVICE_NAME], capture_output=True, text=True)


def ollama_is_ready() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def wait_for_ollama_ready(timeout_s: int = STARTUP_POLL_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ollama_is_ready():
            return True
        time.sleep(STARTUP_POLL_INTERVAL_S)
    return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> int:
    log.info("local_llm_idle_watcher starting up (model=%s)", MODEL)
    write_state("offline")

    gpu = GpuMonitor()
    idle_streak = 0
    service_running = False

    try:
        while True:
            input_idle_s = get_idle_seconds()
            gpu_avg_pct = gpu.sample()

            input_idle = input_idle_s >= IDLE_THRESHOLD_S
            gpu_idle = gpu_avg_pct <= GPU_IDLE_PCT
            is_idle = input_idle and gpu_idle

            log.info(
                "poll: input_idle_s=%.0f (idle=%s) gpu_avg_pct=%.1f (idle=%s) "
                "-> is_idle=%s streak=%d service_running=%s",
                input_idle_s, input_idle, gpu_avg_pct, gpu_idle, is_idle,
                idle_streak, service_running,
            )

            if is_idle:
                idle_streak += 1
            else:
                if service_running:
                    log.info("Activity detected — stopping HermesOllama immediately.")
                    sc_stop_service()
                    service_running = False
                    write_state("offline")
                idle_streak = 0

            if (
                is_idle
                and idle_streak >= CONSECUTIVE_NEEDED
                and not service_running
            ):
                log.info(
                    "Idle threshold met (%d consecutive checks) — starting HermesOllama.",
                    idle_streak,
                )
                write_state("starting")
                sc_start_service()
                if wait_for_ollama_ready():
                    log.info("HermesOllama is up and responding on /api/tags.")
                    write_state("online")
                    service_running = True
                else:
                    log.warning(
                        "HermesOllama did not become ready within %ds; will retry next poll.",
                        STARTUP_POLL_TIMEOUT_S,
                    )
                    write_state("offline")
                    service_running = False
                    idle_streak = 0

            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        log.info("Shutting down (KeyboardInterrupt).")
    finally:
        gpu.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())

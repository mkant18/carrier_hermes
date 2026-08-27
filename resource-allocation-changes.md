# Resource Allocation Changes — t_040a64d0
Date: 2026-08-26
Task: Increase Resource Allocation (carrier_hermes fleet)

## Problem
Fleet bots were hitting resource exhaustion / OOM errors. Root causes:
1. Docker container memory limit too low (4G) for bots running large local LLM contexts
2. Ollama request timeout (90s) causing spurious timeouts on resource-constrained loads
3. Silent Running gate required `qwen2.5:7b-instruct-q4_K_M` — flagged by error_bug_scanner as
   a crash-loop risk (32K ctx, below the 64K minimum floor)

## Changes Applied

### 1. docker/docker-compose.carrier-fleet.yml
- All 20 bot services: `memory: 4G` → `memory: 6G` (50% increase)
- Added `reservations.memory: 1G` per bot so Docker reserves baseline before limits
- CPU limit unchanged at 2 per bot (not the OOM cause)

### 2. scripts/carrier_vm_manager.py (line ~201)
- `--memory 4g` → `--memory 6g` in the `docker run` arguments for `start_bot_vm()`
- Keeps runtime-launched containers consistent with the Compose file

### 3. scripts/fleet_hardening_loop.py
- `OLLAMA_TIMEOUT = 90` → `OLLAMA_TIMEOUT = 120` (prevents timeout OOM kills on slow inference)
- `MAX_MEM_TOKENS = 600` → `MAX_MEM_TOKENS = 800` (allows richer memory hardening output)

### 4. scripts/silent_running_common.py
- `REQUIRED_MODEL = "qwen2.5:7b-instruct-q4_K_M"` → `REQUIRED_MODEL = "llama3.1:8b-instruct-q4_K_M"`
- `qwen2.5:7b-instruct-q4_K_M` is listed in PHANTOM_MODELS / crash-loop models in error_bug_scanner.py
  (32K ctx, below 64K floor, FIM model with no tool calls)
- `llama3.1:8b-instruct-q4_K_M` is the canonical fleet primary model (GOOD_LOCAL_MODELS set)

## Files Changed
- C:/Users/micha/carrier_hermes/docker/docker-compose.carrier-fleet.yml
- C:/Users/micha/carrier_hermes/scripts/carrier_vm_manager.py
- C:/Users/micha/carrier_hermes/scripts/fleet_hardening_loop.py
- C:/Users/micha/carrier_hermes/scripts/silent_running_common.py

## Note
No restart of running containers is triggered here. These changes take effect:
- Docker Compose: on next `docker compose up --force-recreate`
- carrier_vm_manager.py: on next `start_bot_vm()` call
- fleet_hardening_loop.py + silent_running_common.py: on next cron run (immediate)

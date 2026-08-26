"""
carrier_vm_manager.py — Fleet-wide VM lifecycle management.

Manages start/stop of all carrier fleet bot VMs and reports aggregate status.

Usage:
    python scripts/carrier_vm_manager.py status
    python scripts/carrier_vm_manager.py start
    python scripts/carrier_vm_manager.py stop
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.carrier_bot_vm import BotVM, _docker_available, get_bot_vm

# ── Fleet bot registry ─────────────────────────────────────────────────────────
# The canonical list of bots in the carrier fleet.
# Add new bots here as they're onboarded.
FLEET_BOT_IDS: list[str] = [
    "coding_lt",
    "research_lt",
    "helm",
    "ob1",
    "viking",
    "peers",
]

FLEET_NETWORK = "carrier-fleet"


# ── Network setup ──────────────────────────────────────────────────────────────

def _ensure_fleet_network() -> bool:
    """Create the carrier-fleet Docker network if it doesn't exist."""
    if not _docker_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "network", "inspect", FLEET_NETWORK],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return True  # Already exists
        create = subprocess.run(
            ["docker", "network", "create",
             "--driver", "bridge",
             "--label", "carrier.managed=true",
             FLEET_NETWORK],
            capture_output=True, text=True, timeout=10,
        )
        if create.returncode == 0:
            print(f"[vm_manager] Created Docker network '{FLEET_NETWORK}'")
            return True
        else:
            print(f"[vm_manager] Failed to create network: {create.stderr}")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Fleet operations ───────────────────────────────────────────────────────────

def start_fleet_vms(bot_ids: list[str] | None = None) -> dict:
    """
    Start VMs for all (or specified) fleet bots.

    Returns a dict mapping bot_id -> start result.
    """
    target_bots = bot_ids or FLEET_BOT_IDS
    print(f"[vm_manager] Starting fleet VMs for: {target_bots}")

    if _docker_available():
        _ensure_fleet_network()
    else:
        print("[vm_manager] Docker not available — starting in fallback (temp-dir) mode")

    results: dict = {}

    def _start_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        return bot_id, vm.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="vm-start") as pool:
        futures = {pool.submit(_start_one, bid): bid for bid in target_bots}
        for future in concurrent.futures.as_completed(futures):
            bot_id, result = future.result()
            results[bot_id] = result
            status = result.get("status", "unknown")
            print(f"[vm_manager]   {bot_id}: {status}")

    return results


def stop_fleet_vms(bot_ids: list[str] | None = None) -> dict:
    """
    Stop VMs for all (or specified) fleet bots.

    Returns a dict mapping bot_id -> stop result.
    """
    target_bots = bot_ids or FLEET_BOT_IDS
    print(f"[vm_manager] Stopping fleet VMs for: {target_bots}")

    results: dict = {}

    def _stop_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        return bot_id, vm.stop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="vm-stop") as pool:
        futures = {pool.submit(_stop_one, bid): bid for bid in target_bots}
        for future in concurrent.futures.as_completed(futures):
            bot_id, result = future.result()
            results[bot_id] = result
            status = result.get("status", "unknown")
            print(f"[vm_manager]   {bot_id}: {status}")

    return results


def vm_status(bot_ids: list[str] | None = None) -> dict:
    """
    Return the current status of all (or specified) fleet bot VMs.

    Returns a dict mapping bot_id -> status dict, plus aggregate summary.
    """
    target_bots = bot_ids or FLEET_BOT_IDS
    results: dict = {}

    def _status_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        return bot_id, vm.status()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="vm-status") as pool:
        futures = {pool.submit(_status_one, bid): bid for bid in target_bots}
        for future in concurrent.futures.as_completed(futures):
            bot_id, status = future.result()
            results[bot_id] = status

    running_count = sum(1 for s in results.values() if s.get("running"))
    return {
        "bots": results,
        "summary": {
            "total": len(target_bots),
            "running": running_count,
            "stopped": len(target_bots) - running_count,
            "docker_available": _docker_available(),
        },
    }


def exec_all(command: str, bot_ids: list[str] | None = None) -> dict:
    """Run a command on all (or specified) running fleet VMs."""
    target_bots = bot_ids or FLEET_BOT_IDS
    results: dict = {}

    def _exec_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        if not vm.is_running():
            return bot_id, {"skipped": True, "reason": "not running"}
        return bot_id, vm.exec_cmd(command)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_exec_one, bid): bid for bid in target_bots}
        for future in concurrent.futures.as_completed(futures):
            bot_id, result = future.result()
            results[bot_id] = result

    return results


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "start":
        result = start_fleet_vms()
        print(json.dumps(result, indent=2, default=str))
    elif cmd == "stop":
        result = stop_fleet_vms()
        print(json.dumps(result, indent=2, default=str))
    elif cmd == "status":
        result = vm_status()
        summary = result["summary"]
        print(f"\nFleet VM Status")
        print(f"  Docker: {'available' if summary['docker_available'] else 'unavailable (fallback mode)'}")
        print(f"  Running: {summary['running']}/{summary['total']}")
        for bot_id, status in sorted(result["bots"].items()):
            icon = "✓" if status.get("running") else "✗"
            mode = " [fallback]" if status.get("mode") == "fallback" else ""
            state = status.get("state", "stopped")
            print(f"  {icon} {bot_id}: {state}{mode}")
    elif cmd == "exec":
        command = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "echo hello"
        result = exec_all(command)
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: carrier_vm_manager.py [start|stop|status|exec <command>]")
        sys.exit(1)

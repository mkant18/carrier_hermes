"""
carrier_vm_manager.py — Full VM-per-bot manager using Docker.

All 20 carrier fleet bots get their own Docker container.
This module manages the full lifecycle: build, start, stop, exec, logs, health.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.carrier_bot_vm import _docker_available, get_bot_vm

# ── Constants ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
DOCKER_DIR = REPO_ROOT / "docker"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))

NETWORK_NAME = "carrier-fleet"
IMAGE_NAME = "carrier-bot"

ALL_BOT_IDS: list[str] = [
    "chief_of_staff",
    "marshal",
    "coding_lt",
    "ops_lt",
    "knowledge_lt",
    "maintenance_lt",
    "firstmate",
    "git_yeoman",
    "subscription_watcher",
    "api_watcher",
    "lockbox",
    "passive_watch",
    "research_agent",
    "hermes_ai_explorer",
    "todoist_manager",
    "email_reader",
    "email_drafter",
    "calendar_manager",
    "finance_reader",
    "obsidian_archivist",
]

# Bots represented by the OpenMausBot-style compose file.  Keep this smaller
# compatibility fleet separate from the canonical 20-bot production fleet.
FLEET_BOT_IDS: list[str] = [
    "coding_lt",
    "research_lt",
    "helm",
    "ob1",
    "viking",
    "peers",
]


def _container_name(bot_id: str) -> str:
    return f"carrier-{bot_id}"


def _run(
    cmd: list[str],
    capture: bool = True,
    timeout: int = 60,
) -> tuple[int, str]:
    """Run a subprocess command. Returns (returncode, stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return 1, f"docker not found in PATH"
    except Exception as exc:  # noqa: BLE001
        return 1, f"Error running {cmd}: {exc}"


# ── Public API ────────────────────────────────────────────────────────────────

def build_bot_image() -> bool:
    """
    Build the carrier-bot Docker image.
    Uses docker/Dockerfile.carrier-bot from the repo root.
    Returns True on success.
    """
    dockerfile = DOCKER_DIR / "Dockerfile.carrier-bot"
    if not dockerfile.exists():
        print(f"[vm_manager] ERROR: Dockerfile not found at {dockerfile}")
        return False

    # Generate requirements file if it doesn't exist
    req_file = DOCKER_DIR / "requirements.carrier.txt"
    if not req_file.exists():
        _generate_requirements(req_file)

    print(f"[vm_manager] Building image {IMAGE_NAME}...")
    rc, out = _run(
        [
            "docker", "build",
            "-t", IMAGE_NAME,
            "-f", str(dockerfile),
            str(REPO_ROOT),
        ],
        capture=True,
        timeout=600,
    )
    if rc == 0:
        print(f"[vm_manager] Image {IMAGE_NAME} built OK")
        return True
    print(f"[vm_manager] Build FAILED (rc={rc}):\n{out[-2000:]}")
    return False


def _generate_requirements(req_file: Path) -> None:
    """Generate minimal requirements for carrier bots."""
    req_file.parent.mkdir(parents=True, exist_ok=True)
    # Core deps — minimal set for carrier bot operation
    requirements = [
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "httpx>=0.25.0",
        "anthropic>=0.34.0",
    ]
    req_file.write_text("\n".join(requirements) + "\n")
    print(f"[vm_manager] Generated {req_file}")


def docker_network_create() -> bool:
    """Create the carrier-fleet Docker network if it doesn't exist. Idempotent."""
    # Check if network exists
    rc, out = _run(["docker", "network", "inspect", NETWORK_NAME])
    if rc == 0:
        print(f"[vm_manager] Network {NETWORK_NAME} already exists")
        return True

    rc, out = _run([
        "docker", "network", "create",
        "--driver", "bridge",
        "--subnet", "172.28.0.0/16",
        NETWORK_NAME,
    ])
    if rc == 0:
        print(f"[vm_manager] Network {NETWORK_NAME} created")
        return True
    print(f"[vm_manager] Network create FAILED: {out}")
    return False


def start_bot_vm(bot_id: str) -> bool:
    """
    Start a Docker container for a specific bot.
    Mounts repo read-only and bot profile read-write.
    Returns True if container is running.
    """
    if bot_id not in ALL_BOT_IDS:
        print(f"[vm_manager] Unknown bot_id: {bot_id}")
        return False

    container = _container_name(bot_id)
    profile_dir = HERMES_HOME / "profiles" / bot_id / "_agent"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Check if already running
    rc, out = _run(["docker", "inspect", "--format", "{{.State.Status}}", container])
    if rc == 0 and out.strip() == "running":
        print(f"[vm_manager] {container} already running")
        return True

    # Remove if exists but not running
    if rc == 0:
        _run(["docker", "rm", "-f", container])

    repo_path = str(REPO_ROOT).replace("\\", "/")
    profile_path = str(profile_dir).replace("\\", "/")

    rc, out = _run([
        "docker", "run",
        "--detach",
        "--name", container,
        "--network", NETWORK_NAME,
        "--volume", f"{repo_path}:/repo:ro",
        "--volume", f"{profile_path}:/profile:rw",
        "--env", f"HERMES_BOT_ID={bot_id}",
        "--env", f"HERMES_PROFILE={bot_id}",
        "--env", "CARRIER_PEERS_BROKER_URL=http://host.docker.internal:9876",
        "--env", "PYTHONUNBUFFERED=1",
        "--cpus", "2",
        "--memory", "6g",
        "--restart", "unless-stopped",
        IMAGE_NAME,
    ], timeout=30)

    if rc == 0:
        print(f"[vm_manager] Started {container}")
        return True
    print(f"[vm_manager] Start FAILED for {container}: {out}")
    return False


def stop_bot_vm(bot_id: str) -> bool:
    """Stop and remove a bot's Docker container. Returns True on success."""
    container = _container_name(bot_id)

    # Stop gracefully
    rc_stop, _ = _run(["docker", "stop", "--time", "10", container])

    # Remove
    rc_rm, out = _run(["docker", "rm", container])

    if rc_rm == 0 or rc_stop == 0:
        print(f"[vm_manager] Stopped and removed {container}")
        return True
    print(f"[vm_manager] Stop/remove failed for {container}: {out}")
    return False


def exec_in_bot_vm(bot_id: str, command: str) -> tuple[int, str]:
    """
    Execute a shell command inside a bot's running container.
    Returns (returncode, stdout_string).
    """
    container = _container_name(bot_id)
    rc, out = _run([
        "docker", "exec",
        container,
        "/bin/bash", "-c", command,
    ], timeout=120)
    return rc, out


def vm_status_all() -> dict[str, dict]:
    """
    Return a status dict for all 20 bots.
    Each value: {'status': str, 'image': str, 'created': str, 'error': str|None}
    """
    status: dict[str, dict] = {}

    # Batch inspect all containers at once
    container_names = [_container_name(bid) for bid in ALL_BOT_IDS]
    rc, out = _run(
        ["docker", "inspect"] + container_names,
        timeout=30,
    )

    inspected: dict[str, dict] = {}
    if rc == 0 and out:
        try:
            data = json.loads(out)
            for item in data:
                name = item.get("Name", "").lstrip("/")
                # Extract bot_id from container name (carrier-<bot_id>)
                if name.startswith("carrier-"):
                    bid = name[len("carrier-"):]
                    inspected[bid] = item
        except json.JSONDecodeError:
            pass

    for bot_id in ALL_BOT_IDS:
        if bot_id in inspected:
            item = inspected[bot_id]
            state = item.get("State", {})
            config = item.get("Config", {})
            status[bot_id] = {
                "status": state.get("Status", "unknown"),
                "running": state.get("Running", False),
                "image": config.get("Image", IMAGE_NAME),
                "created": item.get("Created", ""),
                "started_at": state.get("StartedAt", ""),
                "pid": state.get("Pid", 0),
                "exit_code": state.get("ExitCode", 0),
                "error": state.get("Error") or None,
            }
        else:
            status[bot_id] = {
                "status": "absent",
                "running": False,
                "image": IMAGE_NAME,
                "created": "",
                "started_at": "",
                "pid": 0,
                "exit_code": 0,
                "error": "Container does not exist",
            }

    return status


def start_fleet() -> dict[str, bool]:
    """
    Start all 20 bot containers.
    Returns {bot_id: success_bool}.
    """
    print("[vm_manager] Starting carrier fleet...")
    docker_network_create()

    results: dict[str, bool] = {}
    for bot_id in ALL_BOT_IDS:
        results[bot_id] = start_bot_vm(bot_id)

    running = sum(1 for v in results.values() if v)
    print(f"[vm_manager] Fleet start: {running}/{len(ALL_BOT_IDS)} running")
    return results


def stop_fleet() -> dict[str, bool]:
    """
    Stop all 20 bot containers.
    Returns {bot_id: success_bool}.
    """
    print("[vm_manager] Stopping carrier fleet...")
    results: dict[str, bool] = {}
    for bot_id in ALL_BOT_IDS:
        results[bot_id] = stop_bot_vm(bot_id)

    stopped = sum(1 for v in results.values() if v)
    print(f"[vm_manager] Fleet stop: {stopped}/{len(ALL_BOT_IDS)} stopped")
    return results


def vm_logs(bot_id: str, tail: int = 50) -> str:
    """Return the last `tail` lines of logs from a bot's container."""
    container = _container_name(bot_id)
    rc, out = _run([
        "docker", "logs",
        "--tail", str(tail),
        "--timestamps",
        container,
    ], timeout=15)
    if rc != 0 and not out:
        return f"[vm_manager] No logs available for {container}"
    return out


def ensure_bot_vm_running(bot_id: str) -> bool:
    """
    Idempotent: ensure bot container is running.
    No-op if already running; starts it if absent or stopped.
    Returns True if running after the call.
    """
    container = _container_name(bot_id)
    rc, out = _run(["docker", "inspect", "--format", "{{.State.Status}}", container])

    if rc == 0:
        current_status = out.strip()
        if current_status == "running":
            return True  # Already running — no-op
        if current_status in ("exited", "created", "paused"):
            # Try to restart existing container
            rc2, _ = _run(["docker", "start", container])
            if rc2 == 0:
                print(f"[vm_manager] Restarted {container} (was {current_status})")
                return True
            # Container is broken — remove and recreate
            _run(["docker", "rm", "-f", container])

    # Container doesn't exist or couldn't restart — create fresh
    return start_bot_vm(bot_id)


def vm_health_summary() -> str:
    """
    Return FLEET_HEALTHY or FLEET_DEGRADED:N_down.
    Stable string — safe for hash-suppressed crons.
    """
    status = vm_status_all()
    down = [bid for bid, s in status.items() if not s.get("running")]
    if not down:
        return "FLEET_HEALTHY"
    return f"FLEET_DEGRADED:{len(down)}_down"


# ── OpenMausBot-compatible fleet API ─────────────────────────────────────────

def _parallel_botvm_call(bot_ids: list[str], method: str, max_workers: int) -> dict:
    """Call a BotVM method in parallel for the compose-managed compatibility fleet."""
    results: dict = {}

    def _call_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        return bot_id, getattr(vm, method)()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_call_one, bot_id) for bot_id in bot_ids]
        for future in concurrent.futures.as_completed(futures):
            bot_id, result = future.result()
            results[bot_id] = result
    return results


def start_fleet_vms(bot_ids: list[str] | None = None) -> dict:
    """Start the OpenMausBot-style fleet, using local fallback when Docker is absent."""
    target_bots = bot_ids or FLEET_BOT_IDS
    if _docker_available():
        docker_network_create()
    else:
        print("[vm_manager] Docker unavailable; using BotVM fallback workspaces")
    return _parallel_botvm_call(target_bots, "start", max_workers=4)


def stop_fleet_vms(bot_ids: list[str] | None = None) -> dict:
    """Stop the OpenMausBot-style fleet."""
    return _parallel_botvm_call(bot_ids or FLEET_BOT_IDS, "stop", max_workers=4)


def vm_status(bot_ids: list[str] | None = None) -> dict:
    """Return per-bot and aggregate status for the OpenMausBot-style fleet."""
    target_bots = bot_ids or FLEET_BOT_IDS
    results = _parallel_botvm_call(target_bots, "status", max_workers=8)
    running_count = sum(1 for status in results.values() if status.get("running"))
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
    """Execute a command in each running OpenMausBot-style fleet VM."""
    target_bots = bot_ids or FLEET_BOT_IDS
    results: dict = {}

    def _exec_one(bot_id: str) -> tuple[str, dict]:
        vm = get_bot_vm(bot_id)
        if not vm.is_running():
            return bot_id, {"skipped": True, "reason": "not running"}
        return bot_id, vm.exec_cmd(command)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_exec_one, bot_id) for bot_id in target_bots]
        for future in concurrent.futures.as_completed(futures):
            bot_id, result = future.result()
            results[bot_id] = result
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carrier VM Manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("build", help="Build carrier-bot image")
    sub.add_parser("network", help="Create carrier-fleet network")
    sub.add_parser("start-fleet", help="Start all 20 bots")
    sub.add_parser("stop-fleet", help="Stop all 20 bots")
    status_p = sub.add_parser("status", help="Show status of all bots")
    status_p.add_argument(
        "--openmaus",
        action="store_true",
        help="Show the six-bot OpenMausBot-compatible fleet",
    )
    sub.add_parser("health", help="Print FLEET_HEALTHY or FLEET_DEGRADED:N")

    start_p = sub.add_parser("start", help="Start one bot, or the OpenMausBot fleet")
    start_p.add_argument("bot_id", nargs="?")

    stop_p = sub.add_parser("stop", help="Stop one bot, or the OpenMausBot fleet")
    stop_p.add_argument("bot_id", nargs="?")

    log_p = sub.add_parser("logs", help="Show logs for a bot")
    log_p.add_argument("bot_id")
    log_p.add_argument("--tail", type=int, default=50)

    exec_p = sub.add_parser("exec", help="Execute in one bot, or across the OpenMausBot fleet")
    exec_p.add_argument("target_or_command")
    exec_p.add_argument("command", nargs="?")

    ensure_p = sub.add_parser("ensure", help="Ensure a bot VM is running")
    ensure_p.add_argument("bot_id")

    args = parser.parse_args()

    if args.cmd == "build":
        sys.exit(0 if build_bot_image() else 1)
    elif args.cmd == "network":
        sys.exit(0 if docker_network_create() else 1)
    elif args.cmd == "start-fleet":
        results = start_fleet()
        for bid, ok in results.items():
            print(f"  {'✓' if ok else '✗'} {bid}")
        sys.exit(0 if all(results.values()) else 1)
    elif args.cmd == "stop-fleet":
        results = stop_fleet()
        for bid, ok in results.items():
            print(f"  {'✓' if ok else '✗'} {bid}")
    elif args.cmd == "status":
        if args.openmaus:
            print(json.dumps(vm_status(), indent=2, default=str))
        else:
            status = vm_status_all()
            for bid, s in status.items():
                icon = "✓" if s["running"] else "✗"
                print(f"  {icon} {bid:30} {s['status']:12} {s.get('error') or ''}")
    elif args.cmd == "health":
        print(vm_health_summary())
    elif args.cmd == "start":
        if args.bot_id:
            sys.exit(0 if start_bot_vm(args.bot_id) else 1)
        print(json.dumps(start_fleet_vms(), indent=2, default=str))
    elif args.cmd == "stop":
        if args.bot_id:
            sys.exit(0 if stop_bot_vm(args.bot_id) else 1)
        print(json.dumps(stop_fleet_vms(), indent=2, default=str))
    elif args.cmd == "logs":
        print(vm_logs(args.bot_id, tail=args.tail))
    elif args.cmd == "exec":
        if args.command is None:
            print(json.dumps(exec_all(args.target_or_command), indent=2, default=str))
        else:
            rc, out = exec_in_bot_vm(args.target_or_command, args.command)
            print(out)
            sys.exit(rc)
    elif args.cmd == "ensure":
        sys.exit(0 if ensure_bot_vm_running(args.bot_id) else 1)
    else:
        parser.print_help()

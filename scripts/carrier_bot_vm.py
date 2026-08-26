"""
carrier_bot_vm.py — Docker-based VM-per-bot scaffold for the carrier fleet.

Each bot runs in its own isolated Docker container (or temp directory fallback
when Docker is unavailable). Inspired by OpenMausBot's per-bot cloud computer
pattern from server/drivers/claude.ts.

Usage:
    from scripts.carrier_bot_vm import get_bot_vm

    vm = get_bot_vm("coding_lt")
    vm.start()
    result = vm.exec_cmd("python scripts/smoke_fleet.sh")
    print(vm.status())
    vm.stop()
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "C:/Users/micha/AppData/Local/hermes"))
CARRIER_HERMES_REPO = Path("C:/Users/micha/carrier_hermes")
BOT_PROFILES_DIR = HERMES_HOME / "profiles"
FLEET_NETWORK = "carrier-fleet"
IMAGE_NAME = "carrier-bot-vm:latest"
RESOURCE_CPUS = "2"
RESOURCE_MEMORY = "4g"


# ── Docker availability check ──────────────────────────────────────────────────

def _docker_available() -> bool:
    """Return True if the docker CLI is on PATH and the daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── BotVM class ────────────────────────────────────────────────────────────────

@dataclass
class BotVM:
    """
    Represents a single bot's isolated execution environment.

    Uses Docker when available, falls back to a temp directory workspace.
    """

    bot_id: str
    container_name: str = field(init=False)
    workspace_path: Path = field(init=False)
    _use_docker: bool = field(init=False, default=False)
    _fallback_dir: Optional[Path] = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.container_name = f"carrier-bot-{self.bot_id}"
        self._use_docker = _docker_available()

        if self._use_docker:
            self.workspace_path = Path(f"/workspace/{self.bot_id}")
        else:
            # Fallback: temp dir on the host
            self._fallback_dir = Path(tempfile.gettempdir()) / f"carrier-bot-{self.bot_id}"
            self._fallback_dir.mkdir(parents=True, exist_ok=True)
            self.workspace_path = self._fallback_dir

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> dict:
        """Start the bot VM. Returns a status dict."""
        if not self._use_docker:
            return {
                "bot_id": self.bot_id,
                "mode": "fallback",
                "workspace": str(self.workspace_path),
                "status": "running",
                "message": "Docker unavailable — using temp directory fallback",
            }

        if self.is_running():
            return {"bot_id": self.bot_id, "status": "already_running", "container": self.container_name}

        bot_profile = BOT_PROFILES_DIR / self.bot_id
        bot_profile.mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker", "run",
            "--detach",
            "--name", self.container_name,
            "--network", FLEET_NETWORK,
            "--cpus", RESOURCE_CPUS,
            "--memory", RESOURCE_MEMORY,
            "--restart", "unless-stopped",
            # Mount carrier_hermes repo (read-only)
            "--volume", f"{CARRIER_HERMES_REPO}:/app/carrier_hermes:ro",
            # Mount bot's profile data (read-write)
            "--volume", f"{bot_profile}:/app/bot-profile:rw",
            # Environment
            "--env", f"BOT_ID={self.bot_id}",
            "--env", f"HERMES_HOME=/app/bot-profile",
            "--label", f"carrier.bot_id={self.bot_id}",
            "--label", "carrier.managed=true",
            IMAGE_NAME,
            "sleep", "infinity",  # Keep container running; exec_cmd sends commands
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                container_id = result.stdout.strip()
                return {
                    "bot_id": self.bot_id,
                    "status": "started",
                    "container": self.container_name,
                    "container_id": container_id[:12],
                }
            else:
                return {
                    "bot_id": self.bot_id,
                    "status": "error",
                    "error": result.stderr.strip(),
                }
        except subprocess.TimeoutExpired:
            return {"bot_id": self.bot_id, "status": "error", "error": "docker start timed out"}

    def stop(self) -> dict:
        """Stop and remove the bot VM container."""
        if not self._use_docker:
            return {"bot_id": self.bot_id, "mode": "fallback", "status": "stopped"}

        if not self.is_running():
            return {"bot_id": self.bot_id, "status": "not_running"}

        # Stop then remove
        for action in ("stop", "rm"):
            try:
                subprocess.run(
                    ["docker", action, self.container_name],
                    capture_output=True, text=True, timeout=15,
                )
            except subprocess.TimeoutExpired:
                pass

        return {"bot_id": self.bot_id, "status": "stopped", "container": self.container_name}

    def exec_cmd(self, command: str) -> dict:
        """Execute a command inside the bot VM."""
        if not self._use_docker:
            # Fallback: run in the temp dir
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=120, cwd=str(self.workspace_path),
                )
                return {
                    "bot_id": self.bot_id,
                    "mode": "fallback",
                    "command": command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
            except subprocess.TimeoutExpired:
                return {"bot_id": self.bot_id, "command": command, "error": "timeout"}

        if not self.is_running():
            return {"bot_id": self.bot_id, "error": "container not running", "command": command}

        try:
            result = subprocess.run(
                ["docker", "exec", self.container_name, "sh", "-c", command],
                capture_output=True, text=True, timeout=120,
            )
            return {
                "bot_id": self.bot_id,
                "container": self.container_name,
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"bot_id": self.bot_id, "command": command, "error": "exec timeout"}

    def status(self) -> dict:
        """Return current status of this bot VM."""
        if not self._use_docker:
            return {
                "bot_id": self.bot_id,
                "mode": "fallback",
                "workspace": str(self.workspace_path),
                "running": True,
                "docker_available": False,
            }

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{.State.Status}}|{{.State.StartedAt}}|{{.Id}}",
                 self.container_name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("|")
                state = parts[0] if parts else "unknown"
                started_at = parts[1] if len(parts) > 1 else ""
                cid = parts[2][:12] if len(parts) > 2 else ""
                return {
                    "bot_id": self.bot_id,
                    "container": self.container_name,
                    "state": state,
                    "running": state == "running",
                    "started_at": started_at,
                    "container_id": cid,
                    "docker_available": True,
                }
            else:
                return {
                    "bot_id": self.bot_id,
                    "container": self.container_name,
                    "state": "not_found",
                    "running": False,
                    "docker_available": True,
                }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"bot_id": self.bot_id, "running": False, "error": "docker not available"}

    def is_running(self) -> bool:
        """Return True if the container is running."""
        return self.status().get("running", False)


# ── Factory / registry ─────────────────────────────────────────────────────────

_vm_registry: dict[str, BotVM] = {}
_registry_lock = __import__("threading").Lock()


def get_bot_vm(bot_id: str) -> BotVM:
    """
    Factory: return (or create) the BotVM for the given bot_id.
    Instances are cached in a process-level registry.
    """
    with _registry_lock:
        if bot_id not in _vm_registry:
            _vm_registry[bot_id] = BotVM(bot_id=bot_id)
        return _vm_registry[bot_id]


def list_registered_vms() -> list[str]:
    """Return the list of bot IDs with registered VM instances."""
    return list(_vm_registry.keys())


# ── Smoke test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Docker available:", _docker_available())

    vm = get_bot_vm("test-bot")
    print("VM:", vm.container_name)
    print("Workspace:", vm.workspace_path)

    result = vm.exec_cmd("echo hello from carrier bot vm")
    print("exec_cmd result:", result)

    print("status:", vm.status())
    print("is_running:", vm.is_running())

    vm2 = get_bot_vm("test-bot")
    assert vm2 is vm, "Factory should return the same cached instance"
    print("Factory cache: OK")

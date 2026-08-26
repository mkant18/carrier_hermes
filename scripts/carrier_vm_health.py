#!/usr/bin/env python3
"""
carrier_vm_health.py — VM health cron monitor (no_agent, stdlib only).

Checks all 20 carrier bot containers.
Prints FLEET_HEALTHY or FLEET_DEGRADED:N_down (stable for hash-suppression).
On degraded: posts alert to Discord fleet channel via First Watch REST.

NO external dependencies — stdlib only.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

DISCORD_CHANNEL_ID = "1541866378255011980"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))

ALL_BOT_IDS = [
    "chief_of_staff", "marshal", "coding_lt", "ops_lt", "knowledge_lt",
    "maintenance_lt", "firstmate", "git_yeoman", "subscription_watcher",
    "api_watcher", "lockbox", "passive_watch", "research_agent",
    "hermes_ai_explorer", "todoist_manager", "email_reader", "email_drafter",
    "calendar_manager", "finance_reader", "obsidian_archivist",
]


# ── Token ─────────────────────────────────────────────────────────────────────

def _get_token() -> str:
    token = os.environ.get("DISCORD_FLEET_BOT_TOKEN", "")
    if token:
        return token
    try:
        result = subprocess.run(
            ["doppler", "secrets", "get", "DISCORD_FLEET_BOT_TOKEN",
             "--plain", "--project", "carrier-ops", "--config", "prd"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


# ── Docker health check ───────────────────────────────────────────────────────

def _check_containers() -> dict[str, str]:
    """
    Run docker ps --format json and check which containers are running.
    Returns {bot_id: 'running'|'absent'|'stopped'}.
    """
    status: dict[str, str] = {bid: "absent" for bid in ALL_BOT_IDS}

    try:
        # docker ps --format json lists only RUNNING containers
        result = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return status

        running_names: set[str] = set()
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                name = obj.get("Names", "").lstrip("/")
                running_names.add(name)
            except json.JSONDecodeError:
                pass

        for bid in ALL_BOT_IDS:
            container = f"carrier-{bid}"
            if container in running_names:
                status[bid] = "running"

        # Check stopped containers (docker ps -a for non-running)
        result_all = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result_all.returncode == 0:
            for line in result_all.stdout.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    name = obj.get("Names", "").lstrip("/")
                    container_status = obj.get("Status", "")
                    if name.startswith("carrier-"):
                        bid = name[len("carrier-"):]
                        if bid in status and status[bid] == "absent":
                            status[bid] = "stopped"
                except json.JSONDecodeError:
                    pass

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return status


# ── Discord alert ─────────────────────────────────────────────────────────────

def _post_discord_alert(down_bots: list[str], token: str) -> None:
    """Post a degraded fleet alert to Discord."""
    down_list = "\n".join(f"• `{b}`" for b in down_bots)
    embed = {
        "title": f"⚠️ Carrier Fleet Degraded — {len(down_bots)} bot(s) down",
        "color": 0xFF4444,
        "description": f"The following carrier bots are NOT running:\n{down_list}",
        "footer": {"text": f"carrier_vm_health @ {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
    except Exception as exc:
        print(f"[vm_health] Discord alert failed: {exc}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    container_status = _check_containers()
    down_bots = [bid for bid, s in container_status.items() if s != "running"]

    if not down_bots:
        print("FLEET_HEALTHY")
        return

    summary = f"FLEET_DEGRADED:{len(down_bots)}_down"
    print(summary)

    # Post Discord alert
    token = _get_token()
    if token:
        _post_discord_alert(down_bots, token)
    else:
        print(f"[vm_health] No token — skipping Discord alert", file=sys.stderr)


if __name__ == "__main__":
    main()

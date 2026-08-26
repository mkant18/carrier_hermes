#!/usr/bin/env python3
"""
gateway_health.py — Health check CLI for Hermes chief_of_staff gateway
=======================================================================
Reports gateway PID, uptime, platform connection states, watchdog status,
and NSSM service status.

EXIT CODES:
  0 — all platforms connected, gateway running, watchdog alive
  1 — gateway running but one or more platforms disconnected
  2 — gateway not running at all

USAGE:
  python gateway_health.py           # human-readable report
  python gateway_health.py --json    # JSON output for scripting
  python gateway_health.py --quiet   # exit code only (no output)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
LOCALAPPDATA  = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
HERMES_HOME   = Path(LOCALAPPDATA) / "hermes"
PROFILE_DIR   = HERMES_HOME / "profiles" / "chief_of_staff"
GW_STATE_FILE = PROFILE_DIR / "gateway_state.json"

CARRIER_ROOT  = Path("C:/Users/micha/carrier_hermes")
LOG_DIR       = HERMES_HOME / "carrier" / "logs"

WATCHDOG_STATE_FILE = PROFILE_DIR / "gateway_watchdog_state.json"
WATCHDOG_LOG        = LOG_DIR / "gateway_watchdog.log"

NSSM_EXE = "C:/Users/micha/AppData/Local/Microsoft/WinGet/Links/nssm.exe"
SERVICE_NAME = "HermesGateway"

try:
    import psutil as _psutil  # type: ignore[import]
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if _HAS_PSUTIL and _psutil is not None:
        return _psutil.pid_exists(int(pid))
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def process_uptime(pid: int) -> str | None:
    """Return human-readable uptime for a PID, or None if unknown."""
    if not _HAS_PSUTIL or _psutil is None:
        return None
    try:
        proc = _psutil.Process(int(pid))
        create_time = proc.create_time()
        elapsed = datetime.now().timestamp() - create_time
        h, rem = divmod(int(elapsed), 3600)
        m, s   = divmod(rem, 60)
        return f"{h}h {m}m {s}s"
    except Exception:
        return None


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def watchdog_last_heartbeat() -> str | None:
    """Return ISO timestamp of last watchdog heartbeat from its state file."""
    state = read_json_file(WATCHDOG_STATE_FILE)
    return state.get("last_heartbeat")


def watchdog_pid() -> int | None:
    """Return watchdog PID from its state file, or None."""
    state = read_json_file(WATCHDOG_STATE_FILE)
    pid = state.get("pid")
    return int(pid) if pid else None


def nssm_service_status() -> str:
    """Query NSSM/SCM for service status. Returns status string or 'NOT_INSTALLED'."""
    if not Path(NSSM_EXE).exists():
        return "NSSM_NOT_FOUND"
    try:
        result = subprocess.run(
            [NSSM_EXE, "status", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        stdout = result.stdout.strip()
        if stdout:
            return stdout
        return f"NSSM_ERROR(exit={result.returncode})"
    except FileNotFoundError:
        # Fall back to sc.exe
        try:
            result = subprocess.run(
                ["sc", "query", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "RUNNING" in result.stdout:
                return "SERVICE_RUNNING"
            elif "STOPPED" in result.stdout:
                return "SERVICE_STOPPED"
            elif result.returncode != 0:
                return "NOT_INSTALLED"
            return result.stdout.strip()[:80]
        except Exception as e:
            return f"SC_ERROR({e})"
    except Exception as e:
        return f"ERROR({e})"


# ─────────────────────────────────────────────────────────────────────────────
# Main health report
# ─────────────────────────────────────────────────────────────────────────────
def collect_health() -> dict:
    """Collect all health data, return as dict."""
    report: dict = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "gateway":      {},
        "watchdog":     {},
        "nssm_service": {},
        "exit_code":    0,
    }

    # ── Gateway ───────────────────────────────────────────────────────────
    gw_state = read_json_file(GW_STATE_FILE)
    gw  = report["gateway"]

    gw["state_file_exists"] = GW_STATE_FILE.exists()

    if not gw_state:
        gw["status"] = "DOWN"
        gw["pid"]    = None
        report["exit_code"] = 2
    else:
        gw_pid = gw_state.get("pid")
        gw["pid"] = gw_pid
        gw["alive"] = pid_alive(gw_pid) if gw_pid else False

        if not gw["alive"]:
            gw["status"] = "DOWN"
            report["exit_code"] = 2
        else:
            gw["uptime"] = process_uptime(gw_pid) if gw_pid is not None else None
            gw["gateway_state"] = gw_state.get("gateway_state", "unknown")
            gw["code_version"]  = gw_state.get("code_version", "unknown")
            gw["updated_at"]    = gw_state.get("updated_at")

            platforms = gw_state.get("platforms", {})
            gw["platforms"] = {}
            all_connected = True
            for name, info in platforms.items():
                state_val = info.get("state", "unknown")
                gw["platforms"][name] = {
                    "state":      state_val,
                    "updated_at": info.get("updated_at"),
                    "error":      info.get("error_message"),
                }
                if state_val != "connected":
                    all_connected = False

            if all_connected:
                gw["status"] = "HEALTHY"
            else:
                gw["status"] = "DEGRADED"
                if report["exit_code"] == 0:
                    report["exit_code"] = 1

    # ── Watchdog ──────────────────────────────────────────────────────────
    wd = report["watchdog"]
    wd_pid = watchdog_pid()
    wd_hb  = watchdog_last_heartbeat()

    wd["pid"]   = wd_pid
    wd["alive"] = pid_alive(wd_pid) if wd_pid else False
    wd["last_heartbeat"] = wd_hb

    if wd_hb:
        try:
            hb_dt = datetime.fromisoformat(wd_hb)
            age_s = (datetime.now(timezone.utc) - hb_dt).total_seconds()
            wd["heartbeat_age_s"] = int(age_s)
            wd["heartbeat_stale"] = age_s > 600  # stale if >10 min
        except Exception:
            wd["heartbeat_age_s"] = None
            wd["heartbeat_stale"] = True
    else:
        wd["heartbeat_age_s"] = None
        wd["heartbeat_stale"] = True

    # ── NSSM service ──────────────────────────────────────────────────────
    nssm = report["nssm_service"]
    nssm["name"]   = SERVICE_NAME
    nssm["status"] = nssm_service_status()

    return report


def format_human(report: dict) -> str:
    """Return a human-readable status report."""
    lines = []
    ts = report["collected_at"]
    lines.append(f"═══ Hermes Gateway Health Report ═══  {ts}")
    lines.append("")

    gw = report["gateway"]
    status_icon = {"HEALTHY": "✅", "DEGRADED": "⚠️ ", "DOWN": "❌"}.get(gw.get("status", "DOWN"), "❓")
    lines.append(f"GATEWAY  {status_icon} {gw.get('status', 'UNKNOWN')}")
    lines.append(f"  PID        : {gw.get('pid', 'N/A')}")
    lines.append(f"  Alive      : {gw.get('alive', False)}")
    if gw.get("uptime"):
        lines.append(f"  Uptime     : {gw['uptime']}")
    if gw.get("gateway_state"):
        lines.append(f"  State      : {gw['gateway_state']}")
    if gw.get("code_version"):
        lines.append(f"  Version    : {gw['code_version']}")
    if gw.get("updated_at"):
        lines.append(f"  Updated at : {gw['updated_at']}")

    if gw.get("platforms"):
        lines.append("  Platforms  :")
        for name, info in gw["platforms"].items():
            icon = "✅" if info["state"] == "connected" else "❌"
            lines.append(f"    {icon} {name:12s}: {info['state']}")
            if info.get("error"):
                lines.append(f"              error: {info['error']}")
            if info.get("updated_at"):
                lines.append(f"              last update: {info['updated_at']}")

    lines.append("")

    wd = report["watchdog"]
    wd_icon = "✅" if wd.get("alive") else "⚠️ "
    lines.append(f"WATCHDOG {wd_icon} {'alive' if wd.get('alive') else 'NOT RUNNING'}")
    lines.append(f"  PID            : {wd.get('pid', 'N/A')}")
    if wd.get("last_heartbeat"):
        age = wd.get("heartbeat_age_s")
        stale = wd.get("heartbeat_stale", True)
        stale_str = " ⚠️ STALE" if stale else ""
        lines.append(f"  Last heartbeat : {wd['last_heartbeat']}  ({age}s ago){stale_str}")

    lines.append("")

    nssm = report["nssm_service"]
    nssm_status = nssm.get("status", "UNKNOWN")
    nssm_icon = "✅" if "RUNNING" in nssm_status or nssm_status == "SERVICE_RUNNING" else "⚠️ "
    lines.append(f"NSSM SVC {nssm_icon} {nssm['name']}: {nssm_status}")

    lines.append("")
    exit_str = {0: "✅ HEALTHY (exit 0)", 1: "⚠️  DEGRADED (exit 1)", 2: "❌ DOWN (exit 2)"}
    lines.append(f"OVERALL  {exit_str.get(report['exit_code'], str(report['exit_code']))}")
    lines.append("═══════════════════════════════════════")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes gateway health check")
    parser.add_argument("--json",   action="store_true", help="Output JSON")
    parser.add_argument("--quiet",  action="store_true", help="No output, exit code only")
    args = parser.parse_args()

    report = collect_health()

    if not args.quiet:
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(format_human(report))

    sys.exit(report["exit_code"])


if __name__ == "__main__":
    main()

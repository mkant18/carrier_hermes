#!/usr/bin/env python3
"""ollama_rescue.py — detect and recover a crashed/stalled Ollama on this host.

Ollama serves the fleet's local models from inside WSL2 (systemd service). When it
crashes, hangs, wedges on a stuck model, or becomes unreachable, every local-primary
bot fails over to OAuth (safe but not the intent) or, worse, a request stalls. This
script is the RESCUE: it diagnoses the failure CLASS and applies escalating recovery,
verifying health at each step. Zero-LLM, safe to run from cron or by hand.

FAILURE TAXONOMY (observed on mks-pc):
  A. Worker init crash (model context < Hermes 64K floor) — a MODEL/config issue,
     not an Ollama fault. Rescue only WARNS (can't fix a bot config safely here).
  B. Unreachable from Windows via 127.0.0.1 — WSL NAT quirk (127.0.0.1 doesn't
     forward to WSL; localhost does). Rescue verifies the working address.
  C. Generated-code infinite loop — contained by the caller's execution timeout;
     NOT an Ollama fault. Out of scope for rescue (belongs to code-exec sandbox).
  D. Ollama server hang / wedged inference slot / crash — RESTART the service.
  E. WSL IP changed -> stale Tailscale portproxy — rebuild the portproxy (needs
     admin; rescue detects + reports the exact command if it can't elevate).

ESCALATION LADDER (stops as soon as health returns):
  0. Probe health (reachable + responsive generate within timeout).
  1. If unreachable but service active -> unload any stuck model (POST keep_alive:0),
     re-probe.
  2. If still bad -> restart the WSL ollama service, wait for ready, re-probe.
  3. Re-probe over the Tailscale IP; if that alone is broken, rebuild portproxy.
  4. If still unrecoverable -> emit an ALERT line (non-empty stdout) for a watchdog
     cron to broadcast, and exit non-zero.

Health is defined as: GET /api/tags 200 AND a tiny /api/generate completes within
GEN_TIMEOUT. Reachability is checked over `localhost` (the address bots use).

Usage:
    python ollama_rescue.py            # diagnose + recover if needed, verbose
    python ollama_rescue.py --check    # health probe only, no recovery (exit 0 ok)
    python ollama_rescue.py --json      # machine-readable result

Exit codes: 0 healthy (or recovered), 2 unrecoverable.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request

HOST = "localhost"                       # the address bots use (NOT 127.0.0.1 on this WSL host)
TAGS_URL = f"http://{HOST}:11434/api/tags"
GEN_URL = f"http://{HOST}:11434/api/generate"
PROBE_MODEL = "llama3.1:8b-instruct-q4_K_M"
TAILSCALE_IP = "100.87.88.30"
GEN_TIMEOUT = 30
READY_TIMEOUT = 90


def _http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e).encode()


def _http_post(url, payload, timeout):
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e).encode()


def _wsl(cmd, timeout=60):
    try:
        r = subprocess.run(["wsl", "bash", "-c", cmd], capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def probe_health(log):
    """Return (ok, detail). ok=True iff reachable AND a tiny generate completes."""
    status, _ = _http_get(TAGS_URL, timeout=5)
    if status != 200:
        log(f"  probe: /api/tags unreachable ({status})")
        return False, "tags_unreachable"
    # responsiveness: a 1-token generate
    t0 = time.time()
    status, body = _http_post(GEN_URL, {
        "model": PROBE_MODEL, "prompt": "hi", "stream": False,
        "options": {"num_predict": 1}, "keep_alive": "30s",
    }, timeout=GEN_TIMEOUT)
    dt = round(time.time() - t0, 1)
    if status == 200:
        log(f"  probe: healthy (generate {dt}s)")
        return True, f"healthy_{dt}s"
    log(f"  probe: generate failed after {dt}s ({body[:80]!r})")
    return False, "generate_failed"


def service_active():
    rc, out = _wsl("systemctl is-active ollama")
    return "active" in out


def unload_models(log):
    log("  recover[1]: unloading any resident model (keep_alive=0)")
    for m in (PROBE_MODEL, "qwen2.5-coder:7b-instruct-q4_K_M", "qwen2.5:7b-instruct-q4_K_M"):
        _http_post(GEN_URL, {"model": m, "keep_alive": 0}, timeout=10)
    _wsl("ollama stop " + PROBE_MODEL, timeout=15)
    time.sleep(2)


def restart_service(log):
    log("  recover[2]: restarting WSL ollama service")
    rc, out = _wsl("sudo systemctl restart ollama", timeout=60)
    if rc != 0:
        log(f"    restart rc={rc}: {out.strip()[:120]}")
    # wait for ready
    deadline = time.time() + READY_TIMEOUT
    while time.time() < deadline:
        status, _ = _http_get(TAGS_URL, timeout=5)
        if status == 200:
            log("    service back up (/api/tags 200)")
            return True
        time.sleep(3)
    log("    service did NOT come back within timeout")
    return False


def check_tailscale(log):
    """Class E: is the Tailscale IP reachable? If not, try to rebuild portproxy."""
    status, _ = _http_get(f"http://{TAILSCALE_IP}:11434/api/tags", timeout=5)
    if status == 200:
        log("  tailscale: reachable")
        return True
    log("  tailscale: NOT reachable — portproxy likely stale (WSL IP changed)")
    rc, wsl_ip = _wsl("hostname -I")
    wsl_ip = wsl_ip.strip().split()[0] if wsl_ip.strip() else ""
    cmd = (f"netsh interface portproxy delete v4tov4 listenport=11434 "
           f"listenaddress={TAILSCALE_IP} & "
           f"netsh interface portproxy add v4tov4 listenport=11434 "
           f"listenaddress={TAILSCALE_IP} connectport=11434 connectaddress={wsl_ip}")
    r = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True)
    if "elevation" in (r.stdout + r.stderr).lower() or "administrator" in (r.stdout + r.stderr).lower():
        log(f"    NEEDS ADMIN. Run in elevated cmd:\n      {cmd}")
        return False
    status, _ = _http_get(f"http://{TAILSCALE_IP}:11434/api/tags", timeout=5)
    ok = status == 200
    log(f"    portproxy rebuilt to {wsl_ip} -> tailscale reachable: {ok}")
    return ok


def rescue(log, check_only=False):
    result = {"initial": None, "steps": [], "final": None, "recovered": False,
              "tailscale_ok": None}

    ok, detail = probe_health(log)
    result["initial"] = detail
    if ok:
        result["final"] = "healthy"
        result["recovered"] = True
        result["tailscale_ok"] = check_tailscale(log) if not check_only else None
        return result
    if check_only:
        result["final"] = "unhealthy"
        return result

    if not service_active():
        log("  service inactive — going straight to restart")
        restart_service(log)
        result["steps"].append("restart(inactive)")
    else:
        # Step 1: unload stuck model
        unload_models(log)
        result["steps"].append("unload")
        ok, _ = probe_health(log)
        if not ok:
            # Step 2: restart
            restart_service(log)
            result["steps"].append("restart")

    ok, detail = probe_health(log)
    result["final"] = detail
    result["recovered"] = ok
    if ok:
        result["tailscale_ok"] = check_tailscale(log)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="health probe only, no recovery")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watchdog", action="store_true",
                    help="silent unless recovery FAILS (for no_agent cron)")
    args = ap.parse_args()

    lines = []
    quiet = args.json or args.watchdog
    def log(m):
        lines.append(m)
        if not quiet:
            print(m)

    if not quiet:
        print(f"=== Ollama Rescue {'(check)' if args.check else ''} ===")
    res = rescue(log, check_only=args.check)

    if args.json:
        print(json.dumps(res))
    elif not args.watchdog:
        verdict = ("✅ healthy" if res["recovered"]
                   else ("🛑 UNHEALTHY" if args.check else "❌ UNRECOVERABLE"))
        print(f"--- {verdict} (steps: {res['steps'] or 'none'}) ---")

    # Non-zero + alert line on unrecoverable, so a no_agent watchdog broadcasts it.
    if not res["recovered"] and not args.check:
        # In watchdog mode this is the ONLY output — delivered verbatim as the alert.
        print("🚨 Ollama Rescue FAILED — local models are DOWN on mks-pc. "
              f"Steps tried: {res['steps'] or 'none'}. Manual intervention needed "
              "(check WSL: `wsl systemctl status ollama`).")
        return 2
    # Watchdog that recovered from a real outage: emit ONE line so the user knows
    # it self-healed (recovery took steps beyond a clean probe).
    if args.watchdog and res["recovered"] and res.get("steps"):
        print(f"🔧 Ollama had stalled and was auto-recovered on mks-pc "
              f"(steps: {', '.join(res['steps'])}). Local models are back online.")
    return 0 if res["recovered"] else 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""error_bug_scanner.py -- Zero-LLM fleet error and bug scanner.

Scans the carrier_hermes fleet for:
  1. Recent Python exceptions/tracebacks in agent logs (last 24h)
  2. Config files with phantom/invalid model names or billing violations
  3. Kanban DB for stuck/crashed/failed tasks
  4. Known bad patterns in script files
  5. Missing model pulls (configured models not in Ollama)

Zero tokens, zero OAuth. Safe in no_agent cron contexts.

Usage:
    python error_bug_scanner.py             # human-readable
    python error_bug_scanner.py --json      # JSON only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
PROFILES_DIR = HERMES_HOME / "profiles"
CARRIER_DIR = HERMES_HOME / "carrier"
REPO = Path(r"C:\Users\micha\carrier_hermes")
KANBAN_DB = HERMES_HOME / "kanban" / "boards" / "carrier" / "kanban.db"
LOG_SCAN_HOURS = 24

# Phantom model names -- must never appear in configs
PHANTOM_MODELS = [
    "claude-sonnet-5", "claude-sonnet-5-20251001", "claude-sonnet-5-20261001",
    "claude-opus-5", "claude-opus-5-20251001",
    "qwen2.5:7b-instruct-q4_K_M",   # 32K ctx -- below 64K floor, crash-loops
    "mistral-nemo:latest",           # fails as kanban worker on full ctx
    "mistral-nemo",                  # same
    "qwen2.5-coder:7b-instruct-q4_K_M",  # FIM model -- no tool calls
]

# OpenRouter frontier models -- billing violations if not in allowlist
OR_FRONTIER_PATTERNS = [
    r"openrouter.*anthropic/claude",
    r"openrouter.*openai/gpt-[45]",
    r"openrouter.*xai/grok",
    r"openrouter.*google/gemini-pro",
    r"openrouter.*meta-llama.*405b",
]

SEVERITY_HIGH   = "HIGH"
SEVERITY_MEDIUM = "MED"
SEVERITY_LOW    = "LOW"

# Known-good local models
GOOD_LOCAL_MODELS = {
    "llama3.1:8b-instruct-q4_K_M",
    "gemma4:26b",
    "qwen2.5-coder-chat:latest",
}


def _q(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Scanner 1 -- agent logs
# ---------------------------------------------------------------------------

def scan_agent_logs() -> list[dict]:
    """Scan agent logs for recent exceptions and errors."""
    issues: list[dict] = []
    cutoff = time.time() - LOG_SCAN_HOURS * 3600

    error_patterns = [
        (r"Traceback \(most recent call last\)",           "traceback",        SEVERITY_HIGH),
        (r"Failed to initialize agent",                    "init_failure",     SEVERITY_HIGH),
        (r"pid not alive|not alive after",                 "worker_crash",     SEVERITY_HIGH),
        (r"context window.*below the minimum",             "context_floor",    SEVERITY_HIGH),
        (r"phantom|404.*model|model not found",            "phantom_model_log",SEVERITY_HIGH),
        (r"billing violation|api_key.*forbidden",          "billing_violation",SEVERITY_HIGH),
        (r"consecutive.failures|crash.loop",               "crash_loop",       SEVERITY_HIGH),
        (r"\bERROR\b|\bCRITICAL\b|\bFATAL\b",             "error_line",       SEVERITY_MEDIUM),
        (r"kanban stop-loop nudge",                        "kanban_nudge",     SEVERITY_MEDIUM),
        (r"DISPATCH_LOCK|SPEND_HALT",                      "halt_flag",        SEVERITY_MEDIUM),
    ]

    log_dirs: list[Path] = []
    if PROFILES_DIR.exists():
        log_dirs += list(PROFILES_DIR.glob("*/logs"))
    if (HERMES_HOME / "logs").exists():
        log_dirs.append(HERMES_HOME / "logs")
    if (HERMES_HOME / "carrier" / "logs").exists():
        log_dirs.append(HERMES_HOME / "carrier" / "logs")

    for log_dir in log_dirs:
        bot_name = log_dir.parent.name if log_dir.parent != HERMES_HOME else "system"
        for log_file in log_dir.glob("*.log"):
            try:
                if not log_file.exists():
                    continue
                if log_file.stat().st_mtime < cutoff:
                    continue
                text = log_file.read_text(encoding="utf-8", errors="replace")
                for pattern, kind, severity in error_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    if not matches:
                        continue
                    # Grab context around first match
                    lines = text.splitlines()
                    ctx = []
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            ctx.append("\n".join(lines[max(0,i-1):min(len(lines),i+4)]))
                            if len(ctx) >= 2:
                                break
                    issues.append({
                        "source": "agent_log",
                        "bot": bot_name,
                        "log_file": log_file.name,
                        "kind": kind,
                        "severity": severity,
                        "count": len(matches),
                        "context": ctx[:1],
                        "detail": f"{len(matches)}x '{kind}' in {bot_name}/{log_file.name}",
                    })
            except Exception:
                pass
    return issues


# ---------------------------------------------------------------------------
# Scanner 2 -- config files
# ---------------------------------------------------------------------------

def scan_configs() -> list[dict]:
    """Scan config.yaml files for phantom models and billing violations."""
    issues: list[dict] = []
    try:
        import yaml
    except ImportError:
        return [{"source": "config_scan", "kind": "missing_dep", "severity": SEVERITY_LOW,
                 "detail": "PyYAML missing -- run with Hermes venv Python"}]

    cfg_paths: list[Path] = [HERMES_HOME / "config.yaml"]
    if PROFILES_DIR.exists():
        cfg_paths += sorted(PROFILES_DIR.glob("*/config.yaml"))

    for cfg_path in cfg_paths:
        if not cfg_path.exists():
            continue
        bot = cfg_path.parent.name if cfg_path.parent != HERMES_HOME else "global"
        try:
            text = cfg_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for phantom in PHANTOM_MODELS:
            if phantom in text:
                issues.append({
                    "source": "config_scan", "bot": bot,
                    "config": str(cfg_path), "kind": "phantom_model",
                    "severity": SEVERITY_HIGH,
                    "model": phantom,
                    "detail": f"Phantom model '{phantom}' in {bot}/config.yaml",
                    "auto_fixable": True,
                })

        for pattern in OR_FRONTIER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                m = re.search(pattern, text, re.IGNORECASE)
                issues.append({
                    "source": "config_scan", "bot": bot,
                    "config": str(cfg_path), "kind": "or_frontier_violation",
                    "severity": SEVERITY_HIGH,
                    "detail": f"OR frontier pattern in {bot}/config.yaml: {m.group()[:60] if m else ''}",
                    "auto_fixable": False,
                })

        # API keys in config -- exclude known-safe values (Ollama placeholder, none, empty)
        api_key_hits = re.findall(r'\bapi_key\s*:\s*(\S+)', text, re.IGNORECASE)
        safe_api_values = {"ollama", "none", "null", '""', "''", ""}
        real_keys = [v.strip("\"'") for v in api_key_hits
                     if v.strip("\"'").lower() not in safe_api_values
                     and len(v.strip("\"'")) > 8]
        if real_keys:
            issues.append({
                "source": "config_scan", "bot": bot,
                "config": str(cfg_path), "kind": "api_key_in_config",
                "severity": SEVERITY_HIGH,
                "detail": f"Possible real api_key in {bot}/config.yaml: {real_keys[0][:20]}...",
                "auto_fixable": False,
            })

        # Disabled kanban toolset (breaks kanban workers -- known bug)
        if bot in ("code_auditor", "patch_writer", "pr_reviewer", "firstmate",
                   "repair_planner", "git_yeoman"):
            try:
                cfg = yaml.safe_load(text) or {}
                disabled = (cfg.get("toolsets") or {}).get("disabled") or []
                if "kanban" in disabled:
                    issues.append({
                        "source": "config_scan", "bot": bot,
                        "config": str(cfg_path), "kind": "kanban_disabled_worker",
                        "severity": SEVERITY_HIGH,
                        "detail": f"{bot} has 'kanban' in toolsets.disabled -- breaks kanban_complete",
                        "auto_fixable": True,
                    })
            except Exception:
                pass

    return issues


# ---------------------------------------------------------------------------
# Scanner 3 -- Kanban DB
# ---------------------------------------------------------------------------

def scan_kanban() -> list[dict]:
    """Scan Kanban DB for stuck, crashed, and failed tasks."""
    issues: list[dict] = []
    if not KANBAN_DB.exists():
        return issues
    try:
        conn = sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row

        # Tasks with consecutive failures
        for r in _q(conn, """
            SELECT id, title, assignee, status, consecutive_failures,
                   max_retries, last_failure_error
            FROM tasks WHERE consecutive_failures > 0
            ORDER BY consecutive_failures DESC LIMIT 20
        """):
            sev = SEVERITY_HIGH if r["consecutive_failures"] >= r["max_retries"] else SEVERITY_MEDIUM
            issues.append({
                "source": "kanban", "kind": "task_failures", "severity": sev,
                "task_id": r["id"], "assignee": r["assignee"], "status": r["status"],
                "failures": r["consecutive_failures"], "max_retries": r["max_retries"],
                "error": (r["last_failure_error"] or "")[:200],
                "detail": (f"Task {r['id']} [{r['title'][:40]}] "
                           f"{r['consecutive_failures']}/{r['max_retries']} failures "
                           f"assignee={r['assignee']}"),
                "auto_fixable": r["status"] in ("blocked", "failed"),
            })

        # Stuck in 'running' > 90 min (orphaned workers)
        stale_cut = int(time.time()) - 5400
        for r in _q(conn, """
            SELECT id, title, assignee, started_at, worker_pid
            FROM tasks WHERE status='running' AND started_at < ?
            ORDER BY started_at ASC
        """, (stale_cut,)):
            age_min = int((time.time() - (r["started_at"] or 0)) / 60)
            issues.append({
                "source": "kanban", "kind": "stuck_running", "severity": SEVERITY_MEDIUM,
                "task_id": r["id"], "assignee": r["assignee"],
                "age_min": age_min, "pid": r["worker_pid"],
                "detail": f"Task {r['id']} stuck 'running' {age_min}min (pid={r['worker_pid']})",
                "auto_fixable": True,
            })

        # Tasks with no assignee profile (orphaned)
        known_profiles = {d.name for d in PROFILES_DIR.iterdir() if d.is_dir()}
        for r in _q(conn, "SELECT id, assignee, title FROM tasks WHERE status='ready'"):
            if r["assignee"] and r["assignee"] not in known_profiles:
                issues.append({
                    "source": "kanban", "kind": "unknown_assignee", "severity": SEVERITY_MEDIUM,
                    "task_id": r["id"], "assignee": r["assignee"],
                    "detail": f"Task {r['id']} assigned to unknown profile '{r['assignee']}'",
                    "auto_fixable": False,
                })

        conn.close()
    except Exception as e:
        issues.append({"source": "kanban", "kind": "scan_error", "severity": SEVERITY_LOW,
                       "detail": f"Kanban scan error: {e}"})
    return issues


# ---------------------------------------------------------------------------
# Scanner 4 -- scripts
# ---------------------------------------------------------------------------

def scan_scripts() -> list[dict]:
    """Scan script files for known bad patterns."""
    issues: list[dict] = []
    scripts_dir = REPO / "scripts"
    if not scripts_dir.exists():
        return issues

    bad_patterns = [
        (r"claude-sonnet-5\b",                "phantom_model_in_script",      SEVERITY_MEDIUM),
        (r"qwen2\.5:7b-instruct-q4_K_M\b",   "crash_model_in_script",        SEVERITY_MEDIUM),
        (r"sc start HermesOllama",            "ollama_service_name_wrong",    SEVERITY_LOW),
        (r"/dev/stdin",                       "dev_stdin_on_windows",         SEVERITY_MEDIUM),
        (r"localhost:11434.*\bpath=",         "ollama_path_endpoint",         SEVERITY_LOW),
    ]

    for py_file in sorted(scripts_dir.glob("*.py")):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            for pattern, kind, severity in bad_patterns:
                if re.search(pattern, text):
                    issues.append({
                        "source": "script_scan", "kind": kind, "severity": severity,
                        "file": py_file.name,
                        "detail": f"'{kind}' in {py_file.name}",
                        "auto_fixable": False,
                    })
        except Exception:
            pass
    return issues


# ---------------------------------------------------------------------------
# Scanner 5 -- Ollama model presence
# ---------------------------------------------------------------------------

def scan_ollama_models() -> list[dict]:
    """Check that configured local models are actually pulled in Ollama."""
    issues: list[dict] = []
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags",
                                     headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        pulled = {m["name"] for m in resp.get("models", [])}
    except Exception as e:
        issues.append({"source": "ollama", "kind": "ollama_unreachable", "severity": SEVERITY_HIGH,
                       "detail": f"Cannot reach Ollama: {e}"})
        return issues

    try:
        import yaml
    except ImportError:
        return issues

    for cfg_path in sorted(PROFILES_DIR.glob("*/config.yaml")):
        bot = cfg_path.parent.name
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            for prov in cfg.get("providers", []):
                if prov.get("name") == "custom":
                    model = prov.get("model", "")
                    if model and model not in pulled:
                        issues.append({
                            "source": "ollama", "kind": "model_not_pulled", "severity": SEVERITY_HIGH,
                            "bot": bot, "model": model,
                            "detail": f"{bot} configured with local model '{model}' NOT in Ollama -- will crash-loop",
                            "auto_fixable": False,
                        })
        except Exception:
            pass
    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_scan() -> dict:
    """Run all scanners. Returns consolidated JSON report."""
    t0 = time.time()
    all_issues: list[dict] = []
    all_issues += scan_agent_logs()
    all_issues += scan_configs()
    all_issues += scan_kanban()
    all_issues += scan_scripts()
    all_issues += scan_ollama_models()

    sev_rank = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    all_issues.sort(key=lambda i: (sev_rank.get(i.get("severity", "LOW"), 2), i.get("kind", "")))

    high   = [i for i in all_issues if i.get("severity") == SEVERITY_HIGH]
    medium = [i for i in all_issues if i.get("severity") == SEVERITY_MEDIUM]
    low    = [i for i in all_issues if i.get("severity") == SEVERITY_LOW]

    return {
        "scanned_at":      int(t0),
        "scan_duration_s": round(time.time() - t0, 2),
        "total_issues":    len(all_issues),
        "high":            len(high),
        "medium":          len(medium),
        "low":             len(low),
        "issues":          all_issues,
        "high_issues":     high,
        "medium_issues":   medium,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Zero-LLM fleet error scanner")
    ap.add_argument("--json", action="store_true", help="JSON output only")
    args = ap.parse_args()
    report = run_scan()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Fleet Error Scan === [{time.strftime('%H:%M:%S')}]")
        print(f"Total: {report['total_issues']} issues  "
              f"HIGH={report['high']}  MED={report['medium']}  LOW={report['low']}  "
              f"({report['scan_duration_s']}s)")
        for issue in report["issues"]:
            print(f"  [{issue['severity']:4}] [{issue['kind']:<32}] {issue.get('detail','')[:80]}")

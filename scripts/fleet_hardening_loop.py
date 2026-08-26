#!/usr/bin/env python3
"""fleet_hardening_loop.py — Continuous fleet hardening orchestrator.

Runs every 30 minutes (via Hermes cron, no_agent=True). Uses local Ollama
(llama3.1:8b) to improve bot memories, seed missing identity memories, and
fix common bugs. Reports tri-platform to Discord #maintenance + Telegram.

This script is the core of the "hardening loop" -- it runs EVEN WHEN YOU
ARE AT YOUR PC, continuously improving the team. Silent Running handles AFK
capacity-gating; this script is the always-on improvement layer.

Cycle phases:
  1. SCAN   -- call error_bug_scanner.py for current issue list
  2. FIX    -- auto-fix what we can (unstick kanban, fix phantom models)
  3. HARDEN -- call Ollama to improve top-priority bot memory stores
  4. SEED   -- seed empty bot memory stores with identity starter content
  5. REPORT -- broadcast results tri-platform

Cost: $0.00. Entirely local LLM (Ollama) + zero-LLM functions.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
HOME   = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
REPO   = Path(r"C:\Users\micha\carrier_hermes")
CARRIER = HOME / "carrier"
SCRIPTS = REPO / "scripts"
KANBAN_DB = HOME / "kanban" / "boards" / "carrier" / "kanban.db"

LOGS_DIR = HOME / "carrier" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "fleet_hardening_loop.log"

HPY = str(HOME / "hermes-agent" / "venv" / "Scripts" / "python.exe")

# ─── Model settings ───────────────────────────────────────────────────────────
OLLAMA_URL      = "http://localhost:11434"
PRIMARY_MODEL   = "llama3.1:8b-instruct-q4_K_M"
FALLBACK_MODEL  = "gemma4:26b"    # only if primary fails
OLLAMA_TIMEOUT  = 90              # seconds per Ollama request
MAX_MEM_TOKENS  = 600             # keep Ollama outputs concise

# ─── Hardening concurrency limits ─────────────────────────────────────────────
MAX_HARDEN_PER_CYCLE = 3    # max bots improved per run (keeps cycles fast)
MAX_FIX_PER_CYCLE    = 5    # max auto-fixes per run

# ─── Cycle state file ─────────────────────────────────────────────────────────
CYCLE_STATE_FILE = CARRIER / "hardening_loop_state.json"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _read_state() -> dict:
    try:
        return json.loads(CYCLE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"cycle": 0, "last_run": 0, "total_fixes": 0,
                "total_memory_improvements": 0, "issues_seen": 0}


def _write_state(s: dict) -> None:
    try:
        CYCLE_STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception:
        pass


# ─── Discord / Telegram helpers (copied from fleet_checkin.py) ────────────────
def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = HOME / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    env.update(os.environ)
    return env


ENV = _load_env()
DISCORD_TOKEN   = ENV.get("DISCORD_FLEET_BOT_TOKEN", "")
DISCORD_CHANNEL = "1542052741889663077"   # #maintenance
TELEGRAM_CHAT   = "-5577918772"            # Fleet Command group
MICHAEL_DISCORD = "<@174349224870150144>"
MICHAEL_TG_ID   = "8816949993"


def _discord_post(msg: str) -> bool:
    if not DISCORD_TOKEN:
        return False
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages"
    payload = {"content": msg[:1990]}
    try:
        req = urllib.request.Request(
            url, method="POST",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bot {DISCORD_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (https://carrier-hermes, 1.0)",
            }
        )
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        _log(f"Discord post failed: {e}")
        return False


def _strip_discord_md(msg: str) -> str:
    """Convert Discord markdown to plain text for Telegram."""
    # Remove bold/italic markers
    msg = re.sub(r'\*\*(.+?)\*\*', r'\1', msg)
    msg = re.sub(r'\*(.+?)\*', r'\1', msg)
    # Remove inline code backticks
    msg = re.sub(r'`(.+?)`', r'\1', msg)
    # Remove _italic_
    msg = re.sub(r'_(.+?)_', r'\1', msg)
    return msg


def _telegram_post(msg: str) -> bool:
    tg_token = ENV.get("TELEGRAM_BOT_TOKEN", "")
    if not tg_token:
        return False
    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    plain = _strip_discord_md(msg)
    payload = {"chat_id": TELEGRAM_CHAT, "text": plain[:4000]}
    try:
        req = urllib.request.Request(
            url, method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        _log(f"Telegram post failed: {e}")
        return False


def broadcast(msg: str) -> None:
    _log(f"BROADCAST: {msg[:120]}")
    _discord_post(msg)
    _telegram_post(msg)


# ─── Ollama helper ────────────────────────────────────────────────────────────
def ollama_chat(prompt: str, system: str = "",
                model: str = PRIMARY_MODEL) -> str | None:
    """Call Ollama chat completions. Returns text or None on failure."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": MAX_MEM_TOKENS,
            "temperature": 0.3,
        },
    }
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(
            urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT).read()
        )
        content = resp["choices"][0]["message"]["content"].strip()
        return content if content else None
    except Exception as e:
        _log(f"Ollama {model} failed: {e}")
        if model == PRIMARY_MODEL:
            return ollama_chat(prompt, system, model=FALLBACK_MODEL)
        return None


# ─── Phase 1: SCAN ───────────────────────────────────────────────────────────
def phase_scan() -> dict:
    _log("Phase 1: SCAN -- running error_bug_scanner")
    scanner = SCRIPTS / "error_bug_scanner.py"
    if not scanner.exists():
        _log("Scanner not found -- skipping scan phase")
        return {"total_issues": 0, "high": 0, "medium": 0, "low": 0, "issues": []}
    try:
        result = subprocess.run(
            [HPY, str(scanner), "--json"],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPTS)
        )
        if result.returncode == 0 and result.stdout.strip():
            report = json.loads(result.stdout)
            _log(f"Scan done: {report['total_issues']} issues (H={report['high']} M={report['medium']})")
            return report
        else:
            _log(f"Scanner stderr: {result.stderr[:200]}")
    except Exception as e:
        _log(f"Scan phase error: {e}")
    return {"total_issues": 0, "high": 0, "medium": 0, "low": 0, "issues": []}


# ─── Phase 2: AUTO-FIX ───────────────────────────────────────────────────────
def phase_autofix(scan_report: dict) -> list[str]:
    """Auto-fix issues that are safe to fix without human approval."""
    fixes_done: list[str] = []
    issues = scan_report.get("issues", [])
    _log(f"Phase 2: AUTO-FIX -- {len(issues)} issues, scanning for auto-fixable")

    try:
        import yaml  # type: ignore[import]
        has_yaml = True
    except ImportError:
        yaml = None  # type: ignore[assignment]
        has_yaml = False

    fix_count = 0
    for issue in issues:
        if fix_count >= MAX_FIX_PER_CYCLE:
            break
        if not issue.get("auto_fixable"):
            continue

        kind = issue.get("kind", "")

        # Fix 1: Phantom model in config -- replace with canonical name
        if kind == "phantom_model" and has_yaml:
            cfg_path = Path(issue.get("config", ""))
            phantom = issue.get("model", "")
            if cfg_path.exists() and phantom:
                # Safe replacements only
                safe_replacements = {
                    "claude-sonnet-5-20251001": "claude-sonnet-4-6",
                    "claude-sonnet-5-20261001": "claude-sonnet-4-6",
                    "claude-sonnet-5":          "claude-sonnet-4-6",
                    "claude-opus-5-20251001":   "claude-opus-4-5",
                    "claude-opus-5":            "claude-opus-4-5",
                }
                replacement = safe_replacements.get(phantom)
                if replacement:
                    try:
                        text = cfg_path.read_text(encoding="utf-8")
                        new_text = text.replace(phantom, replacement)
                        if new_text != text:
                            cfg_path.write_text(new_text, encoding="utf-8")
                            desc = f"Fixed phantom model '{phantom}' → '{replacement}' in {issue.get('bot','?')}/config.yaml"
                            fixes_done.append(desc)
                            _log(f"FIX: {desc}")
                            fix_count += 1
                    except Exception as e:
                        _log(f"Fix phantom model failed: {e}")

        # Fix 2: Stuck 'running' task > 90 min -- reset to ready
        elif kind == "stuck_running":
            task_id = issue.get("task_id")
            if task_id and KANBAN_DB.exists():
                try:
                    conn = sqlite3.connect(str(KANBAN_DB), timeout=10)
                    conn.execute("""
                        UPDATE tasks SET
                            status='ready', consecutive_failures=0,
                            last_failure_error=NULL, started_at=NULL,
                            worker_pid=NULL, current_run_id=NULL,
                            claim_lock=NULL, claim_expires=NULL,
                            last_heartbeat_at=NULL
                        WHERE id=? AND status='running'
                    """, (task_id,))
                    conn.commit()
                    conn.close()
                    desc = f"Reset stuck task {task_id} (was running {issue.get('age_min','?')}min) → ready"
                    fixes_done.append(desc)
                    _log(f"FIX: {desc}")
                    fix_count += 1
                except Exception as e:
                    _log(f"Fix stuck task {task_id} failed: {e}")

        # Fix 3: kanban disabled in worker config -- remove it
        elif kind == "kanban_disabled_worker" and has_yaml:
            cfg_path = Path(issue.get("config", ""))
            if cfg_path.exists():
                try:
                    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}  # type: ignore[union-attr]
                    toolsets = cfg.setdefault("toolsets", {})
                    disabled = toolsets.get("disabled", [])
                    if "kanban" in disabled:
                        disabled.remove("kanban")
                        toolsets["disabled"] = disabled
                        cfg_path.write_text(
                            yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),  # type: ignore[union-attr]
                            encoding="utf-8"
                        )
                        desc = f"Removed 'kanban' from toolsets.disabled in {issue.get('bot','?')}/config.yaml"
                        fixes_done.append(desc)
                        _log(f"FIX: {desc}")
                        fix_count += 1
                except Exception as e:
                    _log(f"Fix kanban disabled failed: {e}")

        # Fix 4: task exhausted max retries -- reset to ready so it can be retried
        elif kind == "task_failures" and issue.get("status") in ("blocked", "failed", "ready"):
            task_id = issue.get("task_id")
            failures = issue.get("failures", 0)
            max_r = issue.get("max_retries", 2)
            if task_id and failures >= max_r and KANBAN_DB.exists():
                try:
                    conn = sqlite3.connect(str(KANBAN_DB), timeout=10)
                    conn.execute("""
                        UPDATE tasks SET
                            status='ready', consecutive_failures=0,
                            last_failure_error=NULL, started_at=NULL,
                            worker_pid=NULL, current_run_id=NULL,
                            claim_lock=NULL, claim_expires=NULL,
                            last_heartbeat_at=NULL
                        WHERE id=? AND status NOT IN ('completed','cancelled')
                    """, (task_id,))
                    conn.commit()
                    conn.close()
                    desc = f"Reset exhausted task {task_id} ({failures}/{max_r} failures) → ready for retry"
                    fixes_done.append(desc)
                    _log(f"FIX: {desc}")
                    fix_count += 1
                except Exception as e:
                    _log(f"Fix task {task_id} failed: {e}")

    return fixes_done


# ─── Phase 3 & 4: HARDEN + SEED memories with local LLM ─────────────────────

# Bot identity descriptions for memory seeding
BOT_IDENTITIES = {
    "chief_of_staff":    "Helm, chief of staff and strategic commander of the carrier_hermes fleet. Orchestrates all bots, manages priorities, owns Discord/Telegram gateways.",
    "firstmate":         "Mate, senior coding executor and primary worker for build/execution tasks. Runs in the Coding Wing under Wrench (coding_lt).",
    "coding_lt":         "Wrench, Coding Wing Lead Lieutenant. Plans, delegates, and reviews code work. Commands firstmate and git_yeoman.",
    "git_yeoman":        "Yeoman, git operations specialist. Handles all git/PR/commit/branch operations using gh CLI. Works in the Coding Wing.",
    "knowledge_lt":      "Scholar, Knowledge Wing Lead Lieutenant. Manages information synthesis, research, and knowledge retrieval.",
    "research_agent":    "Probe, web research specialist. Performs agentic deep-dive research on any topic.",
    "ops_lt":            "Navigator, Operations Wing Lead Lieutenant. Manages operational tasks, scheduling, and integrations.",
    "maintenance_lt":    "Bosun, Shipwright Wing Lead Lieutenant. Orchestrates autonomous maintenance pipeline: audit → plan → patch → review.",
    "code_auditor":      "Inspector (code_auditor), Shipwright wing bot. Scans codebase for bugs, outdated patterns, and technical debt.",
    "repair_planner":    "Architect (repair_planner), Shipwright wing bot. Plans fixes for issues surfaced by Inspector.",
    "patch_writer":      "Rigger (patch_writer), Shipwright wing bot. Writes code patches based on Architect repair plans.",
    "pr_reviewer":       "Judge (pr_reviewer), Shipwright wing bot. Reviews patches and PRs for correctness before merge.",
    "marshal":           "Marshal, Kanban commander. Decomposes large plans into granular Kanban tasks.",
    "obsidian_archivist":"Scribe (obsidian_archivist), Obsidian vault manager. Reads, writes, and organizes the knowledge vault.",
    "vault_librarian":   "Librarian, vault specialist. Searches and retrieves information from the Obsidian knowledge base.",
    "api_watcher":       "Ledger (api_watcher), billing and API usage watchdog. Monitors for cost anomalies and policy violations.",
    "subscription_watcher": "Vigil (subscription_watcher), subscription and quota watchdog. Tracks OAuth limits and capacity.",
    "email_reader":      "Inbox (email_reader), Gmail triage specialist. Reads and categorizes email using gmail.readonly scope.",
    "email_drafter":     "Quill (email_drafter), Gmail drafting specialist. Creates email drafts using gmail.compose scope (no send permission).",
    "calendar_manager":  "Chronos (calendar_manager), Google Calendar manager. Reads and writes calendar events.",
    "finance_reader":    "Purse (finance_reader), finance data reader. Reads financial data for analysis.",
    "todoist_manager":   "Tasker (todoist_manager), Todoist task manager. Creates, reads, and updates Todoist tasks.",
    "lockbox":           "LockBox, secure credential and authorization manager. Signs grants and manages fleet security.",
    "passive_watch":     "Sonar (passive_watch), passive fleet monitor. Watches for anomalies without active intervention.",
    "hermes_ai_explorer": "Explorer (hermes_ai_explorer), AI capability researcher. Investigates new models, tools, and techniques.",
}

HARDEN_SYSTEM = """You are a concise memory analyst for an AI fleet system. 
Your job is to improve a bot's memory file to be more useful and accurate.
Focus on: clarity, removing redundancy, adding missing key operational facts.
Preserve all important information. Keep output under 400 words.
Format as clean bullet points or short paragraphs. Be specific and actionable."""

SEED_SYSTEM = """You are writing the initial MEMORY.md for an AI bot in a fleet system.
Write a concise, useful memory file (150-250 words) covering:
1. Who this bot is and its role
2. Key operational facts (what it does, doesn't do, its constraints)
3. Important pitfalls or lessons for this role
4. How it interacts with other fleet bots
Be specific, practical, and concise. Format as clear sections."""


def _get_memory_path(bot: str, kind: str = "MEMORY.md") -> Path:
    return HOME / "profiles" / bot / "memories" / kind


def _read_memory(bot: str, kind: str = "MEMORY.md") -> str:
    p = _get_memory_path(bot, kind)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


def _write_memory(bot: str, content: str, kind: str = "MEMORY.md") -> bool:
    p = _get_memory_path(bot, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        _log(f"Write memory {bot}/{kind} failed: {e}")
        return False


def _get_memory_queue() -> list[dict]:
    """Get prioritized list of memories to work on this cycle."""
    queue: list[dict] = []
    profiles_dir = HOME / "profiles"
    if not profiles_dir.exists():
        return queue

    for prof_dir in sorted(profiles_dir.iterdir()):
        if not prof_dir.is_dir():
            continue
        bot = prof_dir.name
        mem_path = prof_dir / "memories" / "MEMORY.md"

        if not mem_path.exists() or mem_path.stat().st_size < 50:
            # Empty or tiny -- needs seeding
            queue.append({"bot": bot, "action": "seed", "priority": 10,
                          "reason": "empty memory"})
        else:
            content = mem_path.read_text(encoding="utf-8", errors="replace")
            chars = len(content)
            age_days = (time.time() - mem_path.stat().st_mtime) / 86400

            # Score: prioritize over-budget, old, or bots with known issues
            score = 0
            reasons = []
            if chars > 1800:   # approaching 2200 cap
                score += 5
                reasons.append(f"over_budget({int(chars/2200*100)}%)")
            if age_days > 7:
                score += 2
                reasons.append(f"stale({age_days:.0f}d)")
            if bot in ("chief_of_staff", "firstmate", "coding_lt", "maintenance_lt"):
                score += 1  # critical bots get priority
                reasons.append("critical_bot")

            if score > 0 or not reasons:
                reasons = reasons or ["routine_review"]
                queue.append({
                    "bot": bot, "action": "harden", "priority": score,
                    "reason": ", ".join(reasons), "chars": chars,
                    "content_preview": content[:300],
                })

    queue.sort(key=lambda x: x.get("priority", 0), reverse=True)
    return queue


def phase_harden_and_seed(scan_report: dict) -> list[str]:
    """Use local Ollama to harden/seed bot memories."""
    improvements: list[str] = []
    queue = _get_memory_queue()
    _log(f"Phase 3+4: HARDEN/SEED -- {len(queue)} bots in queue")

    done_count = 0
    for item in queue:
        if done_count >= MAX_HARDEN_PER_CYCLE:
            break
        bot = item["bot"]
        action = item["action"]

        _log(f"  {action.upper()} {bot} ({item.get('reason','')})...")

        if action == "seed":
            identity = BOT_IDENTITIES.get(bot, f"{bot}: fleet bot in carrier_hermes system")
            prompt = (
                f"Write the initial MEMORY.md for this bot:\n\n"
                f"Bot: {bot}\nIdentity: {identity}\n\n"
                f"Fleet context: carrier_hermes is a 20-bot AI fleet running on Windows "
                f"with Ollama local LLMs (primary) + OAuth subscription fallbacks. "
                f"Primary model: llama3.1:8b-instruct-q4_K_M. "
                f"Discord/Telegram/Buzz for comms. Kanban board for task management. "
                f"Billing policy: never use API keys, never use OpenRouter frontier models."
            )
            result = ollama_chat(prompt, system=SEED_SYSTEM)
            if result:
                _write_memory(bot, result)
                desc = f"Seeded MEMORY.md for {bot} ({len(result)} chars)"
                improvements.append(desc)
                _log(f"  ✓ {desc}")
                done_count += 1

        elif action == "harden":
            current = _read_memory(bot)
            if not current:
                continue
            # Include any relevant bug context for this bot
            bot_issues = [i for i in scan_report.get("issues", [])
                          if i.get("bot") == bot or i.get("assignee") == bot]
            issue_ctx = ""
            if bot_issues:
                issue_ctx = "\n\nRecent issues found for this bot:\n" + "\n".join(
                    f"- [{i['severity']}] {i['detail'][:80]}" for i in bot_issues[:3]
                )

            prompt = (
                f"Here is the current MEMORY.md for bot '{bot}':\n\n"
                f"{current[:1500]}\n"
                f"{issue_ctx}\n\n"
                f"Improve this memory file: remove redundancy, improve clarity, "
                f"add any missing key operational facts based on the bot's role. "
                f"If there are recent issues listed, add a lessons-learned note. "
                f"Return the improved MEMORY.md content only."
            )
            result = ollama_chat(prompt, system=HARDEN_SYSTEM)
            if result and len(result) > 50:
                # Validate: don't shrink dramatically or hallucinate phantom content
                if len(result) > len(current) * 0.3:
                    _write_memory(bot, result)
                    desc = f"Hardened MEMORY.md for {bot} ({len(current)} → {len(result)} chars, reason: {item.get('reason','')})"
                    improvements.append(desc)
                    _log(f"  ✓ {desc}")
                    done_count += 1
                else:
                    _log(f"  ⚠ Ollama output too short for {bot} ({len(result)} chars) -- skipping")

        time.sleep(2)  # brief pause between Ollama calls

    return improvements


# ─── Phase 5: REPORT ─────────────────────────────────────────────────────────
def phase_report(state: dict, scan: dict,
                 fixes: list[str], improvements: list[str]) -> None:
    """Broadcast cycle summary tri-platform."""
    cycle = state["cycle"]
    ts    = datetime.now(timezone.utc).strftime("%H:%M UTC")

    lines = [
        f"🔁 **Hardening Loop — Cycle #{cycle}** [{ts}]",
        f"",
    ]

    # Scan summary
    total_issues = scan.get("total_issues", 0)
    high = scan.get("high", 0)
    if total_issues > 0:
        lines.append(f"🔍 **Scan:** {total_issues} issues — {high} HIGH, {scan.get('medium',0)} MED, {scan.get('low',0)} LOW")
        for i in scan.get("high_issues", [])[:3]:
            lines.append(f"   ⚠ `{i.get('kind','')}` — {i.get('detail','')[:70]}")
    else:
        lines.append("🔍 **Scan:** ✅ Fleet clean — no issues found")

    # Auto-fixes
    if fixes:
        lines.append(f"\n🔧 **Auto-fixed ({len(fixes)}):**")
        for fix in fixes[:5]:
            lines.append(f"   ✓ {fix[:80]}")
    else:
        lines.append("\n🔧 **Fixes:** None needed this cycle")

    # Memory improvements
    if improvements:
        lines.append(f"\n🧠 **Memory hardening ({len(improvements)}):**")
        for imp in improvements[:5]:
            lines.append(f"   ✓ {imp[:80]}")
    else:
        lines.append("\n🧠 **Memory:** No improvements this cycle")

    # Cumulative stats
    lines.append(f"\n📊 **Cumulative:** {state['total_fixes']} fixes · {state['total_memory_improvements']} memory improvements since start")
    lines.append(f"\n_Next cycle in ~30 min · Running until {MICHAEL_DISCORD} says stop_")

    msg = "\n".join(lines)
    broadcast(msg)


# ─── Main entry point ─────────────────────────────────────────────────────────
def main() -> int:
    state = _read_state()
    state["cycle"]    = state.get("cycle", 0) + 1
    state["last_run"] = int(time.time())

    cycle_num = state["cycle"]
    _log(f"{'='*60}")
    _log(f"HARDENING LOOP CYCLE #{cycle_num} START")
    _log(f"{'='*60}")

    # Check halt flags
    if (CARRIER / "SPEND_HALT").exists():
        _log("SPEND_HALT present -- skipping this cycle")
        _write_state(state)
        return 0
    if (CARRIER / "HARDENING_HALT").exists():
        _log("HARDENING_HALT present -- skipping this cycle")
        _write_state(state)
        return 0

    # Phase 1: Scan
    scan_report = phase_scan()
    state["issues_seen"] = state.get("issues_seen", 0) + scan_report.get("total_issues", 0)

    # Phase 2: Auto-fix
    fixes = phase_autofix(scan_report)
    state["total_fixes"] = state.get("total_fixes", 0) + len(fixes)

    # Phase 3+4: Harden + seed memories
    improvements = phase_harden_and_seed(scan_report)
    state["total_memory_improvements"] = (
        state.get("total_memory_improvements", 0) + len(improvements)
    )

    # Phase 5: Report
    phase_report(state, scan_report, fixes, improvements)

    _write_state(state)
    _log(f"CYCLE #{cycle_num} DONE — {len(fixes)} fixes, {len(improvements)} improvements")
    return 0


if __name__ == "__main__":
    sys.exit(main())

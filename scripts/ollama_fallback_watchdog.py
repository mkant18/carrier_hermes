#!/usr/bin/env python3
"""
ollama_fallback_watchdog.py
───────────────────────────
Monitor Ollama on 127.0.0.1:11434. When it goes unreachable, patch all
OMB worker bots from ollama::* → claude-haiku-4-5 (OAuth subscription).
When Ollama comes back, restore the original ollama::* model for each bot.

Usage:
    python ollama_fallback_watchdog.py [--interval 30] [--dry-run]

The script is idempotent: it can be killed and restarted at any time.
State is persisted to ~/.openmausbot/ollama_fallback_state.json so a restart
after Ollama recovers doesn't accidentally leave bots pointing at cloud.

Billing constraint:
    Fallback MUST use anthropic OAuth (auth_type=oauth, instanceId="claude",
    model="claude-haiku-4-5"). No API keys, no OpenRouter.
"""

import argparse
import json
import time
import urllib.request
import urllib.error
import os
import sys
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────

OMB_API    = "http://127.0.0.1:8799"
OLLAMA_URL = "http://127.0.0.1:11434/v1/models"
STATE_FILE = os.path.expanduser("~/.openmausbot/ollama_fallback_state.json")

# OAuth fallback — claude engine, haiku-4-5, subscription only
FALLBACK_INSTANCE  = "claude"
FALLBACK_MODEL     = "claude-haiku-4-5"

# Worker bots eligible for fallback (decision-tier bots are NOT listed here)
WORKER_BOT_NAMES = {
    "Mate", "Yeoman", "Probe", "Inbox", "Quill", "Chronos",
    "Tasker", "Purse", "Librarian", "Clerk", "Vigil", "Sonar",
    "Ledger", "LockBox", "Diver", "Caulker",
}

# Ollama models these workers use (only bots using these are eligible)
OLLAMA_MODEL_PREFIXES = ("ollama::",)


# ── Helpers ──────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def ollama_reachable(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def get_bots() -> list[dict]:
    try:
        with urllib.request.urlopen(f"{OMB_API}/api/bots", timeout=10) as r:
            data = json.loads(r.read())
            return data.get("bots", [])
    except Exception as e:
        log(f"  ERROR fetching bots: {e}")
        return []


def patch_bot(bot_id: str, instance_id: str, model: str, dry_run: bool) -> bool:
    payload = json.dumps({
        "modelSelection": {"instanceId": instance_id, "model": model}
    }).encode()
    if dry_run:
        log(f"  [DRY-RUN] would PATCH {bot_id} → instanceId={instance_id}, model={model}")
        return True
    req = urllib.request.Request(
        f"{OMB_API}/api/bots/{bot_id}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            ok = "bot" in resp
            return ok
    except Exception as e:
        log(f"  ERROR patching {bot_id}: {e}")
        return False


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"ollama_was_down": False, "originals": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Main logic ───────────────────────────────────────────────────────────────

def apply_fallback(bots: list[dict], state: dict, dry_run: bool) -> None:
    """Switch eligible worker bots from ollama::* to claude-haiku-4-5."""
    log(f"Ollama UNREACHABLE → switching worker bots to {FALLBACK_INSTANCE}/{FALLBACK_MODEL}")
    patched = 0
    for bot in bots:
        name = bot.get("name", "")
        if name not in WORKER_BOT_NAMES:
            continue
        ms = bot.get("modelSelection", {})
        current_model = ms.get("model", "")
        current_instance = ms.get("instanceId", "")

        if not any(current_model.startswith(pfx) for pfx in OLLAMA_MODEL_PREFIXES):
            log(f"  SKIP {name}: not on ollama::* (model={current_model})")
            continue

        # Save original so we can restore it later
        bot_id = bot["id"]
        if bot_id not in state["originals"]:
            state["originals"][bot_id] = {
                "name": name,
                "instanceId": current_instance,
                "model": current_model,
            }

        ok = patch_bot(bot_id, FALLBACK_INSTANCE, FALLBACK_MODEL, dry_run)
        if ok:
            log(f"  ✓ {name} ({bot_id[:8]}…): {current_model} → {FALLBACK_MODEL}")
            patched += 1
        else:
            log(f"  ✗ {name}: PATCH failed")

    state["ollama_was_down"] = True
    save_state(state)
    log(f"Fallback applied to {patched} bots. State saved.")


def restore_ollama(bots: list[dict], state: dict, dry_run: bool) -> None:
    """Restore worker bots from claude-haiku-4-5 back to their ollama::* model."""
    log("Ollama REACHABLE again → restoring worker bots to local models")
    originals = state.get("originals", {})
    if not originals:
        log("  No originals recorded — nothing to restore.")
    else:
        bot_by_id = {b["id"]: b for b in bots}
        restored = 0
        for bot_id, orig in originals.items():
            name = orig["name"]
            orig_instance = orig["instanceId"]
            orig_model = orig["model"]
            bot = bot_by_id.get(bot_id)
            if not bot:
                log(f"  SKIP {name}: bot not found in OMB")
                continue
            ok = patch_bot(bot_id, orig_instance, orig_model, dry_run)
            if ok:
                log(f"  ✓ {name}: → {orig_model}")
                restored += 1
            else:
                log(f"  ✗ {name}: restore PATCH failed")
        log(f"Restored {restored} bots.")

    state["ollama_was_down"] = False
    state["originals"] = {}
    save_state(state)


def run(interval: int, dry_run: bool) -> None:
    log(f"Ollama fallback watchdog starting (interval={interval}s, dry_run={dry_run})")
    log(f"Monitoring: {OLLAMA_URL}")
    log(f"Fallback:   {FALLBACK_INSTANCE}/{FALLBACK_MODEL} (OAuth subscription)")
    log(f"State file: {STATE_FILE}")
    log(f"Worker bots: {', '.join(sorted(WORKER_BOT_NAMES))}")
    log("")

    state = load_state()
    log(f"Loaded state: ollama_was_down={state['ollama_was_down']}, "
        f"originals_saved={len(state.get('originals', {}))}")

    while True:
        reachable = ollama_reachable()

        if not reachable and not state["ollama_was_down"]:
            bots = get_bots()
            apply_fallback(bots, state, dry_run)

        elif reachable and state["ollama_was_down"]:
            bots = get_bots()
            restore_ollama(bots, state, dry_run)

        else:
            status = "✅ up" if reachable else "❌ down (fallback already active)"
            log(f"Ollama {status}")

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OMB Ollama fallback watchdog")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval in seconds (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would happen without patching bots")
    args = parser.parse_args()
    try:
        run(args.interval, args.dry_run)
    except KeyboardInterrupt:
        log("Watchdog stopped by user.")
        sys.exit(0)

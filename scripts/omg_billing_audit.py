#!/usr/bin/env python3
"""
OMG Billing Audit — zero LLM, zero network, reads bots.json from disk.
Exits 0 on clean, exits 1 on ANY violation (blocks CI, triggers alerts).

Usage:
    python omg_billing_audit.py [--bots PATH]

Environment (for loud Discord/Telegram alerts on failure):
    DISCORD_FLEET_BOT_TOKEN   First Watch token
    DISCORD_ALERTS_CHANNEL_ID  #alerts channel snowflake
    TELEGRAM_BOT_TOKEN
    TELEGRAM_FLEET_CHAT_ID
"""

import json
import os
import sys
import argparse
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# ── Policy ────────────────────────────────────────────────────────────────────

DECISION_BOTS = {
    "Helm", "Marshal", "Wrench", "Deck", "Stacks",
    "Chart", "Bosun", "Rigger", "Surveyor",
}
MONITOR_BOTS = {"Vigil", "Sonar", "Ledger"}
LOCAL_FIRST  = {
    "Mate", "Yeoman", "Diver", "Caulker", "Probe",
    "Inbox", "Quill", "Chronos", "Tasker", "Purse",
    "Librarian", "Clerk", "LockBox",
}
SKIP = {"Moss"}

DECISION_ENGINES  = {"grok", "codex"}
LOCAL_MODELS      = {
    "ollama::llama3.1:8b-instruct-q4_K_M",
    "ollama::qwen2.5:7b-instruct-q4_K_M",
}
FORBIDDEN_ENGINES = {"openaiCompat"}


# ── Loud failure helpers ───────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  🚨🚨🚨  OMG BILLING AUDIT FAILED  🚨🚨🚨                   ║
║  A bot is misconfigured and may incur unexpected API costs.  ║
║  This PR/push is BLOCKED until violations are fixed.         ║
╚══════════════════════════════════════════════════════════════╝
"""

def post_discord(token: str, channel_id: str, message: str) -> None:
    payload = json.dumps({"content": message}).encode()
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type":  "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [discord alert failed: {e}]", file=sys.stderr)


def post_telegram(token: str, chat_id: str, message: str) -> None:
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [telegram alert failed: {e}]", file=sys.stderr)


def send_alerts(violations: list[str], context: str) -> None:
    msg_discord = (
        f"🚨 **OMG BILLING AUDIT FAILED** — {context}\n"
        + "\n".join(f"• {v}" for v in violations)
        + "\n\n⛔ Push/PR blocked until fixed."
    )
    msg_telegram = (
        f"🚨 <b>OMG BILLING AUDIT FAILED</b> — {context}\n"
        + "\n".join(f"• {v}" for v in violations)
        + "\n\n⛔ Push/PR blocked until fixed."
    )

    token_d   = os.environ.get("DISCORD_FLEET_BOT_TOKEN")
    channel_d = os.environ.get("DISCORD_ALERTS_CHANNEL_ID")
    token_t   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_t    = os.environ.get("TELEGRAM_FLEET_CHAT_ID", "-5577918772")

    if token_d and channel_d:
        post_discord(token_d, channel_d, msg_discord)
        print("  → Discord #alerts notified")
    else:
        print("  → Discord alert skipped (DISCORD_FLEET_BOT_TOKEN or DISCORD_ALERTS_CHANNEL_ID not set)")

    if token_t:
        post_telegram(token_t, chat_t, msg_telegram)
        print("  → Telegram Fleet Command notified")
    else:
        print("  → Telegram alert skipped (TELEGRAM_BOT_TOKEN not set)")


# ── Main audit ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bots",
        default=str(Path.home() / ".openmausbot" / "bots.json"),
        help="Path to bots.json (default: ~/.openmausbot/bots.json)",
    )
    parser.add_argument(
        "--context",
        default="manual run",
        help="Context string for alert messages (e.g. 'PR #42')",
    )
    args = parser.parse_args()

    try:
        bots = json.loads(Path(args.bots).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"❌ bots.json not found at {args.bots} — is OpenMausBot installed?")
        return 1

    violations: list[str] = []
    warnings:   list[str] = []

    print("=== OMG Billing Audit ===\n")
    print(f"  Bots file: {args.bots}")
    print(f"  Bot count: {len(bots)}\n")

    for bot in bots:
        name = bot.get("name", "?")
        if name in SKIP:
            continue

        ms     = bot.get("modelSelection", {})
        engine = ms.get("instanceId", "?")
        model  = ms.get("model", "?")
        auto_a = bot.get("autoApprove", False)

        status = "✅"
        notes: list[str] = []

        # autoApprove must always be off — bots must ask before destructive actions
        if auto_a:
            status = "🚨"
            violations.append(f"{name}: autoApprove=True — bots will act without asking")
            notes.append("autoApprove=True")

        # No bot should ever use the openaiCompat (OpenRouter) engine as its primary
        if engine in FORBIDDEN_ENGINES:
            status = "🚨"
            violations.append(f"{name}: primary engine={engine} (forbidden — OpenRouter direct)")
            notes.append(f"FORBIDDEN ENGINE: {engine}")

        # Decision-tier: must use subscription OAuth engine, never local
        if name in DECISION_BOTS:
            if engine not in DECISION_ENGINES:
                status = "🚨"
                violations.append(
                    f"{name}: decision bot on engine={engine} — expected grok or codex (subscription OAuth)"
                )
                notes.append(f"WRONG ENGINE: {engine}")
            if "ollama::" in model:
                status = "🚨"
                violations.append(
                    f"{name}: decision bot using local model {model} — must use subscription OAuth"
                )
                notes.append("LOCAL on decision bot")

        # Worker/monitor tier: must be on local Ollama
        elif name in (LOCAL_FIRST | MONITOR_BOTS):
            if model not in LOCAL_MODELS:
                # Haiku fallback is OK (watchdog put it there) — warn, don't violation
                if "haiku" in model.lower() or "claude-haiku" in model.lower():
                    status = "⚠️"
                    warnings.append(
                        f"{name}: on Haiku fallback (model={model}) — Ollama may be down"
                    )
                    notes.append("HAIKU FALLBACK (Ollama down?)")
                else:
                    status = "🚨"
                    violations.append(
                        f"{name}: worker/monitor bot not on local Ollama or approved fallback (model={model})"
                    )
                    notes.append(f"BAD MODEL: {model}")
            if engine == "openaiCompat":
                status = "🚨"
                violations.append(f"{name}: worker bot on openaiCompat (forbidden)")
                notes.append("FORBIDDEN ENGINE")

        note_str = f"  [{', '.join(notes)}]" if notes else ""
        print(f"  {status} {name:12} engine={engine:12} model={model[:48]}{note_str}")

    print()

    if warnings:
        print(f"⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"   {w}")
        print()

    if not violations:
        print("✅ All billing policy checks passed. No violations.")
        return 0

    # ── VIOLATION PATH — fail super loudly ────────────────────────────────────
    print(BANNER)
    print(f"🚨 VIOLATIONS ({len(violations)}) — AUDIT FAILED:\n")
    for v in violations:
        print(f"   ❌ {v}")

    print()
    print("Fix before merging: open OpenMausBot, check each flagged bot's model picker,")
    print("and restore the correct engine/model per the carrier_hermes billing policy.")
    print()

    # Send external alerts
    send_alerts(violations, args.context)

    return 1


if __name__ == "__main__":
    sys.exit(main())

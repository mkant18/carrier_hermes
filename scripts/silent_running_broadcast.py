#!/usr/bin/env python3
"""silent_running_broadcast.py — tri-platform EMCON ping for Silent Running.

Posts the fleet-wide "Silent Running, EMCON" announcement (and the "EMCON lifted"
all-clear) to all THREE fleet channels simultaneously, per Michael's standing
comms preference:
    * Discord #fleet   (First Watch REST, DISCORD_FLEET_BOT_TOKEN)
    * Buzz   #fleet    (nak kind:9 signed as the posting bot)
    * Telegram Fleet Command group (-5577918772) with Michael @mentioned

It reuses the battle-tested post helpers from fleet_checkin.py (discord_post,
buzz_post, telegram_send, load_env) instead of re-implementing them. Helm does
NOT get tagged (per preference — Helm is never engaged in automated reports).

The message is posted as Helm (chief_of_staff) since Helm owns the silent-running
process, opening with the exact phrase Michael specified: "Silent Running, EMCON".

Usage:
    python silent_running_broadcast.py enter    # "Silent Running, EMCON" (session start)
    python silent_running_broadcast.py exit      # "EMCON lifted" (session end)

This script MAY call one cheap OpenRouter Gemini-Flash-Lite line for a natural
one-sentence status, but by default it is fully templated and ZERO-LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the proven broadcast helpers from the fleet check-in module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_checkin as FC  # noqa: E402
import silent_running_common as C  # noqa: E402

MICHAEL_DISCORD = "174349224870150144"
FLEET_DISCORD_CHANNEL = "1541866443765977138"  # #fleet


def compose_enter(report: dict | None) -> str:
    lines = [
        "**Helm ⚓** — 🔇 **Silent Running, EMCON**",
        f"<@{MICHAEL_DISCORD}> the deck is dark — beginning autonomous night watch.",
        "",
        "The crew will work the priority ladder slowly and methodically on "
        "**local LLMs** (Qwen2.5-7B), staying under **80% CPU/GPU**, checkpointing "
        "to git every 10 min. OAuth models are reserved for high-level calls only.",
    ]
    if report:
        kb = report.get("kanban", {})
        top = report.get("top_tier_name") or "standby"
        lines += [
            "",
            f"⛓ Opening tier: **{top}**  ·  backlog {kb.get('backlog_count', 0)} · "
            f"maintenance {kb.get('maintenance_open', 0)} open",
        ]
    lines.append("> 🤖 zero-LLM broadcast · $0.00")
    return "\n".join(lines)


def compose_exit(report: dict | None) -> str:
    lines = [
        "**Helm ⚓** — 🔊 **EMCON lifted** — securing from Silent Running.",
        f"<@{MICHAEL_DISCORD}> welcome back. Work in flight has been checkpointed "
        "to git; the crew is standing down from the night watch.",
    ]
    if report:
        cp = report.get("capacity", {})
        lines.append(f"> capacity at handoff: cpu {cp.get('cpu','?')}% · "
                     f"gpu {cp.get('gpu','?')}% · zero-LLM · $0.00")
    return "\n".join(lines)


def broadcast(message: str) -> dict:
    env = FC.load_env()
    discord_token = env.get("DISCORD_FLEET_BOT_TOKEN", "")

    # Telegram token + Michael's uid live in the chief_of_staff profile .env.
    cos_env = C.HERMES_HOME / "profiles" / "chief_of_staff" / ".env"
    tg_token = ""
    tg_uid = ""
    if cos_env.exists():
        for line in cos_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tg_token = line.partition("=")[2].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_ALLOWED_USERS="):
                tg_uid = line.partition("=")[2].strip().split(",")[0].strip()
    tg_chat = FC.BUZZ_CHANNELS.get("command", {}).get("telegram_chat_id", "")

    results = {}
    # Discord
    if discord_token:
        results["discord"] = FC.discord_post(discord_token, FLEET_DISCORD_CHANNEL, message)
    else:
        results["discord"] = False
        print("  [discord] no DISCORD_FLEET_BOT_TOKEN — skipping")

    # Buzz — post as Helm (chief_of_staff), plain text
    buzz_text = message.replace("**", "").replace("`", "")
    results["buzz"] = FC.buzz_post("chief_of_staff", buzz_text, "fleet")

    # Telegram — mention Michael
    if tg_chat and tg_token:
        results["telegram"] = FC.telegram_send(tg_chat, message, tg_token, tg_uid)
    else:
        results["telegram"] = False
        print("  [telegram] missing chat/token — skipping")

    return results


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "enter"

    # Pull a fresh ladder report for context (best-effort).
    report = None
    try:
        import silent_running_ladder as L
        report = L.build_report()
    except Exception:
        pass

    if mode == "exit":
        message = compose_exit(report)
    else:
        message = compose_enter(report)

    print(f"--- Silent Running broadcast ({mode}) ---\n{message}\n---")
    results = broadcast(message)
    ok = any(results.values())
    C.log(f"broadcast({mode}): " + " ".join(f"{k}={'OK' if v else 'FAIL'}"
                                             for k, v in results.items()))
    print("  " + " ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

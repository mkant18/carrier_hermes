#!/usr/bin/env python3
"""silent_running_omb_audit.py — zero-LLM OMB bot health inspector (Silent Running Tier 3b).

Scans every bot's event NDJSON log, bots.json config, and running harness state
to produce a prioritised health queue. The harden worker (silent_running_omb_harden.py)
consumes this queue to propose identity/prompt improvements via local LLM.

Health signals scored per bot:
  * error_rate      — fraction of turns ending ok=False (rpc_error, broker-error, etc.)
  * zero_token_rate — turns where input+output tokens = 0 (model never ran)
  * wrong_engine    — instanceId banned (grok API-key driver) or unavailable instance
  * stale_desc      — description mentions banned engines (grok, openrouter, api key)
  * silent_turns    — turns completed with no assistant_text items (Marshal pattern)
  * no_events       — bot has never had a turn (brand new or completely broken)

Output JSON schema:
  {generated_at, total_bots, unhealthy_count, queue: [{bot_id, name, score, signals, ...}]}

ZERO-LLM. Safe from cron / no_agent contexts.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import silent_running_common as C

OMB_DATA = Path.home() / ".openmausbot"
EVENTS_DIR = OMB_DATA / "events"
BOTS_FILE = OMB_DATA / "bots.json"
HARNESS_URL = "http://127.0.0.1:8799"

# Engines that should never be used per fleet billing policy
BANNED_INSTANCE_IDS = {"grok"}  # grokAgent (CLI) is allowed; grok (API-key) is not

# Phrases in descriptions that indicate stale/wrong billing instructions
STALE_DESC_PATTERNS = [
    "xai", "openrouter", "api key", "api-key", "grok engine",
    "use the grok", "openai compat",
]

# Minimum turns before we start scoring error rates
MIN_TURNS_FOR_RATE = 2

# Score thresholds
UNHEALTHY_SCORE = 1.5


def _fetch_harness_bots() -> list[dict]:
    """Get live bot list from harness (includes current activity/busy state)."""
    try:
        with urllib.request.urlopen(f"{HARNESS_URL}/api/bots", timeout=5) as r:
            return json.loads(r.read()).get("bots", [])
    except Exception:
        return []


def _fetch_instances() -> dict[str, dict]:
    """Map instanceId -> snapshot from harness."""
    try:
        with urllib.request.urlopen(f"{HARNESS_URL}/api/instances", timeout=5) as r:
            instances = json.loads(r.read()).get("instances", [])
            return {i["instanceId"]: i for i in instances}
    except Exception:
        return {}


def _parse_events(thread_id: str) -> list[dict]:
    path = EVENTS_DIR / f"{thread_id}.ndjson"
    if not path.exists():
        return []
    events = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return events


def _score_bot(bot: dict, instances: dict[str, dict]) -> dict:
    bot_id = bot.get("id", "")
    name = bot.get("name", "?")
    thread_id = bot.get("threadId", "")
    ms = bot.get("modelSelection", {})
    instance_id = ms.get("instanceId", "")
    model = ms.get("model", "")
    description = bot.get("description", "")

    events = _parse_events(thread_id)

    # Group events by turnId
    turns: dict[str, dict] = {}
    for e in events:
        tid = e.get("turnId")
        if not tid:
            continue
        if tid not in turns:
            turns[tid] = {
                "completed": False, "ok": None, "stopReason": None,
                "has_text": False, "tokens_in": 0, "tokens_out": 0,
                "has_error": False, "error_msg": "",
            }
        t = turns[tid]
        etype = e.get("type", "")
        if etype == "turn.completed":
            t["completed"] = True
            t["ok"] = e.get("ok")
            t["stopReason"] = e.get("stopReason")
        elif etype == "item.completed" and e.get("itemType") == "assistant_text":
            t["has_text"] = True
        elif etype == "thread.token-usage.updated":
            t["tokens_in"] += e.get("input", 0) or 0
            t["tokens_out"] += e.get("output", 0) or 0
        elif etype == "runtime.error":
            t["has_error"] = True
            t["error_msg"] = e.get("message", "")

    completed = [t for t in turns.values() if t["completed"]]
    total = len(completed)

    signals = []
    score = 0.0

    # Signal: no events at all
    if total == 0 and len(events) == 0:
        signals.append("no_events")
        score += 0.5

    # Signal: error rate
    if total >= MIN_TURNS_FOR_RATE:
        errors = sum(1 for t in completed if not t["ok"])
        err_rate = errors / total
        if err_rate >= 0.5:
            signals.append(f"error_rate:{err_rate:.0%}({errors}/{total})")
            score += 2.0 + err_rate
        elif err_rate > 0:
            signals.append(f"error_rate:{err_rate:.0%}({errors}/{total})")
            score += err_rate

    # Signal: zero-token turns (model ran but charged nothing — grok API miss)
    if total >= MIN_TURNS_FOR_RATE:
        zero_tok = sum(1 for t in completed if t["tokens_in"] == 0 and t["tokens_out"] == 0)
        zero_rate = zero_tok / total
        if zero_rate >= 0.5:
            signals.append(f"zero_token:{zero_rate:.0%}({zero_tok}/{total})")
            score += 2.0

    # Signal: silent turns (completed but no assistant_text)
    if total >= MIN_TURNS_FOR_RATE:
        silent = sum(1 for t in completed if t["ok"] and not t["has_text"])
        if silent > 0:
            signals.append(f"silent_turns:{silent}/{total}")
            score += 1.0 + (silent / total)

    # Signal: wrong/banned engine
    if instance_id in BANNED_INSTANCE_IDS:
        signals.append(f"banned_engine:{instance_id}")
        score += 3.0

    # Signal: engine unavailable in harness
    inst = instances.get(instance_id)
    if inst and inst.get("snapshot", {}).get("state") == "unavailable":
        signals.append(f"engine_unavailable:{instance_id}")
        score += 2.0

    # Signal: stale description mentioning banned providers
    desc_lower = description.lower()
    stale_hits = [p for p in STALE_DESC_PATTERNS if p in desc_lower]
    if stale_hits:
        signals.append(f"stale_desc:{','.join(stale_hits[:3])}")
        score += 0.5 * len(stale_hits)

    # Signal: no description at all
    if not description.strip():
        signals.append("no_description")
        score += 1.0

    # Last error message for context
    last_error = ""
    for t in reversed(completed):
        if t["has_error"]:
            last_error = t["error_msg"]
            break

    return {
        "bot_id": bot_id,
        "name": name,
        "instance_id": instance_id,
        "model": model,
        "score": round(score, 2),
        "signals": signals,
        "total_turns": total,
        "last_error": last_error,
        "description_chars": len(description),
        "description_snippet": description[:120].replace("\n", " "),
        "unhealthy": score >= UNHEALTHY_SCORE,
    }


def build_queue() -> dict:
    # Load bots from disk (harness may be down — fallback)
    bots_raw: list[dict] = []
    if BOTS_FILE.exists():
        try:
            bots_raw = json.loads(BOTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Enrich with live harness state if available
    instances = _fetch_instances()

    scored = []
    for bot in bots_raw:
        scored.append(_score_bot(bot, instances))

    scored.sort(key=lambda b: b["score"], reverse=True)
    unhealthy = [b for b in scored if b["unhealthy"]]

    return {
        "generated_at": int(time.time()),
        "total_bots": len(scored),
        "unhealthy_count": len(unhealthy),
        "unhealthy_threshold": UNHEALTHY_SCORE,
        "queue": scored,
        "note": (
            "Workers (local LLM via silent_running_omb_harden.py) propose improved "
            "system prompts for unhealthy bots. OAuth Helm reviews each change before "
            "it is written to bots.json. This script performs NO writes."
        ),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--unhealthy-only", action="store_true")
    args = ap.parse_args()

    q = build_queue()
    bots = q["queue"] if not args.unhealthy_only else [b for b in q["queue"] if b["unhealthy"]]

    if args.json:
        out = dict(q)
        out["queue"] = bots
        print(json.dumps(out, indent=2))
        return 0

    print("=== Silent Running — OMB Bot Health Audit (Tier 3b) ===")
    print(f"total={q['total_bots']}  unhealthy={q['unhealthy_count']}  "
          f"threshold={q['unhealthy_threshold']}")
    print()
    for b in bots:
        flag = "🔴" if b["unhealthy"] else "🟢"
        print(f"  {flag} [{b['score']:>5}] {b['name']:20s}  "
              f"{b['instance_id']:10s}/{b['model'][:30]}")
        for sig in b["signals"]:
            print(f"           ↳ {sig}")
        if b["last_error"]:
            print(f"           last_error: {b['last_error'][:80]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

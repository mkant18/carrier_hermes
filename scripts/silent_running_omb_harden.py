#!/usr/bin/env python3
"""silent_running_omb_harden.py — local-LLM bot identity hardening worker (Silent Running Tier 3b).

Consumes the queue from silent_running_omb_audit.py. For each unhealthy bot:
  1. Feeds bot name, role, description, and error signals into Ollama qwen2.5:7b
  2. Gets a suggested improved system prompt (tightened identity + correct billing line)
  3. Writes the proposal to a staging file in ~/.openmausbot/harden_proposals/
  4. Does NOT write to bots.json — Helm (OAuth) reviews proposals and calls
     the harness PATCH API only after approving each one

Fleet billing policy enforced in every generated prompt:
  - Decision-tier: "claude OAuth subscription (claude-sonnet-4-6). Fallback: codex OAuth."
  - Worker-tier: "Local Ollama PRIMARY — claude or codex engine, ollama::llama3.1:8b-instruct-q4_K_M"
  - Monitor-tier: "Local Ollama — ollama::qwen2.5:7b-instruct-q4_K_M"
  - NEVER: grok API, OpenRouter, API keys

Usage:
    python silent_running_omb_harden.py [--dry-run] [--bot-id ID] [--max N]

Uses Ollama REST (http://localhost:11434/api/chat) with qwen2.5:7b-instruct-q4_K_M.
Local LLM only — zero OAuth spend.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

import silent_running_common as C

OMB_DATA = Path.home() / ".openmausbot"
BOTS_FILE = OMB_DATA / "bots.json"
PROPOSALS_DIR = OMB_DATA / "harden_proposals"
HARNESS_URL = "http://127.0.0.1:8799"

OLLAMA_URL = "http://localhost:11434/api/chat"
HARDEN_MODEL = "qwen2.5:7b-instruct-q4_K_M"

# Bot tier classification by name (lowercase) — drives billing line injected into prompt
DECISION_TIER = {"helm", "marshal", "wrench", "deck", "stacks", "chart",
                 "bosun", "rigger", "surveyor"}
MONITOR_TIER  = {"vigil", "sonar", "ledger", "lockbox"}
# Everything else = worker tier

BILLING_LINES = {
    "decision": (
        "ENGINE & BILLING: claude OAuth subscription (claude-sonnet-4-6). "
        "Fallback: codex OAuth subscription. "
        "NEVER: Grok API, OpenRouter, API keys, local Ollama."
    ),
    "worker": (
        "ENGINE & BILLING: Local Ollama PRIMARY — use claude or codex engine and pick "
        "ollama::llama3.1:8b-instruct-q4_K_M. "
        "Fallback chain: grok subscription → codex subscription → claude haiku OAuth → "
        "OpenRouter deepseek-flash (absolute last resort). Never frontier OR models."
    ),
    "monitor": (
        "ENGINE & BILLING: Local Ollama — ollama::qwen2.5:7b-instruct-q4_K_M. "
        "Fallback: claude haiku OAuth subscription only. Never OpenRouter, never API keys."
    ),
}


def _tier(name: str) -> str:
    n = name.lower()
    if n in DECISION_TIER:
        return "decision"
    if n in MONITOR_TIER:
        return "monitor"
    return "worker"


def _ollama_chat(prompt: str) -> str:
    """Send one prompt to Ollama, return response text or raise."""
    payload = {
        "model": HARDEN_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["message"]["content"].strip()


def _build_harden_prompt(bot: dict, audit: dict) -> str:
    name = bot.get("name", "?")
    title = bot.get("title", "")
    current_desc = bot.get("description", "(none)")
    signals = audit.get("signals", [])
    last_error = audit.get("last_error", "")
    tier = _tier(name)
    billing = BILLING_LINES[tier]

    return f"""You are a fleet operations specialist improving bot system prompts for the carrier_hermes fleet.

BOT: {name}
TITLE: {title}
TIER: {tier}
CURRENT DESCRIPTION:
---
{current_desc}
---
DETECTED ISSUES: {', '.join(signals) if signals else 'none flagged'}
LAST ERROR: {last_error or 'none'}

TASK:
Write an improved system prompt for this bot. Requirements:
1. Keep the bot's core identity, role, and personality intact
2. Make the role description tighter and more specific (what exactly this bot owns, what it never does)
3. Replace ANY billing/engine instructions with EXACTLY this line (do not modify it):
   {billing}
4. Remove any mention of: grok API, XAI_API_KEY, OpenRouter, API keys, or any banned engine
5. Keep it concise — under 200 words total
6. Do NOT include the bot's name in the opening line (OMB prepends "You are <name>," automatically)

Respond with ONLY the new system prompt text — no preamble, no explanation, no markdown fences."""


def _load_bots() -> list[dict]:
    if not BOTS_FILE.exists():
        return []
    return json.loads(BOTS_FILE.read_text(encoding="utf-8"))


def _load_audit_queue(max_bots: int, bot_id: Optional[str] = None) -> list[dict]:
    """Run the audit inline and return the unhealthy queue."""
    import importlib.util, sys
    audit_path = Path(__file__).parent / "silent_running_omb_audit.py"
    spec = importlib.util.spec_from_file_location("omb_audit", audit_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    q = mod.build_queue()
    bots = [b for b in q["queue"] if b["unhealthy"]]
    if bot_id:
        bots = [b for b in bots if b["bot_id"] == bot_id]
    return bots[:max_bots]


def _write_proposal(bot_id: str, name: str, proposed_desc: str,
                    audit: dict, dry_run: bool) -> Path:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    fname = f"{name.lower().replace(' ','_')}_{ts}.json"
    proposal = {
        "created_at": ts,
        "bot_id": bot_id,
        "name": name,
        "audit_signals": audit.get("signals", []),
        "audit_score": audit.get("score"),
        "proposed_description": proposed_desc,
        "status": "pending_review",  # Helm sets to "approved" or "rejected"
        "reviewed_at": None,
        "patch_url": f"{HARNESS_URL}/api/bots/{bot_id}",
        "patch_body": {"description": proposed_desc},
    }
    path = PROPOSALS_DIR / fname
    if not dry_run:
        path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Generate proposals but don't write them to disk")
    ap.add_argument("--bot-id", help="Only harden this specific bot ID")
    ap.add_argument("--max", type=int, default=3,
                    help="Max bots to harden per run (default 3, respect concurrency cap)")
    args = ap.parse_args()

    # Gate: must have Ollama with the required model
    if not C.ollama_ready():
        print(f"[harden] Ollama not ready with {C.REQUIRED_MODEL} — aborting")
        return 1

    # Get audit queue
    queue = _load_audit_queue(max_bots=args.max, bot_id=args.bot_id)
    if not queue:
        print("[harden] No unhealthy bots found — nothing to do")
        return 0

    bots_by_id = {b["id"]: b for b in _load_bots()}

    results = []
    for audit in queue:
        bot_id = audit["bot_id"]
        name = audit["name"]
        bot = bots_by_id.get(bot_id, {"name": name, "description": "", "title": ""})

        print(f"[harden] Processing {name} (score={audit['score']} signals={audit['signals']})")
        C.log(f"omb_harden: processing {name} bot_id={bot_id} signals={audit['signals']}")

        try:
            prompt = _build_harden_prompt(bot, audit)
            proposed = _ollama_chat(prompt)
        except Exception as e:
            print(f"[harden] {name}: Ollama failed — {e}")
            C.log(f"omb_harden: {name} ollama error: {e}")
            continue

        path = _write_proposal(bot_id, name, proposed, audit, dry_run=args.dry_run)
        print(f"[harden] {name}: proposal {'(dry-run, not written)' if args.dry_run else f'written → {path.name}'}")
        C.log(f"omb_harden: {name} proposal written to {path}")
        results.append({"name": name, "proposal": str(path), "chars": len(proposed)})

    print(f"\n[harden] Done. {len(results)}/{len(queue)} proposals generated.")
    if results:
        print("Pending Helm review in:", str(PROPOSALS_DIR))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

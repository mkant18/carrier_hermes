#!/usr/bin/env python3
"""silent_running_memory.py — tier-3 memory-optimization queue builder.

Zero-LLM inspector that assembles the work queue for Silent Running TIER 3
(agent-memory optimization). It does NOT rewrite any memory itself — rewriting is
a judgment task done by the local-LLM workers, with the LT + Helm calling an OAuth
model to VERIFY that each proposed change is important and ideal (per Michael's
requirement). This script just finds the memory stores, measures them, applies the
OpenViking tiering concept, and emits a prioritized queue.

OpenViking concept applied to memory (per carrier_hermes/integrations/openviking.md):
  Every memory store is decomposed into three tiers so context stays cheap:
    L0 (abstract) — a one-line summary of the whole store (always resident)
    L1 (overview) — section headers / bullet leads (loaded on demand)
    L2 (details)  — full entries (lazy, only when a query needs them)
  The optimization pass restructures each MEMORY.md so its highest-signal facts
  surface at L0/L1 and stale/duplicate detail is pruned from L2 — exactly the
  "self-evolving context database" idea, done locally against the markdown stores.

Memory stores scanned:
  * Global:      <home>/memories/MEMORY.md and USER.md
  * Per-profile: <home>/profiles/<bot>/memories/MEMORY.md and USER.md (when present)

Scoring (which stores most need an optimization pass):
  * over_budget   — approaching the char cap (MEMORY 2200 / USER 1375 per Hermes)
  * dup_ratio     — fraction of near-duplicate lines (cheap shingle heuristic)
  * stale_days    — days since last modified (very fresh = skip; very old = review)
  * size          — larger stores get reviewed before tiny ones

Usage:
    python silent_running_memory.py            # human-readable + JSON queue
    python silent_running_memory.py --json     # JSON only (for Helm)

ZERO-LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import silent_running_common as C

# Hermes memory char caps (from the memory tool spec).
CAPS = {"MEMORY.md": 2200, "USER.md": 1375}
BUDGET_WARN = 0.80  # flag stores >= 80% of cap


def _dup_ratio(text: str) -> float:
    """Cheap near-duplicate line ratio via normalized shingles."""
    lines = [l.strip().lower() for l in text.splitlines()
             if len(l.strip()) > 12 and not l.strip().startswith("#")]
    if len(lines) < 2:
        return 0.0
    seen: set[str] = set()
    dups = 0
    for l in lines:
        key = l[:60]
        if key in seen:
            dups += 1
        seen.add(key)
    return round(dups / len(lines), 2)


def inspect_store(path: Path, kind: str, owner: str) -> dict | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    chars = len(text)
    cap = CAPS.get(kind, 2200)
    entries = text.count("\n§") + (1 if text.strip() else 0)
    mtime = path.stat().st_mtime
    stale_days = round((time.time() - mtime) / 86400, 1)
    dup = _dup_ratio(text)
    budget = round(chars / cap, 2)

    # Composite review score — higher = more in need of a pass.
    score = 0.0
    if budget >= BUDGET_WARN:
        score += 3.0 + (budget - BUDGET_WARN) * 5
    score += dup * 2.0
    score += min(stale_days / 30.0, 1.0)          # up to +1 for a month stale
    score += min(chars / cap, 1.0) * 0.5

    reasons = []
    if budget >= BUDGET_WARN:
        reasons.append(f"over_budget({int(budget*100)}%)")
    if dup >= 0.15:
        reasons.append(f"dup_ratio({dup})")
    if stale_days >= 21:
        reasons.append(f"stale({stale_days}d)")
    if not reasons:
        reasons.append("routine")

    return {
        "owner": owner,
        "kind": kind,
        "path": str(path),
        "chars": chars,
        "cap": cap,
        "budget_pct": int(budget * 100),
        "entries": entries,
        "dup_ratio": dup,
        "stale_days": stale_days,
        "score": round(score, 2),
        "reasons": reasons,
    }


def build_queue() -> dict:
    home = C.HERMES_HOME
    stores: list[dict] = []

    # Global memory.
    for kind in ("MEMORY.md", "USER.md"):
        s = inspect_store(home / "memories" / kind, kind, "global")
        if s:
            stores.append(s)

    # Per-profile memory.
    prof_dir = home / "profiles"
    if prof_dir.is_dir():
        for d in sorted(prof_dir.iterdir()):
            if not d.is_dir():
                continue
            for kind in ("MEMORY.md", "USER.md"):
                s = inspect_store(d / "memories" / kind, kind, d.name)
                if s:
                    stores.append(s)

    stores.sort(key=lambda s: s["score"], reverse=True)
    return {
        "generated_at": int(time.time()),
        "openviking_concept": "L0 abstract / L1 overview / L2 detail retiering per store",
        "total_stores": len(stores),
        "needs_review": [s for s in stores if s["score"] >= 1.0],
        "queue": stores,
        "note": (
            "Workers (local LLM) propose retiered/pruned MEMORY.md rewrites; the "
            "owning LT + Helm call an OAuth model to VERIFY each change is important "
            "and ideal before it is committed. This script performs NO writes."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    q = build_queue()
    if args.json:
        print(json.dumps(q, indent=2))
        return 0
    print("=== Silent Running — Tier 3 Memory Optimization Queue ===")
    print(f"stores scanned: {q['total_stores']}  needing review: {len(q['needs_review'])}")
    for s in q["queue"]:
        print(f"  [{s['score']:>5}] {s['owner']:20} {s['kind']:10} "
              f"{s['budget_pct']:>3}% cap · dup {s['dup_ratio']} · "
              f"{s['stale_days']}d · {', '.join(s['reasons'])}")
    print(json.dumps(q))
    return 0


if __name__ == "__main__":
    sys.exit(main())

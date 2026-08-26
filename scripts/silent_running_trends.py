#!/usr/bin/env python3
"""silent_running_trends.py — zero-LLM trend DATA-GATHERER for Silent Running tier 5.

Tier 5 (TRENDS) is Michael's explicit exception to the "primarily local LLM" rule:
the ANALYSIS is done by Helm + the LTs on OAuth models (Claude Sonnet/Opus), and
MUST stay on subscription OAuth — NEVER OpenRouter. This script does NOT do the
analysis. It does the cheap, deterministic part: mining the raw signals so the
OAuth models reason over a compact pre-digested dataset instead of re-crawling
every DB (which would waste subscription turns).

Two signal families are gathered:

  A. STALL PATTERNS — where bots get stuck repeatedly
     * Kanban tasks with consecutive_failures > 0 or status='blocked'
     * task_runs with outcome in (failed, error, timeout) grouped by profile + error
     * recurring last_failure_error strings (the same wall hit many times)
     * per-bot session end_reason tallies that look like stalls
       (rate_limit / error / timeout / handoff)

  B. BILLING / USAGE PATTERNS — from each profile's session_model_usage
     * per-provider api_call_count, tokens, estimated vs actual cost
     * any NON-$0 actual_cost (would indicate a metered route — a red flag)
     * heaviest models by call volume (where the fleet spends its turns)
     * OpenRouter usage split (allowlist vs anything unexpected)

Output is a JSON digest written to
  carrier_hermes/_agent/silent_running/trends_digest_<date>.json
and echoed to stdout, ready to hand to Helm/LTs for the OAuth analysis pass.

ZERO-LLM. Read-only. Spends no tokens.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import silent_running_common as C

OUT_DIR = C.REPO / "_agent" / "silent_running"
STALL_END_REASONS = ("rate_limit", "rate-limit", "error", "timeout", "timed_out",
                     "handoff", "overloaded", "quota", "429", "failed")
FAIL_OUTCOMES = ("failed", "error", "timeout", "timed_out", "blocked")


def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# ─── A. Stall patterns ────────────────────────────────────────────────────────

def gather_stalls(window_h: int) -> dict:
    since = time.time() - window_h * 3600
    out = {
        "blocked_tasks": [],
        "failing_tasks": [],
        "run_failures_by_profile": {},
        "recurring_errors": [],
        "session_stall_reasons": {},
    }

    conn = _ro(C.KANBAN_DB)
    if conn:
        try:
            # Blocked / repeatedly-failing tasks.
            for r in conn.execute(
                "SELECT id, assignee, status, consecutive_failures, "
                "substr(title,1,60) AS t, substr(last_failure_error,1,160) AS err "
                "FROM tasks WHERE status='blocked' OR consecutive_failures > 0 "
                "ORDER BY consecutive_failures DESC"):
                rec = dict(r)
                if r["status"] == "blocked":
                    out["blocked_tasks"].append(rec)
                if (r["consecutive_failures"] or 0) > 0:
                    out["failing_tasks"].append(rec)

            # task_runs failures grouped by profile.
            prof_fail = defaultdict(int)
            err_counter = Counter()
            for r in conn.execute(
                "SELECT profile, outcome, substr(error,1,120) AS err, ended_at "
                "FROM task_runs WHERE outcome IS NOT NULL"):
                oc = (r["outcome"] or "").lower()
                if any(f in oc for f in FAIL_OUTCOMES):
                    prof_fail[r["profile"] or "?"] += 1
                    if r["err"]:
                        err_counter[r["err"].strip()] += 1
            out["run_failures_by_profile"] = dict(
                sorted(prof_fail.items(), key=lambda kv: kv[1], reverse=True))
            out["recurring_errors"] = [
                {"error": e, "count": n} for e, n in err_counter.most_common(10) if n >= 2
            ]
        finally:
            conn.close()

    # Per-bot session end_reason stalls.
    prof_dir = C.HERMES_HOME / "profiles"
    if prof_dir.is_dir():
        for d in sorted(prof_dir.iterdir()):
            sdb = d / "state.db"
            conn = _ro(sdb)
            if not conn:
                continue
            try:
                tally = Counter()
                for r in conn.execute(
                    "SELECT end_reason FROM sessions "
                    "WHERE ended_at IS NOT NULL AND started_at > ?", (since,)):
                    er = (r["end_reason"] or "").lower()
                    if er and any(k in er for k in STALL_END_REASONS):
                        tally[er] += 1
                if tally:
                    out["session_stall_reasons"][d.name] = dict(tally)
            except Exception:
                pass
            finally:
                conn.close()
    return out


# ─── B. Billing / usage patterns ──────────────────────────────────────────────

def gather_billing() -> dict:
    out = {
        "by_provider": defaultdict(lambda: {"calls": 0, "in": 0, "out": 0,
                                            "est_usd": 0.0, "actual_usd": 0.0}),
        "by_model": defaultdict(lambda: {"calls": 0, "actual_usd": 0.0}),
        "nonzero_actual_cost": [],   # RED FLAG: any real spend
        "openrouter_models": defaultdict(int),
    }
    prof_dir = C.HERMES_HOME / "profiles"
    if not prof_dir.is_dir():
        return _finalize_billing(out)

    for d in sorted(prof_dir.iterdir()):
        conn = _ro(d / "state.db")
        if not conn:
            continue
        try:
            for r in conn.execute(
                "SELECT model, billing_provider, api_call_count, input_tokens, "
                "output_tokens, estimated_cost_usd, actual_cost_usd "
                "FROM session_model_usage"):
                prov = r["billing_provider"] or "?"
                model = r["model"] or "?"
                calls = r["api_call_count"] or 0
                p = out["by_provider"][prov]
                p["calls"] += calls
                p["in"] += r["input_tokens"] or 0
                p["out"] += r["output_tokens"] or 0
                p["est_usd"] += r["estimated_cost_usd"] or 0.0
                p["actual_usd"] += r["actual_cost_usd"] or 0.0
                m = out["by_model"][model]
                m["calls"] += calls
                m["actual_usd"] += r["actual_cost_usd"] or 0.0
                if (r["actual_cost_usd"] or 0.0) > 0:
                    out["nonzero_actual_cost"].append({
                        "bot": d.name, "model": model, "provider": prov,
                        "actual_usd": round(r["actual_cost_usd"], 4),
                    })
                if prov == "openrouter":
                    out["openrouter_models"][model] += calls
        except Exception:
            pass
        finally:
            conn.close()
    return _finalize_billing(out)


def _finalize_billing(out: dict) -> dict:
    out["by_provider"] = {
        k: {**v, "est_usd": round(v["est_usd"], 4),
            "actual_usd": round(v["actual_usd"], 4)}
        for k, v in sorted(out["by_provider"].items(),
                           key=lambda kv: kv[1]["calls"], reverse=True)
    }
    out["by_model"] = {
        k: {**v, "actual_usd": round(v["actual_usd"], 4)}
        for k, v in sorted(out["by_model"].items(),
                           key=lambda kv: kv[1]["calls"], reverse=True)[:15]
    }
    out["openrouter_models"] = dict(
        sorted(out["openrouter_models"].items(), key=lambda kv: kv[1], reverse=True))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-h", type=int, default=48,
                    help="stall lookback window in hours (default 48)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="also write the digest JSON to _agent/silent_running/")
    args = ap.parse_args()

    digest = {
        "generated_at": int(time.time()),
        "window_hours": args.window_h,
        "analysis_owner": "Helm + LTs on Claude Sonnet/Opus — SUBSCRIPTION OAUTH ONLY "
                          "(never OpenRouter). This file is zero-LLM input data.",
        "stalls": gather_stalls(args.window_h),
        "billing": gather_billing(),
    }

    # Surface the most important flag up top.
    flags = []
    if digest["billing"]["nonzero_actual_cost"]:
        flags.append("NONZERO_ACTUAL_COST — a metered route is billing; investigate")
    if digest["stalls"]["recurring_errors"]:
        flags.append(f"{len(digest['stalls']['recurring_errors'])} recurring error pattern(s)")
    if digest["stalls"]["blocked_tasks"]:
        flags.append(f"{len(digest['stalls']['blocked_tasks'])} blocked task(s)")
    digest["flags"] = flags

    if args.write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        p = OUT_DIR / f"trends_digest_{date.today():%Y-%m-%d}.json"
        p.write_text(json.dumps(digest, indent=2), encoding="utf-8")
        C.log(f"trends: wrote digest {p.name} flags={flags}")
        print(f"wrote {p}")

    if args.json:
        print(json.dumps(digest, indent=2))
        return 0

    print("=== Silent Running — Tier 5 Trends Digest (zero-LLM input) ===")
    print(f"window: {args.window_h}h   flags: {flags or 'none'}")
    b = digest["billing"]
    print("\nBilling by provider (calls / est$ / ACTUAL$):")
    for prov, v in b["by_provider"].items():
        print(f"  {prov:14} calls={v['calls']:>5} est=${v['est_usd']:.4f} "
              f"actual=${v['actual_usd']:.4f}")
    if b["nonzero_actual_cost"]:
        print("  ⚠️ NONZERO ACTUAL COST:", b["nonzero_actual_cost"])
    s = digest["stalls"]
    print(f"\nStalls: blocked={len(s['blocked_tasks'])} "
          f"failing={len(s['failing_tasks'])} "
          f"recurring_errors={len(s['recurring_errors'])}")
    for e in s["recurring_errors"][:5]:
        print(f"  ×{e['count']}  {e['error']}")
    if s["run_failures_by_profile"]:
        print("  failures by profile:", s["run_failures_by_profile"])
    print("\n" + json.dumps(digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())

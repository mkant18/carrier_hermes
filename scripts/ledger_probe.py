#!/usr/bin/env python3
"""
Ledger Probe — Carrier Hermes API Watcher
==========================================
Aggregates spend data from TWO sources:
  1. Hermes state.db (session_model_usage + sessions) across ALL 20 profile DBs
  2. OpenRouter /api/v1/key + /api/v1/credits for real OR balance

Writes output JSON to: $OBSIDIAN_VAULT_PATH/_agent/api_watcher/ledger-snapshot.json
Also writes rolling daily log: $OBSIDIAN_VAULT_PATH/_agent/api_watcher/ledger-YYYY-MM-DD.jsonl

Usage:
  python3 ledger_probe.py [--full]    # --full includes per-session rows
  python3 ledger_probe.py --live      # parse recent agent.log lines only (fast)

Exit codes:
  0 = success, under all caps
  1 = error
  2 = soft cap hit (>= soft_daily threshold)
  3 = hard cap hit (>= hard_daily threshold)
"""

from __future__ import annotations
import argparse
import datetime
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

# ─── Config ────────────────────────────────────────────────────────────────────
HOME = Path.home()
CARRIER_ROOT = HOME / "carrier_hermes"
VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", HOME / "Desktop" / "Existing Folders" / "OBSIDIAN"))
OUT_DIR = VAULT / "_agent" / "api_watcher"
SNAPSHOT_PATH = OUT_DIR / "ledger-snapshot.json"
ENV_FILE = Path(os.environ.get("HERMES_HOME", HOME / ".hermes")) / ".env"

SOFT_DAILY = float(os.environ.get("CARRIER_OR_SOFT_DAILY", "8"))
HARD_DAILY = float(os.environ.get("CARRIER_OR_HARD_DAILY", "15"))

PROFILES_DIR = HOME / ".hermes" / "profiles"
LOG_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO "
    r"\[(?P<session>[^\]]+)\] agent\.conversation_loop: "
    r"API call #\d+: model=(?P<model>\S+) provider=(?P<provider>\S+) "
    r"in=(?P<inp>\d+) out=(?P<out>\d+) total=(?P<total>\d+) latency=(?P<lat>[0-9.]+)s"
)


# ─── Helpers ───────────────────────────────────────────────────────────────────
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def or_fetch(key: str, endpoint: str) -> dict[str, Any]:
    """Fetch an OpenRouter API endpoint. Returns parsed JSON or {'error': ...}."""
    import urllib.request
    import urllib.error
    url = f"https://openrouter.ai/api/v1/{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def read_profile_db(db_path: Path) -> dict[str, Any]:
    """Read session_model_usage + sessions from one profile state.db."""
    # Default profile lives at ~/.hermes/state.db (parent = .hermes, not a profile name)
    parent_name = db_path.parent.name
    profile = "default" if parent_name == ".hermes" else parent_name
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Aggregate usage by model/provider
        cur.execute("""
            SELECT 
                model, billing_provider,
                SUM(api_call_count) as calls,
                SUM(input_tokens) as inp,
                SUM(output_tokens) as out,
                SUM(cache_read_tokens) as cache_read,
                SUM(cache_write_tokens) as cache_write,
                SUM(reasoning_tokens) as reasoning,
                SUM(estimated_cost_usd) as est_cost,
                COUNT(DISTINCT session_id) as sessions,
                MAX(last_seen) as last_seen
            FROM session_model_usage
            GROUP BY model, billing_provider
        """)
        usage_rows = [dict(r) for r in cur.fetchall()]

        # Top sessions by cost/tokens
        cur.execute("""
            SELECT 
                s.id as session_id,
                s.title,
                s.last_activity_description,
                smu.model,
                smu.billing_provider,
                SUM(smu.api_call_count) as calls,
                SUM(smu.input_tokens) as inp,
                SUM(smu.output_tokens) as out,
                SUM(smu.estimated_cost_usd) as est_cost,
                s.last_activity_at
            FROM session_model_usage smu
            LEFT JOIN sessions s ON s.id = smu.session_id
            GROUP BY smu.session_id
            ORDER BY SUM(smu.input_tokens) + SUM(smu.output_tokens) DESC
            LIMIT 5
        """)
        top_sessions = [dict(r) for r in cur.fetchall()]

        conn.close()
        return {"profile": profile, "usage": usage_rows, "top_sessions": top_sessions}
    except Exception as e:
        return {"profile": profile, "error": str(e)}


def parse_log_tail(profile: str, lines: int = 500) -> list[dict]:
    """Parse recent API call lines from a profile's agent.log."""
    # Default profile log lives at ~/.hermes/logs/agent.log
    if profile == "default":
        log_path = HOME / ".hermes" / "logs" / "agent.log"
    else:
        log_path = PROFILES_DIR / profile / "logs" / "agent.log"
    if not log_path.exists():
        return []
    calls = []
    try:
        content = log_path.read_text(errors="replace")
        # tail last N lines
        all_lines = content.splitlines()
        for line in all_lines[-lines:]:
            m = LOG_RE.search(line)
            if m:
                calls.append({
                    "ts": m.group("ts"),
                    "profile": profile,
                    "session_id": m.group("session"),
                    "model": m.group("model"),
                    "provider": m.group("provider"),
                    "input_tokens": int(m.group("inp")),
                    "output_tokens": int(m.group("out")),
                    "total_tokens": int(m.group("total")),
                    "latency_s": float(m.group("lat")),
                })
    except Exception:
        pass
    return calls


# ─── Main probe ────────────────────────────────────────────────────────────────
def run_probe(full: bool = False, live_only: bool = False, fetch_or_activity: bool = False) -> dict[str, Any]:
    env = load_env()
    OR_KEY = env.get("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
    OR_MGMT_KEY = env.get("OPENROUTER_MANAGEMENT_KEY", os.environ.get("OPENROUTER_MANAGEMENT_KEY", ""))
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── OpenRouter live balance ──────────────────────────────────────────────
    or_balance: dict[str, Any] = {}
    or_credits: dict[str, Any] = {}
    or_activity: dict[str, Any] = {}
    if OR_KEY and not live_only:
        key_data = or_fetch(OR_KEY, "auth/key")
        credits_data = or_fetch(OR_KEY, "credits")
        if "data" in key_data:
            d = key_data["data"]
            or_balance = {
                "limit": d.get("limit"),
                "limit_remaining": d.get("limit_remaining"),
                "usage": d.get("usage"),
                "usage_daily": d.get("usage_daily"),
                "usage_weekly": d.get("usage_weekly"),
                "usage_monthly": d.get("usage_monthly"),
                "is_free_tier": d.get("is_free_tier"),
                "expires_at": d.get("expires_at"),
                "is_management_key": d.get("is_management_key"),
                "label": (d.get("label", "") or "")[:12] + "...",
            }
        else:
            or_balance = key_data
        if "data" in credits_data:
            d = credits_data["data"]
            or_credits = {
                "total_credits": d.get("total_credits"),
                "total_usage": d.get("total_usage"),
            }
        else:
            or_credits = credits_data

    # ── OpenRouter activity (management key only) ────────────────────────────
    if fetch_or_activity and not live_only:
        if OR_MGMT_KEY:
            activity_data = or_fetch(OR_MGMT_KEY, "activity?limit=100")
            if "data" in activity_data:
                entries = activity_data["data"]
                # Compact: keep only the fields we care about
                compact = []
                for e in (entries if isinstance(entries, list) else []):
                    compact.append({
                        "id": e.get("id"),
                        "created_at": e.get("created_at"),
                        "model": e.get("model"),
                        "provider": e.get("provider"),
                        "total_cost": e.get("total_cost"),
                        "prompt_tokens": e.get("prompt_tokens"),
                        "completion_tokens": e.get("completion_tokens"),
                        "native_tokens_prompt": e.get("native_tokens_prompt"),
                        "native_tokens_completion": e.get("native_tokens_completion"),
                        "latency": e.get("latency"),
                        "finish_reason": e.get("finish_reason"),
                        "app_id": e.get("app_id"),
                    })
                # Aggregate by model
                by_model_or: dict[str, dict] = {}
                total_or_cost = 0.0
                for e in compact:
                    m = e.get("model") or "unknown"
                    cost = float(e.get("total_cost") or 0)
                    ptok = int(e.get("prompt_tokens") or 0)
                    ctok = int(e.get("completion_tokens") or 0)
                    total_or_cost += cost
                    if m not in by_model_or:
                        by_model_or[m] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0.0}
                    by_model_or[m]["calls"] += 1
                    by_model_or[m]["prompt_tokens"] += ptok
                    by_model_or[m]["completion_tokens"] += ctok
                    by_model_or[m]["total_cost"] += cost
                or_activity = {
                    "status": "ok",
                    "generation_count": len(compact),
                    "total_cost": total_or_cost,
                    "by_model": by_model_or,
                    "recent": compact[:20],
                }
            else:
                or_activity = {"status": "error", "detail": activity_data}
        else:
            or_activity = {
                "status": "unavailable",
                "detail": "OPENROUTER_MANAGEMENT_KEY not present in environment. "
                          "Per-generation logs require a management key from openrouter.ai/settings/keys. "
                          "Request one via Helm → LockBox to unlock this view.",
            }

    # ── Parse all profile DBs (including the default profile at ~/.hermes/state.db) ──
    dbs = sorted(glob.glob(str(PROFILES_DIR / "*/state.db")))
    default_db = HOME / ".hermes" / "state.db"
    if default_db.exists() and str(default_db) not in dbs:
        dbs = [str(default_db)] + dbs
    by_profile: dict[str, Any] = {}
    by_model: dict[str, Any] = {}
    by_provider: dict[str, Any] = {}
    all_top_sessions: list[dict] = []
    fleet_totals = dict(
        calls=0, inp=0, out=0, cache_read=0, cache_write=0,
        reasoning=0, est_cost=0.0, sessions=0
    )

    for db_path in dbs:
        if live_only:
            break
        result = read_profile_db(Path(db_path))
        profile = result["profile"]
        if "error" in result:
            by_profile[profile] = {"error": result["error"]}
            continue

        pt_calls = 0; pt_inp = 0; pt_out = 0; pt_cr = 0
        pt_cw = 0; pt_rs = 0; pt_ec = 0.0; pt_ss = 0
        pt_models: list[str] = []; pt_providers: list[str] = []
        for row in result["usage"]:
            model = row["model"]
            prov = row["billing_provider"]
            calls = int(row["calls"] or 0)
            inp = int(row["inp"] or 0)
            out = int(row["out"] or 0)
            cr = int(row["cache_read"] or 0)
            cw = int(row["cache_write"] or 0)
            rs = int(row["reasoning"] or 0)
            ec = float(row["est_cost"] or 0.0)
            ss = int(row["sessions"] or 0)

            # Profile totals
            pt_calls += calls; pt_inp += inp; pt_out += out
            pt_cr += cr; pt_cw += cw; pt_rs += rs; pt_ec += ec; pt_ss += ss
            if model not in pt_models:
                pt_models.append(model)
            if prov not in pt_providers:
                pt_providers.append(prov)

            # Fleet totals
            fleet_totals["calls"] += calls
            fleet_totals["inp"] += inp
            fleet_totals["out"] += out
            fleet_totals["cache_read"] += cr
            fleet_totals["cache_write"] += cw
            fleet_totals["reasoning"] += rs
            fleet_totals["est_cost"] += ec
            fleet_totals["sessions"] += ss

            # By model
            if model not in by_model:
                by_model[model] = dict(calls=0, inp=0, out=0, cache_read=0, cache_write=0, reasoning=0, est_cost=0.0)
            by_model[model]["calls"] += calls
            by_model[model]["inp"] += inp
            by_model[model]["out"] += out
            by_model[model]["cache_read"] += cr
            by_model[model]["cache_write"] += cw
            by_model[model]["reasoning"] += rs
            by_model[model]["est_cost"] += ec

            # By provider
            if prov not in by_provider:
                by_provider[prov] = dict(calls=0, inp=0, out=0, est_cost=0.0)
            by_provider[prov]["calls"] += calls
            by_provider[prov]["inp"] += inp
            by_provider[prov]["out"] += out
            by_provider[prov]["est_cost"] += ec

        by_profile[profile] = {
            "calls": pt_calls, "inp": pt_inp, "out": pt_out,
            "cache_read": pt_cr, "cache_write": pt_cw, "reasoning": pt_rs,
            "est_cost": pt_ec, "sessions": pt_ss,
            "models": pt_models, "providers": pt_providers,
        }

        # Top sessions
        for sess in result["top_sessions"]:
            sess["profile"] = profile
            all_top_sessions.append(sess)

    # Sort top sessions by token count
    all_top_sessions.sort(
        key=lambda x: (x.get("inp") or 0) + (x.get("out") or 0),
        reverse=True,
    )

    # ── Parse live log calls ────────────────────────────────────────────────
    all_live_calls: list[dict] = []
    for db_path in dbs:
        parent_name = Path(db_path).parent.name
        profile = "default" if parent_name == ".hermes" else parent_name
        all_live_calls.extend(parse_log_tail(profile, lines=200))
    # Sort by ts desc, keep top 50
    all_live_calls.sort(key=lambda x: x["ts"], reverse=True)
    live_calls = all_live_calls[:50]

    # ── Threshold check ──────────────────────────────────────────────────────
    usage_daily = or_balance.get("usage_daily") or 0.0
    try:
        usage_daily = float(usage_daily)
    except (TypeError, ValueError):
        usage_daily = 0.0

    halt = False
    soft_hit = False
    halt_reason = None
    if usage_daily >= HARD_DAILY:
        halt = True
        halt_reason = f"OR daily hard cap: ${usage_daily:.2f} >= ${HARD_DAILY:.2f}"
    elif usage_daily >= SOFT_DAILY:
        soft_hit = True
        halt_reason = f"OR daily soft cap: ${usage_daily:.2f} >= ${SOFT_DAILY:.2f}"

    # ── Assemble output ──────────────────────────────────────────────────────
    snapshot = {
        "ts": ts,
        "or_balance": or_balance,
        "or_credits": or_credits,
        "or_activity": or_activity,
        "thresholds": {
            "soft_daily": SOFT_DAILY,
            "hard_daily": HARD_DAILY,
            "usage_daily": usage_daily,
            "soft_hit": soft_hit,
            "halt": halt,
            "halt_reason": halt_reason,
        },
        "fleet_totals": fleet_totals,
        "by_profile": by_profile,
        "by_model": by_model,
        "by_provider": by_provider,
        "top_sessions": all_top_sessions[:20],
        "live_calls": live_calls,
    }
    if full:
        snapshot["_full"] = True

    return snapshot


def write_snapshot(snapshot: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, default=str) + "\n")

    # Rolling daily log
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    daily_log = OUT_DIR / f"ledger-{today}.jsonl"
    with open(daily_log, "a") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")

    return SNAPSHOT_PATH


def print_summary(snapshot: dict) -> None:
    """Print a compact human-readable summary to stdout."""
    bal = snapshot.get("or_balance", {})
    tot = snapshot.get("fleet_totals", {})
    thresh = snapshot.get("thresholds", {})

    print(f"=== Ledger Probe {snapshot['ts']} ===")
    print(f"OpenRouter: ${bal.get('usage_daily', '?'):.2f} used today / ${bal.get('limit', '?'):.2f} limit  "
          f"(remaining: ${bal.get('limit_remaining', '?'):.2f})")
    print(f"Fleet (Hermes estimate): {tot.get('calls', 0)} API calls, "
          f"{(tot.get('inp',0)+tot.get('out',0)):,} tokens, "
          f"${tot.get('est_cost', 0):.4f} est cost")
    print(f"Cap status: {'⛔ HALT' if thresh.get('halt') else '⚠️ SOFT' if thresh.get('soft_hit') else '✅ OK'}")

    print("\nBy profile (top 5 by inp+out tokens):")
    profiles = snapshot.get("by_profile", {})
    sorted_profiles = sorted(
        profiles.items(),
        key=lambda kv: (kv[1].get("inp", 0) or 0) + (kv[1].get("out", 0) or 0),
        reverse=True,
    )
    for name, data in sorted_profiles[:5]:
        if isinstance(data, dict) and "error" not in data:
            print(f"  {name:25s} | {data.get('calls',0):4d} calls | "
                  f"{(data.get('inp',0)+data.get('out',0)):>10,} tok | "
                  f"${data.get('est_cost',0):>6.4f}")

    print("\nBy model:")
    for model, data in sorted(snapshot.get("by_model", {}).items(),
                               key=lambda kv: kv[1].get("inp", 0) + kv[1].get("out", 0),
                               reverse=True):
        print(f"  {model:40s} | {(data.get('inp',0)+data.get('out',0)):>10,} tok | ${data.get('est_cost',0):.4f}")

    live = snapshot.get("live_calls", [])
    if live:
        print(f"\nLive log (last {len(live)} API calls):")
        for c in live[:8]:
            print(f"  {c['ts']} [{c['profile']:20s}] {c['model']}: "
                  f"in={c['input_tokens']:,} out={c['output_tokens']:,} lat={c['latency_s']:.1f}s")

    reason = thresh.get("halt_reason")
    if reason:
        print(f"\n⚠️  {reason}")

    # OR activity block
    act = snapshot.get("or_activity", {})
    if act:
        status = act.get("status", "")
        if status == "ok":
            print(f"\nOR per-generation activity ({act.get('generation_count', 0)} calls, ${act.get('total_cost', 0):.4f} total):")
            for model, d in sorted(act.get("by_model", {}).items(), key=lambda x: x[1].get("total_cost", 0), reverse=True):
                print(f"  {model:40s} | {d['calls']} calls | "
                      f"{d['prompt_tokens']+d['completion_tokens']:,} tok | ${d['total_cost']:.4f}")
        elif status == "unavailable":
            print(f"\n⚠️  OR activity logs unavailable — management key not present.")
            print(f"   Add OPENROUTER_MANAGEMENT_KEY to ~/.hermes/.env to unlock per-generation detail.")
        elif status == "error":
            print(f"\n⚠️  OR activity fetch error: {act.get('detail')}")


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ledger Probe")
    parser.add_argument("--full", action="store_true", help="Include per-session detail")
    parser.add_argument("--live", action="store_true", help="Log tail only (fast, no DB)")
    parser.add_argument("--or-activity", action="store_true", help="Fetch OR per-generation logs (needs OPENROUTER_MANAGEMENT_KEY)")
    parser.add_argument("--quiet", action="store_true", help="No stdout (write only)")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    snapshot = run_probe(full=args.full, live_only=args.live, fetch_or_activity=args.or_activity)
    path = write_snapshot(snapshot)

    if args.json_out:
        print(json.dumps(snapshot, indent=2, default=str))
    elif not args.quiet:
        print_summary(snapshot)
        print(f"\nSnapshot written → {path}")

    # Exit code signals for heartbeat script
    thresh = snapshot.get("thresholds", {})
    if thresh.get("halt"):
        sys.exit(3)
    elif thresh.get("soft_hit"):
        sys.exit(2)
    else:
        sys.exit(0)

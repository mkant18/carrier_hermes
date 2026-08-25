#!/usr/bin/env python3
"""
Ledger Inspector — prompt-to-model-to-cost drill-down
======================================================
Maps every user prompt in a session to the exact model that handled it,
the cost, and (with --explain) WHY that model was used vs what was configured.

Usage:
  python3 ledger_inspect.py                          # list recent sessions
  python3 ledger_inspect.py --session SESSION_ID     # drill into one session
  python3 ledger_inspect.py --session SESSION_ID --explain   # + why each model

  python3 ledger_inspect.py --profile api_watcher   # specific bot profile
  python3 ledger_inspect.py --all-profiles           # search all profiles
  python3 ledger_inspect.py --today                  # sessions from today only
  python3 ledger_inspect.py --limit 20               # how many sessions to list

Data sources:
  ~/.hermes/state.db (default profile)
  ~/.hermes/profiles/<name>/state.db
  ~/.hermes/logs/agent.log  /  ~/.hermes/profiles/<name>/logs/agent.log
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
PROFILES_DIR = HERMES_HOME / "profiles"

# ── Log parsing patterns ───────────────────────────────────────────────────────
API_CALL_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO "
    r"\[(?P<session>[^\]]+)\] agent\.conversation_loop: "
    r"API call #(?P<call_n>\d+): model=(?P<model>\S+) provider=(?P<provider>\S+) "
    r"in=(?P<inp>\d+) out=(?P<out>\d+) total=(?P<total>\d+) latency=(?P<lat>[0-9.]+)s"
    r"(?:.*cache=(?P<cache>[^\s,]+))?"
)
FALLBACK_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO "
    r"\[(?P<session>[^\]]+)\] agent\.chat_completion_helpers: "
    r"Fallback activated: (?P<from_m>\S+) → (?P<to_m>\S+)"
)
FALLBACK_REASON_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (?:WARNING|INFO) "
    r"\[(?P<session>[^\]]+)\] agent\.[^:]+: "
    r"API call failed.*error_type=(?P<etype>[^\s]+).*summary=(?P<summary>.+)$"
)
FALLBACK_INITIATE_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO "
    r"\[(?P<session>[^\]]+)\] agent\.chat_completion_helpers: "
    r"Fallback to (?P<to_m>[^:]+): (?P<reason>.+)$"
)


def get_db_path(profile: str | None) -> Path:
    if profile is None or profile == "default":
        return HERMES_HOME / "state.db"
    return PROFILES_DIR / profile / "state.db"


def get_log_path(profile: str | None) -> Path:
    if profile is None or profile == "default":
        return HERMES_HOME / "logs" / "agent.log"
    return PROFILES_DIR / profile / "logs" / "agent.log"


def all_profile_dbs() -> list[tuple[str, Path]]:
    """Return (profile_name, db_path) for all profiles including default."""
    result = [("default", HERMES_HOME / "state.db")]
    for d in sorted(PROFILES_DIR.iterdir()):
        db = d / "state.db"
        if db.exists():
            result.append((d.name, db))
    return result


def ts_to_human(ts: float | None) -> str:
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def cost_str(usd: float | None) -> str:
    if usd is None or usd == 0:
        return "$0.00"
    if usd < 0.001:
        return f"${usd:.5f}"
    return f"${usd:.4f}"


# ── Log parsing ────────────────────────────────────────────────────────────────
def parse_log_for_session(log_path: Path, session_id: str) -> dict[str, Any]:
    """
    Parse agent.log for a specific session.
    Returns:
      api_calls: list of {call_n, model, provider, inp, out, lat, ts}
      fallbacks: list of {ts, from_m, to_m}
      fallback_reasons: list of {ts, error_type, summary} — the failure that triggered fallback
    """
    result: dict[str, Any] = {"api_calls": [], "fallbacks": [], "fallback_reasons": []}
    if not log_path.exists():
        return result

    # Buffer lines for context (pre-fallback failure messages)
    pending_failure: dict | None = None

    with open(log_path, "r", errors="replace") as f:
        for line in f:
            line = line.rstrip()

            # API call success line
            m = API_CALL_RE.search(line)
            if m and m.group("session") == session_id:
                result["api_calls"].append({
                    "call_n": int(m.group("call_n")),
                    "model": m.group("model"),
                    "provider": m.group("provider"),
                    "inp": int(m.group("inp")),
                    "out": int(m.group("out")),
                    "total": int(m.group("total")),
                    "lat": float(m.group("lat")),
                    "ts": m.group("ts"),
                })
                continue

            # Fallback reason (API call failed — the trigger)
            m2 = FALLBACK_REASON_RE.search(line)
            if m2 and m2.group("session") == session_id:
                pending_failure = {
                    "ts": m2.group("ts"),
                    "error_type": m2.group("etype"),
                    "summary": m2.group("summary").strip()[:200],
                }
                result["fallback_reasons"].append(pending_failure)
                continue

            # Fallback initiation — "clearing primary credential pool" style
            m3 = FALLBACK_INITIATE_RE.search(line)
            if m3 and m3.group("session") == session_id:
                # attach to most recent pending failure if any
                if pending_failure:
                    pending_failure["initiate_reason"] = m3.group("reason").strip()
                continue

            # Fallback activated
            m4 = FALLBACK_RE.search(line)
            if m4 and m4.group("session") == session_id:
                entry = {
                    "ts": m4.group("ts"),
                    "from_m": m4.group("from_m"),
                    "to_m": m4.group("to_m"),
                }
                if pending_failure:
                    entry["trigger"] = pending_failure
                    pending_failure = None
                result["fallbacks"].append(entry)
                continue

    return result


# ── DB queries ─────────────────────────────────────────────────────────────────
def list_sessions(db_path: Path, profile: str, limit: int = 20, today_only: bool = False) -> list[dict]:
    """Return recent sessions with cost + model info."""
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path), timeout=5)
    con.row_factory = sqlite3.Row
    where = ""
    if today_only:
        # today midnight UTC in epoch
        today_start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        where = f"WHERE s.started_at >= {today_start}"
    rows = con.execute(f"""
        SELECT
            s.id,
            s.title,
            s.model,
            s.model_config,
            s.billing_provider,
            s.estimated_cost_usd,
            s.actual_cost_usd,
            s.cost_status,
            s.api_call_count,
            s.message_count,
            s.started_at,
            s.last_activity_at,
            GROUP_CONCAT(u.model || '|' || u.billing_provider || '|' || COALESCE(u.estimated_cost_usd,0), ';;') AS usage_summary
        FROM sessions s
        LEFT JOIN session_model_usage u ON u.session_id = s.id
        {where}
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    con.close()
    result = []
    for r in rows:
        result.append({
            "profile": profile,
            "session_id": r["id"],
            "title": r["title"] or "(untitled)",
            "model_configured": r["model"],
            "model_config": r["model_config"],
            "billing_provider": r["billing_provider"],
            "estimated_cost_usd": r["estimated_cost_usd"],
            "actual_cost_usd": r["actual_cost_usd"],
            "cost_status": r["cost_status"],
            "api_call_count": r["api_call_count"],
            "message_count": r["message_count"],
            "started_at": r["started_at"],
            "last_activity_at": r["last_activity_at"],
            "usage_summary": r["usage_summary"],
        })
    return result


def get_session_messages(db_path: Path, session_id: str) -> list[dict]:
    """Return all messages for a session in order."""
    con = sqlite3.connect(str(db_path), timeout=5)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT id, role, content, tool_calls, tool_name, timestamp, token_count, finish_reason
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
    """, (session_id,)).fetchall()
    con.close()
    result = []
    for r in rows:
        content = r["content"]
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        result.append({
            "id": r["id"],
            "role": r["role"],
            "content": content or "",
            "tool_calls": r["tool_calls"],
            "tool_name": r["tool_name"],
            "timestamp": r["timestamp"],
            "token_count": r["token_count"],
            "finish_reason": r["finish_reason"],
        })
    return result


def get_session_model_usage(db_path: Path, session_id: str) -> list[dict]:
    con = sqlite3.connect(str(db_path), timeout=5)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT model, billing_provider, billing_base_url, task,
               api_call_count, input_tokens, output_tokens, cache_read_tokens,
               estimated_cost_usd, actual_cost_usd, cost_status, first_seen, last_seen
        FROM session_model_usage
        WHERE session_id = ?
        ORDER BY first_seen ASC
    """, (session_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_session_meta(db_path: Path, session_id: str) -> dict | None:
    con = sqlite3.connect(str(db_path), timeout=5)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    con.close()
    return dict(row) if row else None


# ── Mapping: user turns → API calls ───────────────────────────────────────────
def map_prompts_to_calls(messages: list[dict], api_calls: list[dict]) -> list[dict]:
    """
    Heuristic: pair user turns with api calls in order.
    Each user message triggers an API call to get an assistant response.
    We pair them positionally (user turn N → api_call N).
    Returns list of {prompt_preview, model, provider, inp, out, lat, call_n}
    """
    user_turns = [m for m in messages if m["role"] == "user"]
    result = []
    for i, (turn, call) in enumerate(zip(user_turns, api_calls)):
        content = turn["content"]
        # Handle JSON-encoded content (tool results etc.)
        preview = ""
        if content.startswith("[") or content.startswith("{"):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and item.get("type") == "text":
                            preview = item.get("text", "")[:300]
                            break
                    if not preview:
                        preview = str(parsed)[:300]
                else:
                    preview = str(parsed)[:300]
            except Exception:
                preview = content[:300]
        else:
            preview = content[:300]
        preview = preview.replace("\n", " ").strip()

        result.append({
            "turn_index": i + 1,
            "prompt_preview": preview,
            "prompt_full_id": turn["id"],
            "prompt_ts": turn["timestamp"],
            "call_n": call.get("call_n"),
            "model": call.get("model"),
            "provider": call.get("provider"),
            "inp": call.get("inp"),
            "out": call.get("out"),
            "lat": call.get("lat"),
            "call_ts": call.get("ts"),
        })

    # If more user turns than api calls (e.g. in-flight session), mark remainder
    for i in range(len(api_calls), len(user_turns)):
        turn = user_turns[i]
        content = turn["content"]
        preview = (content[:300]).replace("\n", " ").strip()
        result.append({
            "turn_index": i + 1,
            "prompt_preview": preview,
            "prompt_full_id": turn["id"],
            "prompt_ts": turn["timestamp"],
            "call_n": None,
            "model": "?? (no api call recorded)",
            "provider": None,
            "inp": None,
            "out": None,
            "lat": None,
            "call_ts": None,
        })

    return result


# ── Display helpers ────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
MAGENTA = "\033[95m"

def bar(char="─", width=80) -> str:
    return char * width

def print_session_list(sessions: list[dict]) -> None:
    print(f"\n{BOLD}{'PROFILE':<14} {'SESSION ID':<26} {'TITLE':<38} {'MODEL (configured)':<30} {'COST':<10} {'CALLS'}{RESET}")
    print(bar())
    for s in sessions:
        title = (s["title"] or "")[:37]
        model = (s["model_configured"] or "")[:29]
        cost_val = s["actual_cost_usd"] or s["estimated_cost_usd"] or 0
        cost_flag = "~" if s["cost_status"] == "estimated" else " "
        calls = s["api_call_count"] or 0
        profile = s["profile"][:13]
        session_id = s["session_id"][:25]
        print(f"{CYAN}{profile:<14}{RESET} {DIM}{session_id:<26}{RESET} {title:<38} {YELLOW}{model:<30}{RESET} {cost_flag}{cost_str(cost_val):<9} {calls}")

    print(bar())
    print(f"\n{DIM}Tip: drill in with  python3 ledger_inspect.py --session SESSION_ID{RESET}")
    print(f"{DIM}     add --explain to see why each model was chosen{RESET}\n")


def print_session_detail(
    meta: dict,
    usage: list[dict],
    mapped: list[dict],
    log_data: dict,
    profile: str,
    explain: bool,
) -> None:
    session_id = meta["id"]
    configured_model = meta.get("model") or "?"
    model_config = meta.get("model_config") or ""

    print(f"\n{bar('═')}")
    print(f"{BOLD}SESSION: {session_id}  [{profile}]{RESET}")
    print(f"  Title:      {meta.get('title') or '(untitled)'}")
    print(f"  Started:    {ts_to_human(meta.get('started_at'))}")
    print(f"  Configured: {YELLOW}{configured_model}{RESET}  (model_config: {model_config[:80]})")
    print(f"  API calls:  {meta.get('api_call_count') or 0}   Messages: {meta.get('message_count') or 0}")

    # Model usage summary
    total_cost = sum(u.get("estimated_cost_usd") or 0 for u in usage)
    print(f"\n{BOLD}Model usage breakdown:{RESET}")
    for u in usage:
        task_tag = f"  [{u['task']}]" if u.get("task") else ""
        cost_v = u.get("estimated_cost_usd") or 0
        cost_s = u.get("cost_status") or "?"
        print(f"  {YELLOW}{u['model']}{RESET} via {u['billing_provider']}{task_tag}")
        print(f"    calls={u['api_call_count']}  in={u['input_tokens']}  out={u['output_tokens']}  "
              f"cache_read={u['cache_read_tokens']}  cost={cost_str(cost_v)} ({cost_s})")
    print(f"  {BOLD}TOTAL ESTIMATED: {cost_str(total_cost)}{RESET}")

    # Fallback summary if any
    if log_data.get("fallbacks"):
        print(f"\n{RED}{BOLD}⚡ Fallbacks detected in this session:{RESET}")
        for fb in log_data["fallbacks"]:
            print(f"  {fb.get('ts','')}  {RED}{fb['from_m']}{RESET} → {GREEN}{fb['to_m']}{RESET}")
            if explain and fb.get("trigger"):
                t = fb["trigger"]
                print(f"    Trigger: {t.get('error_type','?')} — {t.get('summary','?')}")
                if t.get("initiate_reason"):
                    print(f"    Detail:  {t['initiate_reason']}")

    # Per-prompt mapping
    print(f"\n{bar()}")
    print(f"{BOLD}PROMPT → MODEL → COST MAP{RESET}  (each user turn paired with its API call)")
    print(bar())

    if not mapped:
        print("  (No user turns found in messages table)")
    else:
        for entry in mapped:
            model_display = entry.get("model") or "?"
            provider_display = entry.get("provider") or ""
            inp = entry.get("inp")
            out = entry.get("out")
            lat = entry.get("lat")
            call_n = entry.get("call_n")
            prompt = entry.get("prompt_preview") or ""
            prompt_display = prompt[:120] + ("…" if len(prompt) > 120 else "")

            call_info = f"call #{call_n}" if call_n else "no call recorded"
            token_info = f"in={inp} out={out}" if inp is not None else ""
            lat_info = f"{lat:.1f}s" if lat else ""

            print(f"\n  {BOLD}[Turn {entry['turn_index']}]{RESET}  {DIM}{call_info}  {ts_to_human(entry.get('prompt_ts'))}{RESET}")
            print(f"  {CYAN}Prompt:{RESET} {prompt_display}")
            print(f"  {YELLOW}Model:{RESET}  {model_display}  ({provider_display})  {token_info}  {lat_info}")

            # Is this model different from the configured one? Highlight it.
            if model_display and configured_model and model_display != configured_model:
                print(f"  {RED}⚡ MISMATCH: configured={configured_model}, actual={model_display}{RESET}", end="")
                if explain:
                    # Find relevant fallback for this call
                    relevant = [fb for fb in log_data.get("fallbacks", []) if fb.get("to_m") == model_display]
                    if relevant:
                        fb = relevant[0]
                        print(f"\n  {BOLD}  WHY:{RESET} Fallback from {fb.get('from_m')} triggered at {fb.get('ts','?')}", end="")
                        if fb.get("trigger"):
                            t = fb["trigger"]
                            print(f"\n  {BOLD}  CAUSE:{RESET} {t.get('error_type','?')} — {t.get('summary','?')}", end="")
                    else:
                        print(f"\n  {DIM}  (run with --explain for fallback reason from agent.log){RESET}", end="")
                print()
            else:
                print(f"  {GREEN}✓ matches configured model{RESET}")

    print(f"\n{bar('═')}\n")
    if not explain:
        print(f"{DIM}Add --explain to see WHY each model was used (parses agent.log for fallback reasons){RESET}\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", "-s", help="Session ID to drill into")
    parser.add_argument("--profile", "-p", default=None, help="Bot profile name (default = your main session)")
    parser.add_argument("--all-profiles", action="store_true", help="List sessions across ALL profiles")
    parser.add_argument("--today", action="store_true", help="Only show sessions from today")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max sessions to list (default 20)")
    parser.add_argument("--explain", action="store_true", help="Show WHY each model was used (parses agent.log)")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Output JSON instead of pretty print")
    args = parser.parse_args()

    if args.session:
        # Drill-down mode: find which profile has this session
        profile = args.profile
        db_path = get_db_path(profile)
        meta = None

        if not profile:
            # Search all profiles for this session ID
            for pname, p in all_profile_dbs():
                if p.exists():
                    m = get_session_meta(p, args.session)
                    if m:
                        meta = m
                        db_path = p
                        profile = pname
                        break
            if not meta:
                print(f"Session {args.session!r} not found in any profile DB.", file=sys.stderr)
                sys.exit(1)
        else:
            meta = get_session_meta(db_path, args.session)
            if not meta:
                print(f"Session {args.session!r} not found in profile {profile!r}.", file=sys.stderr)
                sys.exit(1)

        usage = get_session_model_usage(db_path, args.session)
        messages = get_session_messages(db_path, args.session)
        log_path = get_log_path(profile)
        log_data = parse_log_for_session(log_path, args.session)
        mapped = map_prompts_to_calls(messages, log_data["api_calls"])

        if args.json_out:
            print(json.dumps({
                "session_id": args.session,
                "profile": profile,
                "meta": {k: meta.get(k) for k in ("id","title","model","model_config","estimated_cost_usd","api_call_count")},
                "model_usage": usage,
                "prompt_to_model_map": mapped,
                "fallbacks": log_data.get("fallbacks"),
                "fallback_reasons": log_data.get("fallback_reasons"),
            }, indent=2, default=str))
        else:
            print_session_detail(meta, usage, mapped, log_data, profile or "default", args.explain)

    else:
        # Listing mode
        if args.all_profiles:
            all_sessions = []
            for pname, p in all_profile_dbs():
                all_sessions.extend(list_sessions(p, pname, limit=args.limit, today_only=args.today))
            all_sessions.sort(key=lambda s: s.get("started_at") or 0, reverse=True)
            sessions = all_sessions[:args.limit]
        else:
            profile = args.profile or "default"
            db_path = get_db_path(profile if profile != "default" else None)
            sessions = list_sessions(db_path, profile, limit=args.limit, today_only=args.today)

        if args.json_out:
            print(json.dumps(sessions, indent=2, default=str))
        else:
            print_session_list(sessions)


if __name__ == "__main__":
    main()

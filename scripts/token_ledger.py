#!/usr/bin/env python3
"""token_ledger.py — daily OAuth token usage ledger + OR cost estimator.

Scans all OMB event NDJSON logs nightly. Extracts thread.token-usage.updated
events, maps each to its bot name and model, and SKIPS any turn on an
ollama::* model (local LLMs cost nothing and inflate the estimate).

Output:
  ~/.openmausbot/token_ledger/YYYY-MM-DD.json  — per-day detail (bot+model breakdown)
  ~/.openmausbot/token_ledger/ledger.csv        — rolling daily totals (append-only)
  ~/.openmausbot/token_ledger/ledger_summary.json — last-N-days summary + OR estimate

The --estimate-or flag projects total OAuth tokens at current OpenRouter
pricing for comparison (to help Michael decide if switching from OAuth
subscription → cheap OR models is worth it).

OR model prices used for estimation (per-million tokens, as of 2026-08):
  deepseek/deepseek-v4-flash-0731:  $0.07 input / $0.28 output
  google/gemini-flash-lite:         $0.10 input / $0.40 output
  meta-llama/llama-3.3-70b:        $0.39 input / $0.39 output

Usage:
    python token_ledger.py [--date YYYY-MM-DD] [--estimate-or] [--days N] [--summary]

ZERO-LLM. Safe from cron / no_agent contexts.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

OMB_DATA = Path.home() / ".openmausbot"
EVENTS_DIR = OMB_DATA / "events"
BOTS_FILE   = OMB_DATA / "bots.json"
LEDGER_DIR  = OMB_DATA / "token_ledger"
CSV_FILE    = LEDGER_DIR / "ledger.csv"
SUMMARY_FILE = LEDGER_DIR / "ledger_summary.json"

# OR model cost reference (USD per million tokens)
OR_MODELS = {
    "deepseek/deepseek-v4-flash-0731": {"input": 0.07,  "output": 0.28,  "label": "DeepSeek Flash"},
    "google/gemini-flash-lite":         {"input": 0.10,  "output": 0.40,  "label": "Gemini Flash Lite"},
    "meta-llama/llama-3.3-70b":         {"input": 0.39,  "output": 0.39,  "label": "Llama 3.3 70B"},
}

CSV_HEADERS = ["date", "input_tokens", "output_tokens", "total_tokens",
               "turns", "bots_active", "est_cost_deepseek_usd",
               "est_cost_gemini_lite_usd", "est_cost_llama70b_usd"]


def _load_bots() -> dict[str, dict]:
    """Map threadId -> bot info."""
    if not BOTS_FILE.exists():
        return {}
    try:
        bots = json.loads(BOTS_FILE.read_text(encoding="utf-8"))
        out = {}
        for b in bots:
            tid = b.get("threadId")
            if tid:
                out[tid] = {
                    "bot_id": b.get("id", ""),
                    "name": b.get("name", "?"),
                    "model": b.get("modelSelection", {}).get("model", "?"),
                    "instance_id": b.get("modelSelection", {}).get("instanceId", "?"),
                }
        return out
    except Exception:
        return {}


def _is_local(model: str) -> bool:
    """True if this model is a local Ollama model (zero cost)."""
    return model.startswith("ollama::") or "ollama" in model.lower()


def _parse_thread_events(path: Path, thread_info: dict,
                          date_str: str) -> list[dict]:
    """Extract token usage records for a given date from one thread's NDJSON."""
    records = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") != "thread.token-usage.updated":
            continue
        # Filter to the target date (UTC)
        created = e.get("createdAt", "")
        if not created.startswith(date_str):
            continue

        inp = e.get("input", 0) or 0
        out = e.get("output", 0) or 0
        if inp == 0 and out == 0:
            continue

        model = thread_info.get("model", "?")
        if _is_local(model):
            continue  # skip local LLM turns entirely

        records.append({
            "bot_id":      thread_info.get("bot_id", ""),
            "name":        thread_info.get("name", "?"),
            "instance_id": thread_info.get("instance_id", "?"),
            "model":       model,
            "input":       inp,
            "output":      out,
            "created_at":  created,
        })
    return records


def _or_estimate(input_tok: int, output_tok: int) -> dict[str, float]:
    """Estimate cost in USD at each OR model's rate."""
    out = {}
    for slug, pricing in OR_MODELS.items():
        cost = (input_tok / 1_000_000) * pricing["input"] + \
               (output_tok / 1_000_000) * pricing["output"]
        out[slug] = round(cost, 6)
    return out


def _build_day(date_str: str, bots_by_thread: dict[str, dict]) -> dict:
    """Aggregate all OAuth token usage for a UTC date string (YYYY-MM-DD)."""
    bot_breakdown: dict[str, dict] = {}  # name -> {input, output, turns}
    total_input = 0
    total_output = 0
    total_turns = 0

    if not EVENTS_DIR.exists():
        return _empty_day(date_str)

    for ndjson in EVENTS_DIR.glob("*.ndjson"):
        thread_id = ndjson.stem
        thread_info = bots_by_thread.get(thread_id, {
            "bot_id": "", "name": f"unknown({thread_id[:8]})",
            "model": "?", "instance_id": "?"
        })

        records = _parse_thread_events(ndjson, thread_info, date_str)
        for r in records:
            name = r["name"]
            if name not in bot_breakdown:
                bot_breakdown[name] = {"input": 0, "output": 0, "turns": 0,
                                        "model": r["model"], "instance_id": r["instance_id"]}
            bot_breakdown[name]["input"]  += r["input"]
            bot_breakdown[name]["output"] += r["output"]
            bot_breakdown[name]["turns"]  += 1
            total_input  += r["input"]
            total_output += r["output"]
            total_turns  += 1

    estimates = _or_estimate(total_input, total_output)

    return {
        "date": date_str,
        "generated_at": int(time.time()),
        "total_input_tokens":  total_input,
        "total_output_tokens": total_output,
        "total_tokens":        total_input + total_output,
        "oauth_turns":         total_turns,
        "bots_active":         len(bot_breakdown),
        "local_llm_excluded":  True,
        "or_estimates_usd":    estimates,
        "bot_breakdown":       bot_breakdown,
        "note": "ollama::* turns excluded — local LLMs cost $0 and would inflate OR estimates.",
    }


def _empty_day(date_str: str) -> dict:
    return {
        "date": date_str,
        "generated_at": int(time.time()),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "oauth_turns": 0,
        "bots_active": 0,
        "local_llm_excluded": True,
        "or_estimates_usd": {k: 0.0 for k in OR_MODELS},
        "bot_breakdown": {},
        "note": "No OAuth token usage found for this date.",
    }


def _append_csv(day: dict) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_FILE.exists()
    estimates = day["or_estimates_usd"]
    slugs = list(OR_MODELS.keys())
    row = [
        day["date"],
        day["total_input_tokens"],
        day["total_output_tokens"],
        day["total_tokens"],
        day["oauth_turns"],
        day["bots_active"],
        estimates.get(slugs[0], 0.0),
        estimates.get(slugs[1], 0.0),
        estimates.get(slugs[2], 0.0),
    ]
    with CSV_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_HEADERS)
        writer.writerow(row)


def _write_summary(days: int = 30) -> dict:
    """Read ledger.csv and write a rolling summary JSON."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    if CSV_FILE.exists():
        with CSV_FILE.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    rows = rows[-days:]  # last N days

    total_in  = sum(int(r.get("input_tokens",  0) or 0) for r in rows)
    total_out = sum(int(r.get("output_tokens", 0) or 0) for r in rows)
    total_tok = total_in + total_out

    def _col_sum(col: str) -> float:
        return round(sum(float(r.get(col, 0) or 0) for r in rows), 4)

    summary = {
        "generated_at": int(time.time()),
        "days_covered": len(rows),
        "date_range": f"{rows[0]['date']} to {rows[-1]['date']}" if rows else "n/a",
        "total_input_tokens":  total_in,
        "total_output_tokens": total_out,
        "total_tokens":        total_tok,
        "or_total_estimates_usd": {
            "deepseek_flash":   _col_sum("est_cost_deepseek_usd"),
            "gemini_flash_lite":_col_sum("est_cost_gemini_lite_usd"),
            "llama_3_3_70b":    _col_sum("est_cost_llama70b_usd"),
        },
        "per_million_rates": {
            slug: {"input": p["input"], "output": p["output"], "label": p["label"]}
            for slug, p in OR_MODELS.items()
        },
        "note": (
            "These are ESTIMATES for switching from OAuth subscription to OpenRouter. "
            "Actual spend depends on prompt structure. Local Ollama turns are excluded."
        ),
        "daily_rows": rows,
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None,
                    help="Target date YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--days", type=int, default=30,
                    help="Days of history for summary (default 30)")
    ap.add_argument("--estimate-or", action="store_true",
                    help="Print OR cost estimate table")
    ap.add_argument("--summary", action="store_true",
                    help="Print rolling summary only (no new scan)")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of human-readable output")
    args = ap.parse_args()

    if args.summary:
        summary = _write_summary(args.days)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            _print_summary(summary)
        return 0

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bots_by_thread = _load_bots()
    day = _build_day(date_str, bots_by_thread)

    # Save day detail
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    day_file = LEDGER_DIR / f"{date_str}.json"
    day_file.write_text(json.dumps(day, indent=2), encoding="utf-8")

    # Append/update CSV (deduplicate by date)
    _append_csv_dedup(day)

    summary = _write_summary(args.days)

    if args.json:
        print(json.dumps({"day": day, "summary": summary}, indent=2))
        return 0

    _print_day(day)
    if args.estimate_or:
        _print_or_table(day, summary)
    return 0


def _append_csv_dedup(day: dict) -> None:
    """Write or update today's row in the CSV (idempotent re-runs)."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    date = day["date"]
    estimates = day["or_estimates_usd"]
    slugs = list(OR_MODELS.keys())
    new_row = {
        "date": date,
        "input_tokens":               str(day["total_input_tokens"]),
        "output_tokens":              str(day["total_output_tokens"]),
        "total_tokens":               str(day["total_tokens"]),
        "turns":                      str(day["oauth_turns"]),
        "bots_active":                str(day["bots_active"]),
        "est_cost_deepseek_usd":      str(estimates.get(slugs[0], 0.0)),
        "est_cost_gemini_lite_usd":   str(estimates.get(slugs[1], 0.0)),
        "est_cost_llama70b_usd":      str(estimates.get(slugs[2], 0.0)),
    }

    rows: list[dict] = []
    if CSV_FILE.exists():
        with CSV_FILE.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    updated = False
    for i, r in enumerate(rows):
        if r.get("date") == date:
            rows[i] = new_row
            updated = True
            break
    if not updated:
        rows.append(new_row)

    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _print_day(day: dict) -> None:
    print(f"=== Token Ledger — {day['date']} (OAuth only, Ollama excluded) ===")
    print(f"  Input:  {day['total_input_tokens']:>10,} tokens")
    print(f"  Output: {day['total_output_tokens']:>10,} tokens")
    print(f"  Total:  {day['total_tokens']:>10,} tokens  ({day['oauth_turns']} turns, "
          f"{day['bots_active']} bots)")
    if day["bot_breakdown"]:
        print()
        print("  Per-bot breakdown:")
        breakdown = sorted(day["bot_breakdown"].items(),
                           key=lambda kv: kv[1]["input"] + kv[1]["output"], reverse=True)
        for name, b in breakdown:
            print(f"    {name:20s}  in={b['input']:>8,}  out={b['output']:>8,}  "
                  f"turns={b['turns']}  ({b['model'][:35]})")


def _print_or_table(day: dict, summary: dict) -> None:
    print()
    print("=== OR Cost Estimate (if these tokens were billed at OR rates) ===")
    print(f"  {'Model':<35}  {'Today':>10}  {str(summary['days_covered'])+'-day total':>12}")
    slugs = list(OR_MODELS.keys())
    summary_ests = summary["or_total_estimates_usd"]
    for slug, pricing in OR_MODELS.items():
        today_cost = day["or_estimates_usd"].get(slug, 0.0)
        total_cost = list(summary_ests.values())[list(OR_MODELS.keys()).index(slug)]
        print(f"  {pricing['label']:<35}  ${today_cost:>9.4f}  ${total_cost:>11.4f}")
    print()
    print("  Note: OAuth subscription cost is flat. OR saves money only if total")
    print("  OR spend < subscription cost. These numbers help you compare.")


def _print_summary(summary: dict) -> None:
    print(f"=== Token Ledger Summary — last {summary['days_covered']} days "
          f"({summary['date_range']}) ===")
    print(f"  Total tokens: {summary['total_tokens']:,}  "
          f"(in={summary['total_input_tokens']:,}  out={summary['total_output_tokens']:,})")
    print()
    print("  OR cost estimates (total period):")
    for key, cost in summary["or_total_estimates_usd"].items():
        label = key.replace("_", " ").title()
        print(f"    {label:<25}  ${cost:.4f}")


if __name__ == "__main__":
    import sys
    sys.exit(main())

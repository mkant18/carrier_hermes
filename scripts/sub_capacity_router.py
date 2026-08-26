#!/usr/bin/env python3
"""
Sub Capacity Router — Carrier Hermes (V1, ZERO-LLM)
=====================================================
Reads REMAINING CAPACITY for the two OAuth subscriptions the fleet shares
(Anthropic/Claude Max, xAI/SuperGrok) and emits a routing decision as a
single JSON object. Purely mechanical: no model calls, no inference, no
third-party dependencies. stdlib only.

Scope: subscription capacity ONLY. OpenRouter $ spend is owned by
scripts/ledger_probe.py — this script never touches it and never routes
to a paid API-key route. Output "provider" is always "anthropic" or
"xai-oauth".

# WIRING (V1 — observability only):
# 1. Call from Vigil's watcher_heartbeat.sh (no_agent bash) every 5m:
#    python3 scripts/sub_capacity_router.py --json >> _agent/watcher/sub_router.jsonl
# 2. Helm can call it during preflight to get the recommended provider.
# 3. V2 will have it flip `hermes config set model.provider` for the session.

Usage:
  python sub_capacity_router.py [--json] [--verbose]

Exit codes:
  0 = success (decision made, even if partially degraded)
  1 = error (both providers failed to probe AND local DB fallback failed
      for both; caller should fall back to its own default)

Env vars:
  SUB_ROUTER_WINDOW_DAYS          rolling window for local DB fallback (default 7)
  CLAUDE_MAX_7D_TOKEN_CEILING     conservative ceiling for Claude Max local-DB
                                  fallback (default 10_000_000)
  SUPERGROK_7D_TOKEN_CEILING      conservative ceiling for SuperGrok local-DB
                                  fallback (default 5_000_000)
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

# ─── Config ──────────────────────────────────────────────────────────────
HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / "AppData" / "Local" / "hermes"))
CARRIER_HOME = Path(os.environ.get("HERMES_CARRIER_HOME", HOME / ".hermes" / "carrier"))

CLAUDE_CREDS_PATH = HOME / ".claude" / ".credentials.json"
XAI_AUTH_PATH = HERMES_HOME / "auth.json"

PROFILES_DIR = HERMES_HOME / "profiles"
DEFAULT_STATE_DB = HERMES_HOME / "state.db"

DISPATCH_LOCK_PATH = CARRIER_HOME / "DISPATCH_LOCK"
SPEND_HALT_PATH = CARRIER_HOME / "SPEND_HALT"

ANTHROPIC_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
XAI_PROBE_URLS = [
    "https://api.x.ai/v1/api-key",
    "https://api.x.ai/v1/usage",
]

WINDOW_DAYS = float(os.environ.get("SUB_ROUTER_WINDOW_DAYS", "7"))
CLAUDE_MAX_7D_TOKEN_CEILING = int(os.environ.get("CLAUDE_MAX_7D_TOKEN_CEILING", "10000000"))
SUPERGROK_7D_TOKEN_CEILING = int(os.environ.get("SUPERGROK_7D_TOKEN_CEILING", "5000000"))

ALERT_THRESHOLD = 0.70
BLOCK_THRESHOLD = 0.90

HTTP_TIMEOUT_S = 10


# ─── Small helpers ──────────────────────────────────────────────────────
def _log(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"[sub_capacity_router] {msg}", file=sys.stderr)


def _http_get_json(url: str, headers: dict[str, str], timeout: int = HTTP_TIMEOUT_S) -> tuple[Optional[dict], Optional[str]]:
    """GET a URL and parse JSON. Returns (data, error). Never raises."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"
    except (TimeoutError, OSError) as e:
        return None, f"timeout/os-error: {e}"
    except json.JSONDecodeError as e:
        return None, f"bad JSON: {e}"
    except Exception as e:  # last-resort catch-all — never crash the router
        return None, f"unexpected: {e}"


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _provider_result(utilization: Optional[float], remaining_tokens: Optional[int], source: str) -> dict[str, Any]:
    util = None if utilization is None else round(_clamp01(utilization), 4)
    return {
        "utilization": util,
        "remaining_tokens": remaining_tokens,
        "source": source,
        "alert_70pct": bool(util is not None and util >= ALERT_THRESHOLD),
        "block_90pct": bool(util is not None and util >= BLOCK_THRESHOLD),
    }


def _unknown_result() -> dict[str, Any]:
    return _provider_result(None, None, "unknown")


# ─── Anthropic / Claude Max ─────────────────────────────────────────────
def read_claude_token(verbose: bool) -> Optional[str]:
    if not CLAUDE_CREDS_PATH.exists():
        _log(verbose, f"Claude credentials file not found: {CLAUDE_CREDS_PATH}")
        return None
    try:
        data = json.loads(CLAUDE_CREDS_PATH.read_text(encoding="utf-8"))
        token = (data.get("claudeAiOauth") or {}).get("accessToken")
        if not token:
            _log(verbose, "Claude credentials file present but accessToken missing")
            return None
        return token
    except Exception as e:
        _log(verbose, f"Failed to read/parse Claude credentials: {e}")
        return None


def probe_anthropic_oauth_usage(verbose: bool) -> Optional[dict[str, Any]]:
    """Probe the Anthropic OAuth usage endpoint. Returns raw parsed JSON or None."""
    token = read_claude_token(verbose)
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    }
    data, err = _http_get_json(ANTHROPIC_USAGE_URL, headers)
    if err:
        _log(verbose, f"Anthropic OAuth usage probe failed: {err}")
        return None
    return data


def get_anthropic_capacity(verbose: bool) -> dict[str, Any]:
    """Highest-priority source: live OAuth usage API. Falls back to local DB."""
    data = probe_anthropic_oauth_usage(verbose)
    if data:
        try:
            # Prefer the seven_day window (matches the ceilings/ARCHITECTURE framing);
            # fall back to five_hour if seven_day is absent.
            windows = data if isinstance(data, dict) else {}
            window = windows.get("seven_day") or windows.get("five_hour")
            if window and "utilization" in window and window["utilization"] is not None:
                util = float(window["utilization"])
                _log(verbose, f"Anthropic OAuth usage: utilization={util}")
                return _provider_result(util, None, "oauth_api")
        except Exception as e:
            _log(verbose, f"Failed to parse Anthropic OAuth usage response: {e}")

    # Fallback: local rolling token counter
    _log(verbose, "Anthropic: falling back to local DB rolling counter")
    return get_local_db_capacity("anthropic", CLAUDE_MAX_7D_TOKEN_CEILING, verbose)


# ─── xAI / SuperGrok ─────────────────────────────────────────────────────
def read_xai_token(verbose: bool) -> Optional[str]:
    if not XAI_AUTH_PATH.exists():
        _log(verbose, f"xAI auth file not found: {XAI_AUTH_PATH}")
        return None
    try:
        data = json.loads(XAI_AUTH_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _log(verbose, f"Failed to read/parse xAI auth.json: {e}")
        return None

    # Primary path: providers["xai-oauth"].tokens.access_token
    try:
        token = (
            (data.get("providers") or {}).get("xai-oauth", {}).get("tokens", {}).get("access_token")
        )
        if token:
            return token
    except Exception:
        pass

    # Fallback path: credential_pool["xai-oauth"][0].access_token
    try:
        pool = (data.get("credential_pool") or {}).get("xai-oauth") or []
        if pool and isinstance(pool, list):
            token = pool[0].get("access_token")
            if token:
                return token
    except Exception:
        pass

    _log(verbose, "xAI auth.json present but no access_token found in either known path")
    return None


def probe_xai_usage(verbose: bool) -> Optional[dict[str, Any]]:
    """xAI has no documented public quota endpoint. Probe known candidates and
    gracefully treat 404/403/anything-without-a-quota-field as unavailable.
    Never fabricate a result."""
    token = read_xai_token(verbose)
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    for url in XAI_PROBE_URLS:
        data, err = _http_get_json(url, headers)
        if err:
            _log(verbose, f"xAI probe {url} failed: {err}")
            continue
        if isinstance(data, dict):
            # Look for a plausible quota/utilization field. We do NOT invent
            # a schema — only accept it if something quota-shaped is present.
            for key in ("utilization", "usage_percent", "quota_utilization", "remaining", "remaining_tokens"):
                if key in data:
                    _log(verbose, f"xAI probe {url} returned quota-shaped field '{key}'")
                    return data
        _log(verbose, f"xAI probe {url} returned data with no recognizable quota field")
    return None


def get_xai_capacity(verbose: bool) -> dict[str, Any]:
    data = probe_xai_usage(verbose)
    if data:
        try:
            util = data.get("utilization")
            if util is None:
                util = data.get("usage_percent")
            if util is None:
                util = data.get("quota_utilization")
            remaining = data.get("remaining_tokens") or data.get("remaining")
            if util is not None:
                return _provider_result(float(util), remaining, "xai_api")
        except Exception as e:
            _log(verbose, f"Failed to parse xAI probe response: {e}")

    # Fallback: local rolling token counter
    _log(verbose, "xAI: no confirmed quota API — falling back to local DB rolling counter")
    return get_local_db_capacity("xai-oauth", SUPERGROK_7D_TOKEN_CEILING, verbose)


# ─── Local rolling token counter (shared fallback) ──────────────────────
def _iter_profile_dbs() -> list[Path]:
    dbs = [Path(p) for p in glob.glob(str(PROFILES_DIR / "*" / "state.db"))]
    if DEFAULT_STATE_DB.exists() and DEFAULT_STATE_DB not in dbs:
        dbs.append(DEFAULT_STATE_DB)
    return dbs


def get_local_db_capacity(billing_provider: str, ceiling: int, verbose: bool) -> dict[str, Any]:
    """Sum input_tokens + output_tokens across all profile DBs for a given
    billing_provider within the rolling window, and compare to a configured
    ceiling. Read-only; never writes."""
    cutoff_ts = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=WINDOW_DAYS)
    ).timestamp()

    total_tokens = 0
    found_any_row = False
    dbs = _iter_profile_dbs()
    if not dbs:
        _log(verbose, "No profile state.db files found for local-DB fallback")
        return _unknown_result()

    for db_path in dbs:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0)
                FROM session_model_usage
                WHERE billing_provider = ? AND last_seen >= ?
                """,
                (billing_provider, cutoff_ts),
            )
            row = cur.fetchone()
            conn.close()
            if row and row[0] is not None:
                total_tokens += int(row[0])
                found_any_row = True
        except Exception as e:
            _log(verbose, f"Local DB read failed for {db_path}: {e}")
            continue

    if not found_any_row:
        _log(verbose, f"No usable session_model_usage rows for provider={billing_provider}")
        return _unknown_result()

    if ceiling <= 0:
        _log(verbose, f"Ceiling for {billing_provider} is non-positive; cannot compute utilization")
        return _unknown_result()

    utilization = total_tokens / ceiling
    remaining = max(0, ceiling - total_tokens)
    _log(
        verbose,
        f"Local DB {billing_provider}: {total_tokens:,} tokens / {ceiling:,} ceiling "
        f"({WINDOW_DAYS:.0f}d window) => utilization={utilization:.4f}",
    )
    return _provider_result(utilization, remaining, "local_db")


# ─── Routing decision ────────────────────────────────────────────────────
def decide_route(anthropic: dict[str, Any], xai: dict[str, Any], verbose: bool) -> tuple[str, str]:
    """V1 routing logic (NO difficulty weighting, NO V2 logic):
      1. If only one provider is below 90%, choose it.
      2. If both below 90%, choose the one with LOWER utilization (more headroom).
      3. If both above 90% (or both unknown), choose "anthropic" as safe default.
    """
    a_util = anthropic.get("utilization")
    x_util = xai.get("utilization")
    a_blocked = bool(anthropic.get("block_90pct"))
    x_blocked = bool(xai.get("block_90pct"))

    a_known = a_util is not None
    x_known = x_util is not None

    if a_known and not a_blocked and (x_blocked or not x_known):
        reason = f"anthropic below 90% ({a_util:.1%}); xai-oauth blocked/unknown"
        return "anthropic", reason

    if x_known and not x_blocked and (a_blocked or not a_known):
        reason = f"xai-oauth below 90% ({x_util:.1%}); anthropic blocked/unknown"
        return "xai-oauth", reason

    if a_known and x_known and not a_blocked and not x_blocked:
        if a_util <= x_util:
            reason = f"both below 90%; anthropic has more headroom ({a_util:.1%} <= {x_util:.1%})"
            return "anthropic", reason
        else:
            reason = f"both below 90%; xai-oauth has more headroom ({x_util:.1%} < {a_util:.1%})"
            return "xai-oauth", reason

    # Both above 90%, or both unknown, or any other combination not covered above.
    reason = "both providers blocked/unknown; defaulting to anthropic (safe default)"
    return "anthropic", reason


# ─── Main ─────────────────────────────────────────────────────────────────
def run(verbose: bool) -> dict[str, Any]:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    anthropic_had_exception = False
    xai_had_exception = False

    try:
        anthropic = get_anthropic_capacity(verbose)
    except Exception as e:
        _log(verbose, f"UNRECOVERABLE anthropic probe exception: {e}")
        anthropic = _unknown_result()
        anthropic_had_exception = True

    try:
        xai = get_xai_capacity(verbose)
    except Exception as e:
        _log(verbose, f"UNRECOVERABLE xai probe exception: {e}")
        xai = _unknown_result()
        xai_had_exception = True

    provider, reason = decide_route(anthropic, xai, verbose)
    _log(verbose, f"Decision: {provider} — {reason}")

    result = {
        "provider": provider,
        "reason": reason,
        "anthropic": anthropic,
        "xai_oauth": xai,
        "dispatch_lock": DISPATCH_LOCK_PATH.exists(),
        "spend_halt": SPEND_HALT_PATH.exists(),
        "ts": ts,
    }
    # Signal to caller whether both probes were unrecoverable (exit-code decision).
    result["_both_unrecoverable"] = bool(anthropic_had_exception and xai_had_exception)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Zero-LLM subscription capacity router (Claude Max / SuperGrok)."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output (default behavior)")
    parser.add_argument("--verbose", action="store_true", help="Log decision reasoning to stderr")
    args = parser.parse_args()

    result = run(args.verbose)
    both_unrecoverable = result.pop("_both_unrecoverable", False)

    print(json.dumps(result))

    if both_unrecoverable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

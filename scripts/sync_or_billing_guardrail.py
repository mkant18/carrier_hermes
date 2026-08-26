#!/usr/bin/env python3
"""Push OpenRouter workspace Default guardrail to ALLOWLIST-only cheap models.

Strategy:
  - allowed_models = catalog intersection with Carrier cheap allowlist
  - ignored_models = all valid catalog Claude/Grok/expensive IDs (no ~ aliases)
  - ignored_providers = anthropic, xai, …

Requires OPENROUTER_MANAGEMENT_KEY.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from or_billing_policy import (  # noqa: E402
    has_forbidden_frontier_needle,
    is_anthropic_or_grok_model,
    is_or_allowlisted_model,
)


def _load_env() -> dict[str, str]:
    env = dict(os.environ)
    p = Path.home() / ".hermes" / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def _req(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://carrier-hermes.local",
            "X-Title": "Carrier billing guardrail sync",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} {url}: {err[:1200]}") from e


def _valid_catalog_id(mid: str) -> bool:
    if not mid or mid.startswith("~") or mid.startswith("openrouter/"):
        return False
    return True


def main() -> int:
    env = _load_env()
    mgmt = env.get("OPENROUTER_MANAGEMENT_KEY") or ""
    inf = env.get("OPENROUTER_API_KEY") or ""
    if not mgmt:
        print("OPENROUTER_MANAGEMENT_KEY missing", file=sys.stderr)
        return 2
    if not inf:
        print("OPENROUTER_API_KEY missing (needed to list catalog)", file=sys.stderr)
        return 2

    catalog = _req("GET", "https://openrouter.ai/api/v1/models", inf).get("data") or []
    ids = [m["id"] for m in catalog if _valid_catalog_id(m.get("id") or "")]

    allowed = sorted({m for m in ids if is_or_allowlisted_model(m)})
    if len(allowed) < 3:
        print("FAIL: allowlist too small after catalog filter", allowed, file=sys.stderr)
        return 1

    ignored = sorted(
        {
            m
            for m in ids
            if m not in allowed
            and (
                is_anthropic_or_grok_model(m)
                or m.startswith("anthropic/")
                or m.startswith("x-ai/")
                or has_forbidden_frontier_needle(m)
            )
        }
    )
    if not ignored:
        # API requires ignored_models >= 1; seed with a known expensive id
        ignored = ["openai/gpt-4o"] if "openai/gpt-4o" in ids else [ids[0]]

    listing = _req("GET", "https://openrouter.ai/api/v1/guardrails", mgmt)
    rows = listing.get("data") or []
    g = next((r for r in rows if "default" in str(r.get("name") or "").lower()), None) or (
        rows[0] if rows else None
    )
    if not g:
        print("no guardrails", file=sys.stderr)
        return 1
    gid = g["id"]

    payload = {
        "allowed_models": allowed,
        "ignored_models": ignored,
        "ignored_providers": [
            "anthropic",
            "xai",
            "azure",
            "bedrock",
            "claude-on-aws",
        ],
        "allowed_providers": None,
        "description": (
            "Carrier HARD allowlist: DeepSeek / Gemini Flash·Lite / gpt-oss only. "
            f"Ignore {len(ignored)} Claude/Grok/frontier catalog IDs. "
            "sync_or_billing_guardrail.py"
        ),
    }

    print(f"Patching {gid} ({g.get('name')})")
    print(f"  allowed={len(allowed)} ignored={len(ignored)}")
    for m in allowed:
        print(f"    allow {m}")

    updated = _req("PATCH", f"https://openrouter.ai/api/v1/guardrails/{gid}", mgmt, payload)
    data = updated.get("data") or updated
    am = data.get("allowed_models") or []
    if not am:
        print("FAIL: empty allowlist after patch", file=sys.stderr)
        return 1
    if any("claude" in x.lower() or "grok" in x.lower() for x in am):
        print("FAIL: frontier still on allowlist", am, file=sys.stderr)
        return 1

    # Confirm
    listing2 = _req("GET", "https://openrouter.ai/api/v1/guardrails", mgmt)
    for row in listing2.get("data") or []:
        if row.get("id") == gid:
            am2 = row.get("allowed_models") or []
            print(
                f"Confirmed allow={len(am2)} ignore={len(row.get('ignored_models') or [])}"
            )
            if not am2:
                print("FAIL re-fetch empty", file=sys.stderr)
                return 1
            break

    print("sync_or_billing_guardrail: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

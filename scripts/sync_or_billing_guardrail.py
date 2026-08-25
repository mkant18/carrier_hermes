#!/usr/bin/env python3
"""Push OpenRouter workspace guardrail to ALLOWLIST-only cheap models.

Replaces dated ignore-lists (which miss undated slugs like anthropic/claude-sonnet-5)
with an explicit allowed_models list from or_billing_policy.

Requires OPENROUTER_MANAGEMENT_KEY in ~/.hermes/.env (or env).
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

from or_billing_policy import or_guardrail_allowed_models  # noqa: E402

GUARDRAIL_NAME_HINT = "Default"


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
            "X-Title": "Carrier Ledger billing guardrail sync",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} {url}: {err[:800]}") from e


def main() -> int:
    env = _load_env()
    key = env.get("OPENROUTER_MANAGEMENT_KEY") or ""
    if not key:
        print("sync_or_billing_guardrail: OPENROUTER_MANAGEMENT_KEY missing", file=sys.stderr)
        return 2

    listing = _req("GET", "https://openrouter.ai/api/v1/guardrails", key)
    rows = listing.get("data") or []
    if not rows:
        print("sync_or_billing_guardrail: no guardrails found", file=sys.stderr)
        return 1

    # Prefer workspace Default
    g = None
    for row in rows:
        name = str(row.get("name") or "")
        if GUARDRAIL_NAME_HINT.lower() in name.lower():
            g = row
            break
    if g is None:
        g = rows[0]

    gid = g["id"]
    allowed = or_guardrail_allowed_models()
    # Hard deny list of expensive providers as ignored_providers (belt)
    ignored_providers = sorted(
        {
            "anthropic",
            "xai",
            "openai",  # gpt-oss still allowed via allowed_models override?
            # Note: if allowed_models is set, intersection applies — gpt-oss is
            # in allowed_models so openai provider may still be needed for gpt-oss.
            "azure",
            "bedrock",
            "claude-on-aws",
            "mistral",
            "cohere",
            "perplexity",
            "together",
            "fireworks",
            "groq",
            "deepinfra",
            "novita",
        }
    )
    # Do NOT ignore openai if we need gpt-oss — rely on allowed_models only.
    ignored_providers = [p for p in ignored_providers if p != "openai"]

    payload = {
        "allowed_models": allowed,
        # Clear partial dated denylist — allowlist is the sole model gate
        "ignored_models": [],
        # Keep ignoring anthropic + xai backends regardless
        "ignored_providers": ignored_providers,
        "allowed_providers": None,
        "description": (
            "Carrier HARD allowlist: DeepSeek/Gemini-Flash/gpt-oss only. "
            "No Claude/Grok/OpenAI-frontier via OpenRouter. Synced by sync_or_billing_guardrail.py"
        ),
    }

    print(f"Patching guardrail {gid} ({g.get('name')})")
    print(f"  allowed_models ({len(allowed)}):")
    for m in allowed:
        print(f"    - {m}")
    updated = _req("PATCH", f"https://openrouter.ai/api/v1/guardrails/{gid}", key, payload)
    # Some APIs wrap in data
    data = updated.get("data") or updated
    am = data.get("allowed_models")
    print("Result allowed_models count:", len(am or []))
    if not am:
        print("WARNING: API returned empty allowed_models — verify in dashboard", file=sys.stderr)
        return 1
    # Verify a forbidden model is not present
    joined = " ".join(am).lower()
    for bad in ("claude", "grok", "gpt-4", "opus", "sonnet-5"):
        if bad in joined and "gpt-oss" not in bad:
            # sonnet shouldn't appear
            if bad == "sonnet-5" or bad in joined:
                if any(bad in x.lower() for x in am):
                    print(f"FAIL: forbidden needle {bad!r} still in allowlist", file=sys.stderr)
                    return 1
    print("sync_or_billing_guardrail: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
share_subscriptions.py — make EVERY Carrier Hermes bot share subscription OAuth
providers in Michael's billing-safe priority order, THEN OpenRouter if present.

Policy (Michael, updated 2026-08-26):
  subscription priority = Grok/xai-oauth → OpenAI/openai-codex → OpenAI/openai-oauth → Anthropic/OAuth

  - primary stays whatever the bot is pinned to when it is already a subscription
  - fallbacks are rebuilt from the remaining subscription routes in priority order
    so OpenAI OAuth sits below Grok and above Anthropic
  - OpenRouter/API-key tails are NOT preserved automatically; per-token billing
    remains human-gated by the separate emergency policy, never a standing fallback
  - any duplicate / same-sub redundant entry is collapsed

Never adds an API-key route. Anthropic + xAI + OpenAI are OAuth/subscription only.
Idempotent. Uses Hermes venv python (PyYAML). No secrets touched.

Usage:  <venv-python> share_subscriptions.py [--dry-run]
"""
from __future__ import annotations
import glob, os, sys
from pathlib import Path
import yaml

HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
DRY = "--dry-run" in sys.argv

# Canonical subscription routes. OpenAI models use ChatGPT/Codex OAuth via
# provider=openai-codex, NOT OpenAI API or OpenRouter.
GROK = {"provider": "xai-oauth", "model": "grok-4.5"}
OPENAI_FRONTIER = {"provider": "openai-codex", "model": "gpt-5.6-sol"}
OPENAI_MID = {"provider": "openai-codex", "model": "gpt-5.6-terra"}
OPENAI_CHEAP = {"provider": "openai-codex", "model": "gpt-5.6-luna"}
CLAUDE = {"provider": "anthropic", "model": "claude-sonnet-4-6"}

# openai-oauth = ChatGPT Plus subscription OAuth (NEW — different from openai-codex)
OPENAI_OAUTH_CHEAP = {"provider": "openai-oauth", "model": "gpt-4o-mini"}
OPENAI_OAUTH_MID   = {"provider": "openai-oauth", "model": "gpt-4o"}
OPENAI_OAUTH_FRONT = {"provider": "openai-oauth", "model": "o3"}

SUBSCRIPTION_PRIORITY = [GROK, OPENAI_FRONTIER, OPENAI_OAUTH_MID, CLAUDE]


def subscription_chain_after(primary_provider: str, primary_model: str) -> list[dict]:
    """Return fallback subscriptions after the primary, in fleet priority order."""
    out: list[dict] = []
    for route in SUBSCRIPTION_PRIORITY:
        if route["provider"] == primary_provider and route["model"] == primary_model:
            continue
        if route["provider"] == primary_provider:
            continue
        out.append(dict(route))
    return out


def is_openrouter(fb: dict) -> bool:
    return (fb.get("provider") or "").lower() == "openrouter"


def normalize(cfg: dict) -> tuple[dict, str]:
    model = cfg.get("model") or {}
    primary_provider = (model.get("provider") or "").lower()
    if primary_provider not in ("xai-oauth", "openai-codex", "openai-oauth", "anthropic"):
        return cfg, f"SKIP (primary provider '{primary_provider}' not a subscription)"

    primary_model = str(model.get("default") or model.get("model") or "")

    # Build: remaining subscriptions in priority order. Per-token/OpenRouter
    # tails are deliberately NOT automatic fallbacks under Michael's policy.
    # The primary is already model.*.
    new_chain = subscription_chain_after(primary_provider, primary_model)

    # Safety: strip any accidental api_key/base_url on subscription entries.
    for e in new_chain:
        if e.get("provider") in ("xai-oauth", "openai-codex", "openai-oauth", "anthropic"):
            e.pop("base_url", None)
            e.pop("api_key", None)

    cfg["fallback_providers"] = new_chain
    prim = f"{model.get('provider')}/{model.get('default') or model.get('model')}"
    chain_str = " -> ".join([prim] + [f"{e['provider']}/{e['model']}" for e in new_chain])
    return cfg, chain_str


def main() -> int:
    changed = 0
    for cfg_path in sorted(glob.glob(str(HOME / "profiles" / "*" / "config.yaml"))):
        bot = os.path.basename(os.path.dirname(cfg_path))
        cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
        before = cfg.get("fallback_providers")
        cfg, info = normalize(cfg)
        after = cfg.get("fallback_providers")
        if info.startswith("SKIP"):
            print(f"  {bot:22} {info}")
            continue
        if before != after:
            changed += 1
            marker = "WOULD WRITE" if DRY else "WROTE"
        else:
            marker = "ok (already shared)"
        print(f"  {bot:22} {marker}: {info}")
        if not DRY and before != after:
            Path(cfg_path).write_text(
                yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
    print(f"\n{'(dry-run) ' if DRY else ''}{changed} config(s) updated. "
          "Every bot now: primary-sub -> Grok/OpenAI/Anthropic priority (no automatic OpenRouter tail).")
    print("Run billing_guard + restart affected gateways to load.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

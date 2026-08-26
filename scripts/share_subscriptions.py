#!/usr/bin/env python3
"""
share_subscriptions.py — make EVERY Carrier Hermes bot share the two OAuth
subscriptions and fall back on each other, THEN OpenRouter.

Policy (Michael, 2026-08-25):
  chain = [ primary-subscription , OTHER-subscription , <existing OpenRouter tiers> ]

  - primary stays whatever the bot is pinned to (xai-oauth/grok or anthropic/claude)
  - the OTHER subscription is inserted as the FIRST fallback (mutual failover)
  - existing OpenRouter allowlisted fallbacks (deepseek/gemini flash, gpt-oss)
    are preserved AFTER both subscriptions
  - any duplicate / same-sub redundant entry is collapsed

Never adds an API-key route. Anthropic + xAI are OAuth/subscription only.
Idempotent. Uses Hermes venv python (PyYAML). No secrets touched.

Usage:  <venv-python> share_subscriptions.py [--dry-run]
"""
from __future__ import annotations
import glob, os, sys
from pathlib import Path
import yaml

HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
DRY = "--dry-run" in sys.argv

# Canonical subscription routes.
GROK = {"provider": "xai-oauth", "model": "grok-4.5"}
CLAUDE = {"provider": "anthropic", "model": "claude-sonnet-4-6"}


def other_sub(primary_provider: str) -> dict:
    """Return the subscription that is NOT the primary."""
    if primary_provider == "xai-oauth":
        return dict(CLAUDE)
    return dict(GROK)


def is_openrouter(fb: dict) -> bool:
    return (fb.get("provider") or "").lower() == "openrouter"


def normalize(cfg: dict) -> tuple[dict, str]:
    model = cfg.get("model") or {}
    primary_provider = (model.get("provider") or "").lower()
    if primary_provider not in ("xai-oauth", "anthropic"):
        return cfg, f"SKIP (primary provider '{primary_provider}' not a subscription)"

    fbs = cfg.get("fallback_providers") or []
    # Keep ONLY the OpenRouter tiers from the existing chain (drop old sub entries;
    # we re-add both subs deterministically). Preserve their order + models.
    or_tiers = [dict(f) for f in fbs if is_openrouter(f)]

    # Build: [other-sub] + [openrouter tiers]. (primary is already model.*)
    new_chain = [other_sub(primary_provider)] + or_tiers

    # Safety: strip any accidental api_key/base_url on subscription entries.
    for e in new_chain:
        if e.get("provider") in ("xai-oauth", "anthropic"):
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
          "Every bot now: primary-sub -> other-sub -> OpenRouter.")
    print("Run billing_guard + restart affected gateways to load.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

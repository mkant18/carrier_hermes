#!/usr/bin/env python3
"""run_local.py — "Run Local with Ollama" toggle for a Hermes profile.

Flips a profile's default model between its normal (cloud/OAuth) model and the
local Ollama endpoint, and back — the one-command "Run Local with Ollama" switch.

Why a config toggle (not CLI flags): Hermes' generic `custom` provider defaults its
base_url to OpenRouter unless the config's `model.base_url` is set explicitly, so a
bare `-m ... --provider custom` gets billing-denied. The reliable, billing-safe way
to run local is to set the profile's `model` block to the Ollama endpoint. This
script does that safely and reversibly.

State: the previous `model` block is saved to `model_prev` in the same config so
`--cloud` restores it exactly. Idempotent.

Usage:
    python run_local.py --status                 # show current mode for the profile
    python run_local.py --local                  # switch to local Ollama (coder model)
    python run_local.py --local --model llama3.1:8b-instruct-q4_K_M
    python run_local.py --cloud                  # restore the saved cloud model
    python run_local.py --profile firstmate --local

Defaults to the 'default' profile (your own chat). Zero-LLM. Billing-safe:
custom/localhost is not a metered provider (billing_guard passes).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"

# OAuth fallback appended when going local, so a cold/broken Ollama fails OVER to
# subscription OAuth instead of crashing. NEVER an API key, NEVER OpenRouter.
# Michael's preference: on fallback, LAND ON HAIKU FIRST (cheapest/fastest OAuth
# degrade), then sonnet, then grok. And fail LOUDLY (see notify_local_fallback).
LOCAL_FALLBACK = [
    {"provider": "anthropic", "model": "claude-haiku-4-5"},
    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    {"provider": "xai-oauth", "model": "grok-4.5"},
]


def config_path(profile: str) -> Path:
    if profile in ("default", "", None):
        return HOME / "config.yaml"
    return HOME / "profiles" / profile / "config.yaml"


def load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def save(p: Path, cfg: dict) -> None:
    p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False,
                                allow_unicode=True), encoding="utf-8")


def is_local(cfg: dict) -> bool:
    m = cfg.get("model", {})
    return m.get("provider") == "custom" and "11434" in str(m.get("base_url", ""))


def status(profile: str) -> None:
    p = config_path(profile)
    if not p.exists():
        print(f"{profile}: NO CONFIG at {p}")
        return
    cfg = load(p)
    m = cfg.get("model", {})
    mode = "LOCAL (Ollama)" if is_local(cfg) else "CLOUD/OAuth"
    print(f"{profile}: {mode} — {m.get('default')} @ {m.get('provider')}"
          + (f" ({m.get('base_url')})" if m.get("base_url") else ""))
    if cfg.get("model_prev"):
        print(f"  saved cloud model: {cfg['model_prev'].get('default')} "
              f"@ {cfg['model_prev'].get('provider')}")


def go_local(profile: str, model: str) -> None:
    p = config_path(profile)
    cfg = load(p)
    if is_local(cfg):
        # already local — just update the model tag
        cfg["model"]["default"] = model
        save(p, cfg)
        print(f"{profile}: already local; model -> {model}")
        return
    # save the current cloud model block for restore
    cfg["model_prev"] = dict(cfg.get("model", {}))
    cfg["model_prev_fallback"] = list(cfg.get("fallback_providers", []) or [])
    cfg["model"] = {
        "default": model,
        "provider": "custom",
        "base_url": OLLAMA_URL,
        "api_key": "ollama",
    }
    cfg["fallback_providers"] = list(LOCAL_FALLBACK)
    save(p, cfg)
    print(f"{profile}: → LOCAL Ollama ({model} @ {OLLAMA_URL}) with OAuth fallback. "
          f"(prev cloud model saved)")


def go_cloud(profile: str) -> None:
    p = config_path(profile)
    cfg = load(p)
    if not is_local(cfg):
        print(f"{profile}: already on cloud/OAuth — nothing to restore")
        return
    prev = cfg.pop("model_prev", None)
    prev_fb = cfg.pop("model_prev_fallback", None)
    if not prev:
        print(f"{profile}: WARNING no saved cloud model; leaving as-is. "
              "Set one with `hermes model` or restore manually.")
        return
    cfg["model"] = prev
    if prev_fb is not None:
        cfg["fallback_providers"] = prev_fb
    save(p, cfg)
    print(f"{profile}: → CLOUD restored ({prev.get('default')} @ {prev.get('provider')})")


def main() -> int:
    ap = argparse.ArgumentParser(description='"Run Local with Ollama" toggle')
    ap.add_argument("--profile", default="default",
                    help="profile to toggle (default: your own 'default' profile)")
    ap.add_argument("--model", default=DEFAULT_LOCAL_MODEL,
                    help=f"local model tag (default: {DEFAULT_LOCAL_MODEL})")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--local", action="store_true", help="switch to local Ollama")
    g.add_argument("--cloud", action="store_true", help="restore the saved cloud model")
    g.add_argument("--status", action="store_true", help="show current mode")
    args = ap.parse_args()

    if args.local:
        go_local(args.profile, args.model)
    elif args.cloud:
        go_cloud(args.profile)
    else:
        status(args.profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())

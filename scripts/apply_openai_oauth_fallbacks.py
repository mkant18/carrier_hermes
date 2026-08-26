#!/usr/bin/env python3
"""Apply OpenAI Codex OAuth fallback routing fleet-wide.

Policy (Michael, 2026-08-26):
- NO OpenAI API keys, NO per-token OpenAI, NO OpenRouter frontier.
- Subscription priority: Grok/xai-oauth -> OpenAI/openai-codex -> Anthropic/OAuth.
- Local workers keep local primary; if local fails, use Grok, then cheap OpenAI
  Codex OAuth, then Claude Haiku OAuth.
- Decision/intelligence bots use Grok primary, OpenAI frontier fallback, then
  Anthropic fallback.

This script touches only profile config.yaml files. It does not read or write
secrets. Run billing_guard before and after.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERMES_HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
SCRIPTDIR = Path(__file__).resolve().parent

GROK = {"provider": "xai-oauth", "model": "grok-4.5"}
OPENAI_FRONTIER = {"provider": "openai-codex", "model": "gpt-5.6-sol"}
OPENAI_MID = {"provider": "openai-codex", "model": "gpt-5.6-terra"}
OPENAI_CHEAP = {"provider": "openai-codex", "model": "gpt-5.6-luna"}
CLAUDE_SONNET = {"provider": "anthropic", "model": "claude-sonnet-4-6"}
CLAUDE_OPUS = {"provider": "anthropic", "model": "claude-opus-4-5"}
CLAUDE_HAIKU = {"provider": "anthropic", "model": "claude-haiku-4-5"}

DECISION_BOTS = {
    "chief_of_staff",
    "marshal",
    "coding_lt",
    "ops_lt",
    "knowledge_lt",
    "maintenance_lt",
    "hermes_ai_explorer",
    "repair_planner",
    "pr_reviewer",
}

# Local-primary workers/watchers. Preserve the exact local model/base_url already
# present if configured; otherwise install a safe 128K local default.
LOCAL_WORKER_BOTS = {
    "api_watcher",
    "subscription_watcher",
    "firstmate",
    "git_yeoman",
    "passive_watch",
    "research_agent",
    "email_reader",
    "email_drafter",
    "calendar_manager",
    "todoist_manager",
    "finance_reader",
    "vault_librarian",
    "obsidian_archivist",
    "lockbox",
    "code_auditor",
    "patch_writer",
}

DEFAULT_LOCAL_MODEL = "llama3.1:8b-instruct-q4_K_M"
DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"


def route_str(route: dict) -> str:
    return f"{route.get('provider')}/{route.get('model') or route.get('default')}"


def run_guard(home: Path) -> None:
    guard = SCRIPTDIR / "billing_guard.py"
    result = subprocess.run(
        [sys.executable, str(guard), "--hermes-home", str(home)],
        capture_output=True,
        text=True,
    )
    out = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise SystemExit(f"billing_guard pre/post check failed:\n{out}")
    print(out)


def clean_subscription_route(route: dict) -> dict:
    out = dict(route)
    for key in ("base_url", "api_base", "api_base_url", "api_key", "key", "token", "key_env"):
        out.pop(key, None)
    return out


def set_decision_chain(cfg: dict, bot: str) -> tuple[dict, list[dict]]:
    # Frontier/decision: Grok -> OpenAI Sol -> Anthropic. Keep Opus as the
    # Anthropic terminal fallback for the two Shipwright planner/reviewer bots
    # that were explicitly Opus-tier; everyone else gets Sonnet.
    anthropic_tail = CLAUDE_OPUS if bot in {"repair_planner", "pr_reviewer"} else CLAUDE_SONNET
    model = {"default": GROK["model"], "provider": GROK["provider"]}
    fallbacks = [dict(OPENAI_FRONTIER), dict(anthropic_tail)]
    return model, fallbacks


def set_worker_chain(cfg: dict) -> tuple[dict, list[dict]]:
    raw_model = cfg.get("model")
    old_model: dict = raw_model if isinstance(raw_model, dict) else {}
    if str(old_model.get("provider") or "").lower() == "custom":
        model: dict = dict(old_model)
    else:
        model = {"default": DEFAULT_LOCAL_MODEL, "provider": "custom", "base_url": DEFAULT_LOCAL_BASE_URL}
    model.setdefault("default", DEFAULT_LOCAL_MODEL)
    model.setdefault("provider", "custom")
    model.setdefault("base_url", DEFAULT_LOCAL_BASE_URL)
    fallbacks = [dict(GROK), dict(OPENAI_CHEAP), dict(CLAUDE_HAIKU)]
    return model, fallbacks


def apply_one(path: Path, dry_run: bool) -> tuple[bool, str]:
    bot = path.parent.name
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    old_model = cfg.get("model") or {}
    old_fallbacks = cfg.get("fallback_providers") or []

    if bot in DECISION_BOTS:
        model, fallbacks = set_decision_chain(cfg, bot)
        tier = "decision"
    elif bot in LOCAL_WORKER_BOTS:
        model, fallbacks = set_worker_chain(cfg)
        tier = "worker-local"
    else:
        # Unknown future profile: do not invent a primary. If it already has a
        # subscription primary, give it midtier-safe fallback order; otherwise skip.
        provider = str((old_model or {}).get("provider") or "").lower()
        if provider not in {"xai-oauth", "openai-codex", "anthropic"}:
            return False, f"{bot:22} SKIP unknown non-subscription primary {provider!r}"
        model = dict(old_model)
        ordered = [dict(GROK), dict(OPENAI_MID), dict(CLAUDE_SONNET)]
        fallbacks = [r for r in ordered if r["provider"] != provider]
        tier = "unknown-subscription"

    model.pop("fallback", None)
    cfg.pop("fallback_model", None)
    cfg["model"] = clean_subscription_route(model) if model.get("provider") in {"xai-oauth", "openai-codex", "anthropic"} else model
    cfg["fallback_providers"] = [clean_subscription_route(r) for r in fallbacks]

    changed = old_model != cfg["model"] or old_fallbacks != cfg["fallback_providers"]
    chain = " -> ".join([route_str(cfg["model"])] + [route_str(r) for r in cfg["fallback_providers"]])
    marker = "WOULD" if dry_run and changed else "WROTE" if changed else "ok"
    if changed and not dry_run:
        backup = path.with_suffix(".yaml.pre-openai-oauth")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    return changed, f"{bot:22} {marker:5} [{tier}] {chain}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes-home", default=str(HERMES_HOME))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    home = Path(args.hermes_home)

    print("=== preflight billing guard ===")
    run_guard(home)
    print("\n=== applying OpenAI Codex OAuth fallback policy ===")
    changed = 0
    total = 0
    for cfg_path in sorted((home / "profiles").glob("*/config.yaml")):
        total += 1
        did_change, line = apply_one(cfg_path, args.dry_run)
        changed += int(did_change)
        print("  " + line)

    print(f"\n{'(dry-run) ' if args.dry_run else ''}{changed}/{total} profile config(s) changed")
    if not args.dry_run:
        print("\n=== postflight billing guard ===")
        run_guard(home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

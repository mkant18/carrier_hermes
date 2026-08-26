#!/usr/bin/env python3
"""patch_rote_bot_configs.py — idempotently patch the 4 rote bot profile
configs to route through Claude Max primary, with the local Ollama LLM
inserted into the fallback chain (idle-only, zero-cost).

CURRENT structure (per bot):
    model:
      default: grok-4.5
      provider: xai-oauth
    fallback_providers:
    - provider: anthropic
      model: claude-sonnet-5
    - provider: openrouter
      model: deepseek/deepseek-v4-flash-0731
    - provider: openrouter
      model: google/gemini-2.5-flash-lite

TARGET structure (per bot):
    model:
      default: claude-sonnet-5
      provider: anthropic
    fallback_providers:
      - provider: xai-oauth
        model: grok-4.5
      # LOCAL LLM — idle-only, zero cost
      - provider: custom
        model: qwen2.5:7b-instruct-q4_K_M
        base_url: http://localhost:11434/v1
      - provider: openrouter
        model: deepseek/deepseek-v4-flash-0731
      - provider: openrouter
        model: google/gemini-2.5-flash-lite

Idempotent: if the local LLM entry is already present in
fallback_providers, the script skips that file (no changes made).

All other top-level config keys (platform_toolsets, known_plugin_toolsets,
mcp_servers, plugins, onboarding, etc.) are preserved untouched.

Usage:
    python scripts/patch_rote_bot_configs.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("patch_rote_bot_configs: need PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

HERMES_HOME = "C:/Users/micha/AppData/Local/hermes"

PROFILE_NAMES = [
    "research_agent",
    "passive_watch",
    "vault_librarian",
    "obsidian_archivist",
]

LOCAL_LLM_MODEL = "qwen2.5:7b-instruct-q4_K_M"
LOCAL_LLM_BASE_URL = "http://localhost:11434/v1"
LOCAL_LLM_PROVIDER = "custom"

TARGET_MODEL_DEFAULT = "claude-sonnet-5"
TARGET_MODEL_PROVIDER = "anthropic"

TARGET_FALLBACKS: list[dict[str, Any]] = [
    {"provider": "xai-oauth", "model": "grok-4.5"},
    {
        "provider": LOCAL_LLM_PROVIDER,
        "model": LOCAL_LLM_MODEL,
        "base_url": LOCAL_LLM_BASE_URL,
    },
    {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash-0731"},
    {"provider": "openrouter", "model": "google/gemini-2.5-flash-lite"},
]


def profile_config_path(profile_name: str) -> Path:
    return Path(HERMES_HOME) / "profiles" / profile_name / "config.yaml"


def has_local_llm_entry(fallback_providers: Any) -> bool:
    if not isinstance(fallback_providers, list):
        return False
    for entry in fallback_providers:
        if not isinstance(entry, dict):
            continue
        if (
            str(entry.get("provider", "")).strip().lower() == LOCAL_LLM_PROVIDER
            and str(entry.get("model", "")).strip() == LOCAL_LLM_MODEL
        ):
            return True
    return False


def patch_one(path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Returns (changed, message)."""
    if not path.exists():
        return False, f"SKIP (not found): {path}"

    try:
        text = path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(text) or {}
    except Exception as e:  # noqa: BLE001
        return False, f"SKIP (parse error): {path}: {e}"

    if not isinstance(cfg, dict):
        return False, f"SKIP (not a mapping at top level): {path}"

    existing_fallbacks = cfg.get("fallback_providers")
    if has_local_llm_entry(existing_fallbacks):
        return False, f"SKIP (already patched — local LLM entry present): {path}"

    model_block = cfg.get("model")
    if not isinstance(model_block, dict):
        model_block = {}

    before_default = model_block.get("default")
    before_provider = model_block.get("provider")
    before_fallbacks = existing_fallbacks

    model_block["default"] = TARGET_MODEL_DEFAULT
    model_block["provider"] = TARGET_MODEL_PROVIDER
    cfg["model"] = model_block
    cfg["fallback_providers"] = [dict(entry) for entry in TARGET_FALLBACKS]

    summary_lines = [
        f"model.default: {before_default!r} -> {TARGET_MODEL_DEFAULT!r}",
        f"model.provider: {before_provider!r} -> {TARGET_MODEL_PROVIDER!r}",
        f"fallback_providers: {before_fallbacks!r} -> "
        f"[xai-oauth/grok-4.5, custom/{LOCAL_LLM_MODEL}, "
        f"openrouter/deepseek-v4-flash-0731, openrouter/gemini-2.5-flash-lite]",
    ]

    if dry_run:
        return True, f"DRY-RUN would patch: {path}\n    " + "\n    ".join(summary_lines)

    dumped = yaml.dump(cfg, default_flow_style=False, sort_keys=False)
    # Insert the "LOCAL LLM" comment above the custom-provider fallback entry.
    # yaml.dump won't preserve inline comments, so we splice it in as text.
    # yaml.dump renders top-level sequence items with no extra indent
    # (e.g. "- provider: custom\n  model: ...\n"), so match on that shape
    # and reuse whatever indent precedes the "- provider:" line found.
    lines = dumped.splitlines(keepends=True)
    out_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip(" ")
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(f"- provider: {LOCAL_LLM_PROVIDER}\n"):
            out_lines.append(f"{indent}# LOCAL LLM \u2014 idle-only, zero cost\n")
        out_lines.append(line)
    dumped = "".join(out_lines)

    path.write_text(dumped, encoding="utf-8")
    return True, f"PATCHED: {path}\n    " + "\n    ".join(summary_lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing files"
    )
    args = ap.parse_args(argv)

    any_error = False
    print("patch_rote_bot_configs: processing 4 rote bot profiles ...")
    for name in PROFILE_NAMES:
        path = profile_config_path(name)
        changed, message = patch_one(path, dry_run=args.dry_run)
        print(f"[{name}] {message}")
        if not changed and "SKIP (not found)" in message:
            any_error = True
        if not changed and "SKIP (parse error)" in message:
            any_error = True

    print()
    print("Done." if not args.dry_run else "Dry run complete — no files written.")
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())

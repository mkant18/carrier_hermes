#!/usr/bin/env python3
"""Carrier Hermes — subscription billing hard-guard.

HARD RULE (Michael):
  Never bill Anthropic (Claude) or xAI (Grok) via API tokens or OpenRouter.
  Those families are SUBSCRIPTION / OAUTH only:
    - anthropic  → Claude Max OAuth
    - xai-oauth  → SuperGrok OAuth

OpenRouter is allowed ONLY for non-frontier cheap/paid tails
(DeepSeek, Gemini Flash Lite/Flash, gpt-oss, etc.).

Exit codes:
  0 = clean
  1 = violation(s) found
  2 = usage / IO error
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("billing_guard: need PyYAML", file=sys.stderr)
    sys.exit(2)

# Substrings (case-insensitive) that must NEVER appear on openrouter routes.
FORBIDDEN_OPENROUTER_NEEDLES = (
    "anthropic/",
    "anthropic.",
    "claude-opus",
    "claude-3",
    "claude-4",
    "claude-sonnet",  # Sonnet must be anthropic OAuth, never OR
    "claude-haiku",
    "x-ai/",
    "xai/",
    "grok-",
    "grok/",
    "/grok",
)

# Providers that mean pay-per-token frontier (banned). OAuth names are allowed.
FORBIDDEN_PROVIDERS = {
    "xai",  # bare xai API key provider — use xai-oauth only
}

# Env keys that enable Anthropic/xAI API-token billing. Must not be set for fleet.
FORBIDDEN_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
)

ALLOWED_FRONTIER_PROVIDERS = {"anthropic", "xai-oauth"}


def _is_forbidden_openrouter_model(model: str) -> bool:
    m = (model or "").lower().strip()
    if not m:
        return False
    return any(n in m for n in FORBIDDEN_OPENROUTER_NEEDLES)


def check_fallback_entry(provider: str, model: str, where: str) -> list[str]:
    errs: list[str] = []
    p = (provider or "").lower().strip()
    m = (model or "").strip()
    if p in FORBIDDEN_PROVIDERS:
        errs.append(f"{where}: forbidden provider {p!r} (use xai-oauth, not API-key xai)")
    if p == "openrouter" and _is_forbidden_openrouter_model(m):
        errs.append(
            f"{where}: BILLING VIOLATION openrouter/{m} — "
            "Anthropic/Grok must never ride OpenRouter or API tokens"
        )
    # anthropic provider with a base_url pointing at openrouter is also bad — checked elsewhere
    return errs


def scan_config(path: Path, label: str) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return errs
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot parse YAML: {e}"]

    model = cfg.get("model") or {}
    if isinstance(model, dict):
        prov = str(model.get("provider") or "")
        default = str(model.get("default") or "")
        errs.extend(check_fallback_entry(prov, default, f"{label} model.default"))
        # primary must not be openrouter for grok/claude
        if prov == "openrouter" and _is_forbidden_openrouter_model(default):
            errs.append(f"{label}: primary model is forbidden openrouter route")

        fb = model.get("fallback")
        if isinstance(fb, dict):
            errs.extend(
                check_fallback_entry(
                    str(fb.get("provider") or ""),
                    str(fb.get("model") or fb.get("default") or ""),
                    f"{label} model.fallback",
                )
            )
        elif isinstance(fb, str) and fb:
            # string fallback — if it looks like openrouter/anthropic/...
            if fb.lower().startswith("openrouter/") and _is_forbidden_openrouter_model(fb):
                errs.append(f"{label}: model.fallback string {fb!r} forbidden")

        aliases = model.get("aliases") or {}
        if isinstance(aliases, dict):
            for k, v in aliases.items():
                vs = str(v or "")
                if vs.lower().startswith("openrouter/") and _is_forbidden_openrouter_model(vs):
                    errs.append(f"{label}: alias {k!r} -> {vs!r} forbidden")

    for i, fb in enumerate(cfg.get("fallback_providers") or []):
        if not isinstance(fb, dict):
            continue
        errs.extend(
            check_fallback_entry(
                str(fb.get("provider") or ""),
                str(fb.get("model") or ""),
                f"{label} fallback_providers[{i}]",
            )
        )

    # base_url tricks
    m = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    bu = str((m or {}).get("base_url") or cfg.get("base_url") or "").lower()
    if "openrouter" in bu and any(
        x in str((m or {}).get("default") or "").lower() for x in ("grok", "claude", "anthropic")
    ):
        errs.append(f"{label}: openrouter base_url with frontier model name")

    return errs


def scan_env_file(path: Path, label: str) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return errs
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot read: {e}"]
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in FORBIDDEN_ENV_KEYS and val:
            errs.append(
                f"{label}: {key} is set (len={len(val)}) — "
                "remove it; use anthropic OAuth / xai-oauth only (no API tokens)"
            )
    return errs


def scan_process_env() -> list[str]:
    errs: list[str] = []
    for key in FORBIDDEN_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            errs.append(
                f"process env: {key} is set (len={len(val)}) — unset for fleet sessions"
            )
    return errs


def iter_profile_configs(hermes_home: Path):
    yield hermes_home / "config.yaml", "default"
    profiles = hermes_home / "profiles"
    if profiles.is_dir():
        for p in sorted(profiles.iterdir()):
            if p.is_dir():
                yield p / "config.yaml", f"profile:{p.name}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hermes-home",
        default=os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes"),
    )
    ap.add_argument(
        "--fix-env",
        action="store_true",
        help="Comment out forbidden API key lines in .env files (does not unset process env)",
    )
    ap.add_argument("--quiet-ok", action="store_true")
    args = ap.parse_args(argv)

    home = Path(args.hermes_home).expanduser()
    errs: list[str] = []

    errs.extend(scan_process_env())

    env_paths = [home / ".env"]
    profiles = home / "profiles"
    if profiles.is_dir():
        for p in profiles.iterdir():
            if p.is_dir():
                env_paths.append(p / ".env")

    for ep in env_paths:
        label = str(ep)
        e = scan_env_file(ep, label)
        if e and args.fix_env and ep.exists():
            text = ep.read_text(encoding="utf-8", errors="ignore")
            out_lines = []
            for line in text.splitlines():
                stripped = line.strip()
                blocked = False
                for key in FORBIDDEN_ENV_KEYS:
                    if stripped.startswith(key + "=") and not stripped.startswith("#"):
                        out_lines.append(
                            f"# BLOCKED_BY_billing_guard (no Anthropic/Grok API tokens): {line}"
                        )
                        blocked = True
                        break
                if not blocked:
                    out_lines.append(line)
            ep.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
            # re-scan
            e = scan_env_file(ep, label)
        errs.extend(e)

    for cfg_path, label in iter_profile_configs(home):
        errs.extend(scan_config(cfg_path, label))

    if errs:
        print("billing_guard: FAIL")
        for x in errs:
            print(f"  - {x}")
        print(
            "\nRemediation: use xai-oauth + anthropic OAuth only for Grok/Claude; "
            "OpenRouter only for DeepSeek/Gemini/gpt-oss tails; "
            "unset ANTHROPIC_API_KEY / XAI_API_KEY; re-run apply_bot_matrix.sh"
        )
        return 1

    if not args.quiet_ok:
        print("billing_guard: PASS — no Anthropic/Grok API-token or OpenRouter frontier routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

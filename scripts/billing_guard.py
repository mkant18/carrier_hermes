#!/usr/bin/env python3
"""Carrier Hermes — subscription billing hard-guard (config + env audit + fix).

HARD RULE: OpenRouter/metered never carries Claude/Grok/frontier.
Canonical policy: or_billing_policy.py

Exit: 0 clean, 1 violations, 2 usage error
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("billing_guard: need PyYAML", file=sys.stderr)
    sys.exit(2)

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from or_billing_policy import (  # noqa: E402
    FORBIDDEN_ENV_KEYS,
    scrub_aliases,
    scrub_fallback_providers,
    walk_config_routes,
)


def scan_env_file(path: Path, label: str) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return errs
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
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
    errs = []
    for key in FORBIDDEN_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            errs.append(f"process env: {key} is set (len={len(val)}) — unset for fleet")
    return errs


def iter_profile_configs(hermes_home: Path):
    yield hermes_home / "config.yaml", "default"
    profiles = hermes_home / "profiles"
    if profiles.is_dir():
        for p in sorted(profiles.iterdir()):
            if p.is_dir():
                yield p / "config.yaml", f"profile:{p.name}"


def fix_config(path: Path) -> list[str]:
    """Scrub forbidden aliases/fallbacks; return log lines."""
    logs: list[str] = []
    if not path.exists():
        return logs
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"{path}: parse error {e}"]
    if not isinstance(cfg, dict):
        return logs
    changed = False
    model = cfg.get("model")
    if isinstance(model, dict):
        aliases = model.get("aliases")
        if isinstance(aliases, dict):
            for line in scrub_aliases(aliases):
                logs.append(f"{path.name}: {line}")
                changed = True
            if not aliases:
                model.pop("aliases", None)
        # strip legacy single fallback if dirty
        fb = model.get("fallback")
        if isinstance(fb, dict):
            from or_billing_policy import violation_for_route

            err = violation_for_route(
                provider=fb.get("provider"),
                model=fb.get("model") or fb.get("default"),
                base_url=fb.get("base_url"),
                where="model.fallback",
            )
            if err:
                model.pop("fallback", None)
                logs.append(f"{path.name}: REMOVED {err}")
                changed = True
        elif isinstance(fb, str) and "openrouter" in fb.lower():
            from or_billing_policy import is_billing_violation, normalize_model_slug

            if is_billing_violation("openrouter", normalize_model_slug(fb)):
                model.pop("fallback", None)
                logs.append(f"{path.name}: REMOVED model.fallback string {fb!r}")
                changed = True
        # Never leave openrouter base_url on anthropic/xai-oauth primary
        bu = str(model.get("base_url") or "")
        prov = str(model.get("provider") or "").lower()
        if "openrouter" in bu.lower() and prov in {"anthropic", "xai-oauth", "xai"}:
            model.pop("base_url", None)
            logs.append(f"{path.name}: REMOVED openrouter base_url on {prov}")
            changed = True
        if "openrouter" in bu.lower() and prov == "openrouter":
            # OK for OR primary only if model allowlisted — walk catches it
            pass

    fbs = cfg.get("fallback_providers")
    if isinstance(fbs, list):
        cleaned, flogs = scrub_fallback_providers(fbs)
        if flogs:
            cfg["fallback_providers"] = cleaned
            for line in flogs:
                logs.append(f"{path.name}: {line}")
            changed = True

    if changed:
        path.write_text(
            yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    return logs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hermes-home",
        default=os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes"),
    )
    ap.add_argument("--fix-env", action="store_true")
    ap.add_argument(
        "--fix-config",
        action="store_true",
        help="Scrub forbidden aliases/fallbacks from configs then re-scan",
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
            out = []
            for line in text.splitlines():
                stripped = line.strip()
                blocked = False
                for key in FORBIDDEN_ENV_KEYS:
                    if stripped.startswith(key + "=") and not stripped.startswith("#"):
                        out.append(
                            f"# BLOCKED_BY_billing_guard (no Anthropic/Grok API tokens): {line}"
                        )
                        blocked = True
                        break
                if not blocked:
                    out.append(line)
            ep.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
            e = scan_env_file(ep, label)
        errs.extend(e)

    if args.fix_config:
        for cfg_path, _label in iter_profile_configs(home):
            for line in fix_config(cfg_path):
                print(f"fix: {line}")

    for cfg_path, label in iter_profile_configs(home):
        if not cfg_path.exists():
            continue
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            errs.append(f"{label}: cannot parse: {e}")
            continue
        errs.extend(walk_config_routes(cfg, label))

    if errs:
        print("billing_guard: FAIL")
        for x in errs:
            print(f"  - {x}")
        print(
            "\nRemediation: anthropic OAuth + xai-oauth only for Claude/Grok; "
            "OpenRouter ALLOWLIST only (DeepSeek/Gemini Flash/gpt-oss); "
            "python3 scripts/billing_guard.py --fix-env --fix-config; "
            "python3 scripts/sync_or_billing_guardrail.py; "
            "bash scripts/apply_bot_matrix.sh"
        )
        return 1

    if not args.quiet_ok:
        print(
            "billing_guard: PASS — no Anthropic/Grok/frontier on OpenRouter or API tokens"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Carrier Hermes — billing hard-guard (config + env audit).

Uses or_billing_policy.py (SINGLE SOURCE OF TRUTH).

HARD RULE — PERIOD, FULL STOP:
  OpenRouter / metered aggregators MUST NEVER run Anthropic/Claude or Grok/xAI
  (or any non-allowlisted frontier). Those families are OAuth only.

Exit: 0 clean · 1 violations · 2 IO
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("billing_guard: need PyYAML", file=sys.stderr)
    sys.exit(2)

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from or_billing_policy import (  # noqa: E402
    FORBIDDEN_ENV_KEYS,
    scrub_aliases,
    scrub_fallback_providers,
    self_test,
    walk_config_routes,
)


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
                "remove it; Anthropic/Grok are OAuth only (no API tokens)"
            )
    return errs


def scan_process_env() -> list[str]:
    errs: list[str] = []
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


def scan_config_file(path: Path, label: str) -> list[str]:
    if not path.exists():
        return []
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot parse YAML: {e}"]
    if not isinstance(cfg, dict):
        return []
    return walk_config_routes(cfg, label)


def fix_env_file(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    out: list[str] = []
    n = 0
    for line in text.splitlines():
        stripped = line.strip()
        blocked = False
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in FORBIDDEN_ENV_KEYS:
                out.append(f"# BLOCKED_BY_billing_guard (no Anthropic/Grok API tokens): {line}")
                blocked = True
                n += 1
        if not blocked:
            out.append(line)
    if n:
        path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return n


def fix_config_file(path: Path, label: str) -> list[str]:
    logs: list[str] = []
    if not path.exists():
        return logs
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"{label}: cannot parse for fix: {e}"]
    if not isinstance(cfg, dict):
        return logs

    changed = False
    model = cfg.get("model")
    if isinstance(model, dict):
        aliases = model.get("aliases")
        if isinstance(aliases, dict):
            for line in scrub_aliases(aliases):
                logs.append(f"{label}: {line}")
                changed = True
        from or_billing_policy import violation_for_route, check_alias_value

        fb = model.get("fallback")
        if isinstance(fb, dict):
            err = violation_for_route(
                provider=fb.get("provider"),
                model=fb.get("model") or fb.get("default"),
                base_url=fb.get("base_url"),
                where=f"{label}.model.fallback",
            )
            if err:
                model.pop("fallback", None)
                logs.append(f"{label}: REMOVED {err}")
                changed = True
        elif isinstance(fb, str) and fb:
            err = check_alias_value("fallback", fb, label)
            if err:
                model.pop("fallback", None)
                logs.append(f"{label}: REMOVED {err}")
                changed = True

        # Primary on OR with forbidden model — do not silently rewrite primary
        # (too dangerous); leave for FAIL report.

    fbp = cfg.get("fallback_providers")
    if isinstance(fbp, list):
        cleaned, scrub_logs = scrub_fallback_providers(fbp)
        if scrub_logs:
            cfg["fallback_providers"] = cleaned
            for line in scrub_logs:
                logs.append(f"{label}: {line}")
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
    ap.add_argument("--fix-config", action="store_true")
    ap.add_argument("--quiet-ok", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        try:
            self_test()
        except AssertionError as e:
            print(f"billing_guard self_test FAIL: {e}", file=sys.stderr)
            return 1
        print("billing_guard: self_test OK")
        return 0

    home = Path(args.hermes_home).expanduser()
    errs: list[str] = []
    fix_logs: list[str] = []

    errs.extend(scan_process_env())

    env_paths = [home / ".env"]
    profiles = home / "profiles"
    if profiles.is_dir():
        for p in profiles.iterdir():
            if p.is_dir():
                env_paths.append(p / ".env")

    for ep in env_paths:
        if args.fix_env:
            n = fix_env_file(ep)
            if n:
                fix_logs.append(f"{ep}: blocked {n} API-key line(s)")
        errs.extend(scan_env_file(ep, str(ep)))

    for cfg_path, label in iter_profile_configs(home):
        if args.fix_config:
            fix_logs.extend(fix_config_file(cfg_path, label))
        errs.extend(scan_config_file(cfg_path, label))

    for line in fix_logs:
        print(f"billing_guard fix: {line}")

    if errs:
        print("billing_guard: FAIL")
        for x in errs:
            print(f"  - {x}")
        print(
            "\nHARD RULE: OpenRouter/metered MUST NEVER carry Anthropic/Claude or Grok.\n"
            "OAuth only: provider anthropic · provider xai-oauth.\n"
            "OR allowlist only: DeepSeek / Gemini Flash-Lite / gpt-oss.\n"
            "Remediation: unset ANTHROPIC_API_KEY/XAI_API_KEY; "
            "python3 scripts/billing_guard.py --fix-env --fix-config; "
            "bash scripts/apply_bot_matrix.sh; "
            "python3 scripts/sync_or_billing_guardrail.py"
        )
        return 1

    if not args.quiet_ok:
        print(
            "billing_guard: PASS — OpenRouter allowlist-only; "
            "zero Anthropic/Claude/Grok on metered transports; no API tokens for those families"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

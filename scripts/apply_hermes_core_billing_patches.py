#!/usr/bin/env python3
"""Apply CARRIER_BILLING_HARD_DENY patches to the local hermes-agent install.

These refuse OpenRouter+Claude/Grok at:
  - conversation_loop (before every API call)
  - agent_runtime_helpers.switch_model
  - chat_completion_helpers.try_activate_fallback
  - hermes_cli.model_switch.switch_model

Idempotent. Re-run after `hermes update` (updates can wipe the install tree).

Does NOT modify the Nous upstream remote — local install only.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def find_hermes_agent() -> Path:
    env = os.environ.get("HERMES_AGENT_ROOT")
    if env:
        p = Path(env)
        if (p / "agent" / "conversation_loop.py").exists():
            return p
    candidates = [
        Path.home() / ".hermes" / "hermes-agent",
        Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent",
        Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".hermes" / "hermes-agent",
    ]
    for c in candidates:
        if c and (c / "agent" / "conversation_loop.py").exists():
            return c
    # Try locate via hermes binary
    try:
        import subprocess

        out = subprocess.check_output(
            [sys.executable, "-c", "import hermes_cli, pathlib; print(pathlib.Path(hermes_cli.__file__).resolve().parent.parent)"],
            text=True,
            timeout=10,
        ).strip()
        p = Path(out)
        if (p / "agent" / "conversation_loop.py").exists():
            return p
    except Exception:
        pass
    raise SystemExit(
        "Cannot find hermes-agent install. Set HERMES_AGENT_ROOT to the clone path."
    )


MARKER = "CARRIER_BILLING_HARD_DENY"


def patch_conversation_loop(root: Path) -> bool:
    path = root / "agent" / "conversation_loop.py"
    t = path.read_text(encoding="utf-8")
    if MARKER in t:
        print(f"OK already: {path}")
        return False
    anchor = """                try:
                    from hermes_cli.middleware import apply_llm_request_middleware

                    _llm_request_mw = apply_llm_request_middleware("""
    inject = f'''                # --- {MARKER} (do not remove) ---
                # Absolute refuse: Claude/Grok/frontier must never hit OpenRouter/metered.
                try:
                    import sys as _sys
                    from pathlib import Path as _Path
                    _bp = _Path.home() / "carrier_hermes" / "scripts"
                    _alt = _Path(os.environ.get("CARRIER_HERMES_ROOT", "")) / "scripts" if os.environ.get("CARRIER_HERMES_ROOT") else None
                    for _cand in (_bp, _alt):
                        if _cand and _cand.is_dir() and str(_cand) not in _sys.path:
                            _sys.path.insert(0, str(_cand))
                    from or_billing_policy import is_billing_violation, violation_message
                    _req_model = api_kwargs.get("model") or agent.model
                    if is_billing_violation(agent.provider, _req_model, getattr(agent, "base_url", None)):
                        _msg = violation_message(agent.provider, _req_model, getattr(agent, "base_url", None))
                        logger.error("{MARKER}: %s", _msg)
                        raise RuntimeError(_msg)
                except RuntimeError:
                    raise
                except Exception as _bill_exc:
                    logger.warning("{MARKER} check error: %s", _bill_exc)
                    _pl = (getattr(agent, "provider", "") or "").lower()
                    _ml = str(api_kwargs.get("model") or getattr(agent, "model", "") or "").lower()
                    _bl = (getattr(agent, "base_url", "") or "").lower()
                    if ("openrouter" in _pl or "openrouter" in _bl) and any(
                        x in _ml for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus", "haiku")
                    ):
                        raise RuntimeError(f"BILLING HARD DENY: {{agent.provider}}/{{api_kwargs.get('model') or agent.model}}")
                # --- end {MARKER} ---

'''
    # inject needs os imported in conversation_loop — usually already is
    if "import os" not in t[:3000] and "\nimport os\n" not in t:
        # local import inside block uses os.environ — add import os in block
        inject = inject.replace(
            "import sys as _sys",
            "import os as _os\n                    import sys as _sys",
        ).replace("os.environ", "_os.environ")

    if anchor not in t:
        print(f"WARN: anchor not found in {path} — hermes version drift", file=sys.stderr)
        return False
    path.write_text(t.replace(anchor, inject + anchor, 1), encoding="utf-8")
    print(f"PATCHED {path}")
    return True


def patch_runtime_switch(root: Path) -> bool:
    path = root / "agent" / "agent_runtime_helpers.py"
    t = path.read_text(encoding="utf-8")
    if MARKER in t:
        print(f"OK already: {path}")
        return False
    anchor = 'turn-scoped).\n    """\n    from hermes_cli.providers import determine_api_mode\n'
    # tolerate slight docstring drift
    if anchor not in t:
        m = re.search(
            r'(def switch_model\(agent, new_model, new_provider.*?\n    """\n)',
            t,
            re.S,
        )
        if not m:
            print(f"WARN: switch_model anchor missing in {path}", file=sys.stderr)
            return False
        insert_at = m.end()
        check = f'''
    # {MARKER}
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _bp = _Path.home() / "carrier_hermes" / "scripts"
        if str(_bp) not in _sys.path:
            _sys.path.insert(0, str(_bp))
        from or_billing_policy import is_billing_violation, violation_message
        if is_billing_violation(new_provider, new_model, base_url):
            raise RuntimeError(violation_message(new_provider, new_model, base_url))
    except RuntimeError:
        raise
    except Exception:
        pl, ml, bl = (new_provider or "").lower(), (new_model or "").lower(), (base_url or "").lower()
        if ("openrouter" in pl or "openrouter" in bl) and any(
            x in ml for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus")
        ):
            raise RuntimeError(f"BILLING HARD DENY: {{new_provider}}/{{new_model}}")

'''
        t = t[:insert_at] + check + t[insert_at:]
        path.write_text(t, encoding="utf-8")
        print(f"PATCHED {path}")
        return True
    check = f'''turn-scoped).
    """
    # {MARKER}
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _bp = _Path.home() / "carrier_hermes" / "scripts"
        if str(_bp) not in _sys.path:
            _sys.path.insert(0, str(_bp))
        from or_billing_policy import is_billing_violation, violation_message
        if is_billing_violation(new_provider, new_model, base_url):
            raise RuntimeError(violation_message(new_provider, new_model, base_url))
    except RuntimeError:
        raise
    except Exception:
        pl, ml, bl = (new_provider or "").lower(), (new_model or "").lower(), (base_url or "").lower()
        if ("openrouter" in pl or "openrouter" in bl) and any(
            x in ml for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus")
        ):
            raise RuntimeError(f"BILLING HARD DENY: {{new_provider}}/{{new_model}}")

    from hermes_cli.providers import determine_api_mode
'''
    path.write_text(t.replace(anchor, check, 1), encoding="utf-8")
    print(f"PATCHED {path}")
    return True


def patch_fallback(root: Path) -> bool:
    path = root / "agent" / "chat_completion_helpers.py"
    t = path.read_text(encoding="utf-8")
    if MARKER in t:
        print(f"OK already: {path}")
        return False
    anchor = '''    fb_provider = (fb.get("provider") or "").strip().lower()
    fb_model = (fb.get("model") or "").strip()
    if not fb_provider or not fb_model:
        return agent._try_activate_fallback(reason)  # skip invalid, try next
'''
    inject = f'''    fb_provider = (fb.get("provider") or "").strip().lower()
    fb_model = (fb.get("model") or "").strip()
    if not fb_provider or not fb_model:
        return agent._try_activate_fallback(reason)  # skip invalid, try next

    # {MARKER} — never activate OR+Claude/Grok/frontier fallbacks
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _bp = _Path.home() / "carrier_hermes" / "scripts"
        if str(_bp) not in _sys.path:
            _sys.path.insert(0, str(_bp))
        from or_billing_policy import is_billing_violation
        _fb_bu = str(fb.get("base_url") or "")
        if is_billing_violation(fb_provider, fb_model, _fb_bu):
            logger.error("{MARKER}: skip fallback %s/%s", fb_provider, fb_model)
            unavailable.add(fb_key)
            return agent._try_activate_fallback(reason)
    except Exception as _bill_exc:
        logger.warning("{MARKER} fallback check error: %s", _bill_exc)
        _ml = (fb_model or "").lower()
        if fb_provider == "openrouter" and any(
            x in _ml for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus")
        ):
            unavailable.add(fb_key)
            return agent._try_activate_fallback(reason)
'''
    if anchor not in t:
        print(f"WARN: fallback anchor missing in {path}", file=sys.stderr)
        return False
    path.write_text(t.replace(anchor, inject, 1), encoding="utf-8")
    print(f"PATCHED {path}")
    return True


def patch_model_switch(root: Path) -> bool:
    path = root / "hermes_cli" / "model_switch.py"
    t = path.read_text(encoding="utf-8")
    if "_carrier_billing_block" in t and MARKER in t:
        print(f"OK already: {path}")
        return False
    changed = False
    if "_carrier_billing_block" not in t:
        anchor = '''    resolved_alias = ""
    new_model = raw_input.strip()
    target_provider = current_provider
    resolved_moa_preset = False
'''
        inject = f'''    resolved_alias = ""
    new_model = raw_input.strip()
    target_provider = current_provider
    resolved_moa_preset = False

    def _carrier_billing_block(provider: str, model: str, base_url: str = "") -> str | None:
        """{MARKER} — refuse OR+Claude/Grok at /model switch."""
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _bp = _Path.home() / "carrier_hermes" / "scripts"
            if str(_bp) not in _sys.path:
                _sys.path.insert(0, str(_bp))
            from or_billing_policy import violation_for_route
            return violation_for_route(
                provider=provider, model=model, base_url=base_url, where="model_switch"
            )
        except Exception:
            pl, ml, bl = (provider or "").lower(), (model or "").lower(), (base_url or "").lower()
            if "openrouter" in pl or "openrouter" in bl:
                if any(x in ml for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus", "haiku")):
                    return f"model_switch: BILLING HARD DENY openrouter/{{model}}"
            return None
'''
        if anchor not in t:
            print(f"WARN: model_switch start anchor missing in {path}", file=sys.stderr)
        else:
            t = t.replace(anchor, inject, 1)
            changed = True

    if "_bill_err = _carrier_billing_block" not in t:
        # Gate every success=True return inside switch_model
        start = t.find("def switch_model(")
        if start < 0:
            print(f"WARN: switch_model not found in {path}", file=sys.stderr)
        else:
            m = re.search(r"\n\ndef ", t[start + 10 :])
            end = start + 10 + m.start() if m else len(t)
            head, body, tail = t[:start], t[start:end], t[end:]
            pattern = re.compile(
                r"(\n( +)return ModelSwitchResult\(\n\2    success=True,)"
            )

            def repl(match: re.Match) -> str:
                ind = match.group(2)
                gate = (
                    f"\n{ind}_bill_err = _carrier_billing_block(target_provider, new_model, \"\")\n"
                    f"{ind}if _bill_err:\n"
                    f"{ind}    return ModelSwitchResult(\n"
                    f"{ind}        success=False,\n"
                    f"{ind}        is_global=is_global,\n"
                    f"{ind}        error_message=_bill_err,\n"
                    f"{ind}    )\n"
                )
                return gate + match.group(1)

            new_body, n = pattern.subn(repl, body)
            if n:
                t = head + new_body + tail
                changed = True
                print(f"gated {n} success return(s) in model_switch")
            else:
                print(f"WARN: no success=True returns gated in {path}", file=sys.stderr)

    if changed:
        path.write_text(t, encoding="utf-8")
        print(f"PATCHED {path}")
    return changed


def main() -> int:
    root = find_hermes_agent()
    print(f"hermes-agent root: {root}")
    n = 0
    for fn in (patch_conversation_loop, patch_runtime_switch, patch_fallback, patch_model_switch):
        try:
            if fn(root):
                n += 1
        except Exception as e:
            print(f"ERROR in {fn.__name__}: {e}", file=sys.stderr)
    print(f"done — {n} file(s) newly patched")
    # Verify markers
    missing = []
    checks = [
        root / "agent" / "conversation_loop.py",
        root / "agent" / "agent_runtime_helpers.py",
        root / "agent" / "chat_completion_helpers.py",
        root / "hermes_cli" / "model_switch.py",
    ]
    for p in checks:
        if p.exists() and MARKER not in p.read_text(encoding="utf-8") and "_carrier_billing_block" not in p.read_text(encoding="utf-8"):
            missing.append(str(p))
    if missing:
        print("WARN incomplete patches:", *missing, file=sys.stderr)
        return 1
    print("verify OK — all refuse points present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""carrier-billing-guard — runtime HARD DENY for OpenRouter Claude/Grok/frontier.

Uses BaseException (not Exception) on block so Hermes middleware cannot
fail-open to the real provider. No HTTP request is made.

Policy: ~/carrier_hermes/scripts/or_billing_policy.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("hermes.plugins.carrier-billing-guard")

_POLICY = None
_POLICY_LOAD_TRIED = False


class BillingHardDenyBase(BaseException):
    """Not a subclass of Exception — bypasses middleware fail-open."""


def _load_policy():
    global _POLICY, _POLICY_LOAD_TRIED
    if _POLICY is not None or _POLICY_LOAD_TRIED:
        return _POLICY
    _POLICY_LOAD_TRIED = True
    roots = [Path.home() / "carrier_hermes" / "scripts"]
    env_root = os.environ.get("CARRIER_HERMES_ROOT")
    if env_root:
        roots.insert(0, Path(env_root) / "scripts")
    for root in roots:
        if not root.is_dir():
            continue
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            import or_billing_policy as pol  # type: ignore

            _POLICY = pol
            return _POLICY
        except Exception as exc:  # noqa: BLE001
            logger.error("carrier-billing-guard: import failed from %s: %s", root, exc)
    logger.error("carrier-billing-guard: or_billing_policy not found — fail-closed on OR+Claude/Grok")
    return None


def _route_from_kwargs(kwargs: dict) -> tuple[str, str, str]:
    provider = str(kwargs.get("provider") or "")
    model = str(kwargs.get("model") or "")
    base_url = str(kwargs.get("base_url") or "")
    request = kwargs.get("request")
    if isinstance(request, dict) and request.get("model"):
        model = str(request.get("model"))
    return provider, model, base_url


def _check(**kwargs: Any) -> str | None:
    provider, model, base_url = _route_from_kwargs(kwargs)
    pol = _load_policy()
    if pol is not None:
        if pol.is_billing_violation(provider, model, base_url):
            return pol.violation_message(provider, model, base_url)
        return None
    # Fail-closed if policy missing and route looks like OR + frontier family
    p, m, bu = provider.lower(), model.lower(), base_url.lower()
    if "openrouter" in p or "openrouter" in bu:
        if any(x in m for x in ("claude", "anthropic", "grok", "x-ai", "sonnet", "opus", "haiku", "fable")):
            return f"BILLING HARD DENY (policy missing): refused {provider}/{model}"
    return None


def on_llm_execution(**kwargs: Any) -> Any:
    err = _check(**kwargs)
    if err:
        logger.error("carrier-billing-guard BLOCKED (no network): %s", err)
        raise BillingHardDenyBase(err)
    return kwargs["next_call"](kwargs.get("request"))


def on_pre_api_request(**kwargs: Any) -> None:
    err = _check(**kwargs)
    if err:
        # Observer — hard block is llm_execution; log loudly if something slipped
        logger.error("carrier-billing-guard pre_api_request FORBIDDEN route: %s", err)


def register(ctx) -> None:
    ctx.register_middleware("llm_execution", on_llm_execution)
    ctx.register_hook("pre_api_request", on_pre_api_request)
    logger.info("carrier-billing-guard active: llm_execution hard deny + pre_api_request")

#!/usr/bin/env python3
"""Carrier Hermes — OpenRouter / metered-aggregator billing policy (SINGLE SOURCE OF TRUTH).

HARD RULE (Michael) — PERIOD, FULL STOP:
  Anthropic (Claude*) and xAI (Grok*) are SUBSCRIPTION / OAUTH ONLY.
    • provider ``anthropic``  → Claude Max OAuth
    • provider ``xai-oauth``  → SuperGrok OAuth

  OpenRouter and every other metered aggregator MUST NEVER carry:
    • any Anthropic/Claude model (any slug, any date, any org prefix)
    • any xAI/Grok model
    • any other non-allowlisted expensive frontier (GPT-4/5, Gemini Pro, …)

  Enforcement is DEFAULT-DENY on metered transports:
    OpenRouter (and openrouter.ai base_url, together, fireworks, …) may ONLY
    run models on OR_ALLOWED_EXACT / OR_ALLOWED_PREFIXES (DeepSeek flash/chat,
    Gemini Flash/Lite, gpt-oss). Everything else is a hard billing violation.

Imported by:
  - billing_guard.py (config/env audit + --fix-*)
  - apply_bot_matrix.sh (write-time refuse)
  - billing_policy.py (compat shim)
  - sync_or_billing_guardrail.py (workspace allowlist push)
  - optional runtime plugin carrier-billing-guard
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# OpenRouter ALLOWLIST — only these may ride OR / metered aggregators.
# ---------------------------------------------------------------------------
OR_ALLOWED_EXACT: frozenset[str] = frozenset(
    {
        "deepseek/deepseek-chat-v3-0324",
        "deepseek/deepseek-chat",
        "deepseek/deepseek-chat-v3.1",
        "deepseek/deepseek-v3.2",
        "deepseek/deepseek-v3.2-exp",
        "deepseek/deepseek-v3.1-terminus",
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash-0731",
        "deepseek/deepseek-v4-flash-vision-exp",
        "google/gemini-2.5-flash-lite",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-image",
        "google/gemini-3.1-flash-lite",
        "google/gemini-3.1-flash-lite-preview",
        "google/gemini-3.1-flash-lite-image",
        "google/gemini-3.5-flash-lite",
        "google/gemini-3.7-flash",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-safeguard-20b",
    }
)

OR_ALLOWED_PREFIXES: tuple[str, ...] = (
    "deepseek/deepseek-chat",
    "deepseek/deepseek-v3",
    "deepseek/deepseek-v4-flash",
    "google/gemini-2.5-flash",
    "google/gemini-3.1-flash-lite",
    "google/gemini-3.5-flash-lite",
    "google/gemini-3.7-flash",
    "openai/gpt-oss-",
)

# Belt-and-suspenders needles (even if someone widens the allowlist by mistake)
FORBIDDEN_OR_NEEDLES: tuple[str, ...] = (
    "anthropic/",
    "anthropic.",
    "claude-",
    "claude/",
    "/claude",
    "claude",
    "sonnet",
    "opus",
    "haiku",
    "fable",
    "x-ai/",
    "xai/",
    "/xai",
    "grok-",
    "grok/",
    "/grok",
    "grok",
    # OpenAI frontier (NOT gpt-oss)
    "openai/gpt-4",
    "openai/gpt-5",
    "openai/gpt-3.5",
    "openai/o1",
    "openai/o3",
    "openai/o4",
    "openai/chatgpt",
    "openai/codex",
    "openai/computer-use",
    "google/gemini-2.5-pro",
    "google/gemini-3-pro",
    "google/gemini-3.5-pro",
    "google/gemini-1.5-pro",
    "google/gemini-pro",
    "meta-llama/llama-4",
    "perplexity/",
    "cohere/command-r-plus",
    "mistralai/mistral-large",
    "mistralai/mistral-medium",
    "qwen/qwen-max",
    "moonshotai/kimi-k2",
)

# Family regex — absolute Anthropic/Grok deny on metered (cannot be "forgot needle")
_ANTHROPIC_FAMILY_RE = re.compile(
    r"anthropic|\bclaude\b|\bsonnet\b|\bopus\b|\bhaiku\b|\bfable\b",
    re.I,
)
_GROK_FAMILY_RE = re.compile(
    r"\bgrok\b|\bx-ai\b|(^|/)xai(/|$)|(^|/)x-ai(/|$)",
    re.I,
)

METERED_PROVIDERS: frozenset[str] = frozenset(
    {
        "openrouter",
        "openrouter-free",
        "open-router",
        "open_router",
        "together",
        "fireworks",
        "groq",
        "deepinfra",
        "novita",
        "siliconflow",
        "ai-gateway",
        "vercel",
        "opencode",
        "opencode-zen",
        "opencode-free",
        "kilocode",
        "nvidia",
        "huggingface",
        "bedrock",
        "openai",
        "openai-key",
    }
)

FORBIDDEN_API_KEY_PROVIDERS: frozenset[str] = frozenset(
    {"xai", "grok", "x-ai", "x_ai", "openai", "openai-key"}
)

OPENROUTER_BASE_URL_NEEDLES: tuple[str, ...] = (
    "openrouter.ai",
    "openrouter.com",
)

FORBIDDEN_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_KEY",
    "CLAUDE_API_KEY",
    "CLAUDE_API_TOKEN",
    "XAI_API_KEY",
    "XAI_KEY",
    "XAI_API_TOKEN",
    "GROK_API_KEY",
    "GROK_KEY",
    "OPENAI_API_KEY",
    "OPENAI_KEY",
    "OPENAI_API_TOKEN",
    "OPENAI_AUTH_TOKEN",
)

# Providers that are subscription/OAuth only — no api_key, no base_url allowed.
SUBSCRIPTION_ONLY_PROVIDERS: frozenset[str] = frozenset(
    {"anthropic", "xai-oauth", "openai-codex", "openai-oauth"}
)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def normalize_model_slug(model: Any) -> str:
    m = str(model or "").strip()
    low = m.lower()
    if low.startswith("openrouter/"):
        m = m[len("openrouter/") :]
    elif low.startswith("openrouter:"):
        m = m[len("openrouter:") :]
    return m


def is_openrouter_transport(provider: Any = None, base_url: Any = None) -> bool:
    p = _norm(provider)
    bu = _norm(base_url)
    if p in METERED_PROVIDERS or p.startswith("openrouter"):
        return True
    if any(n in bu for n in OPENROUTER_BASE_URL_NEEDLES):
        return True
    # composite provider field
    if "openrouter" in p:
        return True
    return False


def is_or_allowlisted_model(model: Any) -> bool:
    m = _norm(normalize_model_slug(model))
    if not m:
        return False
    base = m.split(":")[0]
    if m in OR_ALLOWED_EXACT or base in OR_ALLOWED_EXACT:
        return True
    return any(m.startswith(pref) or base.startswith(pref) for pref in OR_ALLOWED_PREFIXES)


def is_anthropic_family_model(model: Any) -> bool:
    m = normalize_model_slug(model)
    return bool(m and _ANTHROPIC_FAMILY_RE.search(m))


def is_grok_family_model(model: Any) -> bool:
    m = normalize_model_slug(model)
    return bool(m and _GROK_FAMILY_RE.search(m))


def is_anthropic_or_grok_model(model: Any) -> bool:
    return is_anthropic_family_model(model) or is_grok_family_model(model)


def has_forbidden_frontier_needle(model: Any) -> bool:
    m = _norm(normalize_model_slug(model))
    if not m:
        return False
    if m.startswith("openai/gpt-oss"):
        return False
    # family regex first (absolute)
    if is_anthropic_or_grok_model(m):
        return True
    return any(n in m for n in FORBIDDEN_OR_NEEDLES)


def is_billing_violation(
    provider: Any = None,
    model: Any = None,
    base_url: Any = None,
) -> bool:
    """True if this route must never execute."""
    p = _norm(provider)
    m = str(model or "").strip()

    if p in FORBIDDEN_API_KEY_PROVIDERS:
        return True

    # Composite strings stuffed into provider or model
    for blob in (provider, model, base_url):
        b = _norm(blob)
        if b.startswith("openrouter/") or b.startswith("openrouter:"):
            rest = normalize_model_slug(blob)
            if is_anthropic_or_grok_model(rest) or not is_or_allowlisted_model(rest):
                # openrouter/deepseek/... is allowlisted; openrouter/anthropic/... is not
                if is_anthropic_or_grok_model(rest) or (
                    rest and not is_or_allowlisted_model(rest) and is_openrouter_transport("openrouter")
                ):
                    if is_anthropic_or_grok_model(rest) or has_forbidden_frontier_needle(rest):
                        return True
                    if rest and not is_or_allowlisted_model(rest):
                        return True

    metered = is_openrouter_transport(provider, base_url)
    if not metered:
        # Direct anthropic / xai-oauth OK
        # But anthropic + openrouter base_url already metered=True
        return False

    # ABSOLUTE: Claude/Grok family never on metered — even if someone adds them to allowlist
    if is_anthropic_or_grok_model(m):
        return True

    # DEFAULT DENY: allowlist only
    if not is_or_allowlisted_model(m):
        return True
    if has_forbidden_frontier_needle(m):
        return True
    return False


def violation_message(
    provider: Any = None,
    model: Any = None,
    base_url: Any = None,
) -> str:
    return (
        f"BILLING HARD DENY: refused {provider or '?'}/{model or '?'} "
        f"(base_url={base_url or ''}). "
        "PERIOD FULL STOP: Anthropic/Claude and xAI/Grok MUST NEVER ride OpenRouter "
        "or any metered aggregator — OAuth only (anthropic / xai-oauth). "
        "OpenRouter is ALLOWLIST-ONLY: DeepSeek flash/chat, Gemini Flash/Lite, gpt-oss."
    )


def violation_for_route(
    *,
    provider: Any = None,
    model: Any = None,
    base_url: Any = None,
    where: str = "route",
) -> str | None:
    if is_billing_violation(provider, model, base_url):
        return f"{where}: {violation_message(provider, model, base_url)}"
    return None


def check_alias_value(alias_key: str, value: Any, where: str = "alias") -> str | None:
    vs = str(value or "").strip()
    if not vs:
        return None
    low = vs.lower()
    if low.startswith("openrouter/") or low.startswith("openrouter:"):
        rest = normalize_model_slug(vs)
        if is_billing_violation("openrouter", rest):
            return f"{where}: alias {alias_key!r} -> {vs!r} FORBIDDEN (OR must never carry Claude/Grok/frontier)"
    # provider-qualified without openrouter prefix but looks like org/model on OR primary — handled by caller
    if is_anthropic_or_grok_model(vs) and "openrouter" in low:
        return f"{where}: alias {alias_key!r} -> {vs!r} FORBIDDEN"
    return None


def scrub_aliases(aliases: dict) -> list[str]:
    logs: list[str] = []
    if not isinstance(aliases, dict):
        return logs
    for k, v in list(aliases.items()):
        err = check_alias_value(str(k), v, "aliases")
        if err:
            del aliases[k]
            logs.append(f"REMOVED {err}")
    return logs


def scrub_fallback_providers(entries: list) -> tuple[list, list[str]]:
    logs: list[str] = []
    cleaned: list = []
    if not isinstance(entries, list):
        return [], logs
    for i, fb in enumerate(entries):
        if not isinstance(fb, dict):
            cleaned.append(fb)
            continue
        err = violation_for_route(
            provider=fb.get("provider"),
            model=fb.get("model") or fb.get("default"),
            base_url=fb.get("base_url"),
            where=f"fallback_providers[{i}]",
        )
        if err:
            logs.append(f"REMOVED {err}")
            continue
        cleaned.append(fb)
    return cleaned, logs


def filter_fallback_entries(entries: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        p = str(e.get("provider") or "")
        m = str(e.get("model") or "")
        bu = str(e.get("base_url") or "")
        if is_billing_violation(p, m, bu):
            raise ValueError(violation_message(p, m, bu))
        out.append(dict(e))
    return out


def assert_openrouter_model_allowed(model: str, *, context: str = "openrouter") -> None:
    if is_billing_violation("openrouter", model):
        raise ValueError(violation_message("openrouter", model))


def walk_config_routes(cfg: Any, where: str = "config") -> list[str]:
    """Deep-scan YAML config for any forbidden metered Claude/Grok/frontier routes."""
    errs: list[str] = []
    if not isinstance(cfg, dict):
        return errs

    def consider(prov, model, base_url, loc: str) -> None:
        err = violation_for_route(provider=prov, model=model, base_url=base_url, where=loc)
        if err:
            errs.append(err)

    model = cfg.get("model")
    if isinstance(model, dict):
        consider(
            model.get("provider"),
            model.get("default") or model.get("model") or model.get("name"),
            model.get("base_url") or cfg.get("base_url"),
            f"{where}.model",
        )
        fb = model.get("fallback")
        if isinstance(fb, dict):
            consider(
                fb.get("provider"),
                fb.get("model") or fb.get("default"),
                fb.get("base_url") or model.get("base_url"),
                f"{where}.model.fallback",
            )
        elif isinstance(fb, str) and fb:
            if fb.lower().startswith("openrouter"):
                consider("openrouter", normalize_model_slug(fb), None, f"{where}.model.fallback")
            else:
                consider(model.get("provider"), fb, model.get("base_url"), f"{where}.model.fallback")
        aliases = model.get("aliases")
        if isinstance(aliases, dict):
            for k, v in aliases.items():
                err = check_alias_value(str(k), v, where)
                if err:
                    errs.append(err)

    for i, fb in enumerate(cfg.get("fallback_providers") or []):
        if isinstance(fb, dict):
            consider(
                fb.get("provider"),
                fb.get("model") or fb.get("default"),
                fb.get("base_url"),
                f"{where}.fallback_providers[{i}]",
            )
        elif isinstance(fb, str):
            consider(None, fb, None, f"{where}.fallback_providers[{i}]")

    for pool_key in ("providers", "provider_pool", "credential_pool", "models", "moa", "aux", "auxiliary"):
        pool = cfg.get(pool_key)
        if isinstance(pool, dict):
            for name, entry in pool.items():
                if isinstance(entry, dict):
                    consider(
                        entry.get("provider") or name,
                        entry.get("model") or entry.get("default") or entry.get("name"),
                        entry.get("base_url") or entry.get("api_base"),
                        f"{where}.{pool_key}.{name}",
                    )
                elif isinstance(entry, list):
                    for i, item in enumerate(entry):
                        if isinstance(item, dict):
                            consider(
                                item.get("provider"),
                                item.get("model") or item.get("default"),
                                item.get("base_url"),
                                f"{where}.{pool_key}.{name}[{i}]",
                            )
        elif isinstance(pool, list):
            for i, entry in enumerate(pool):
                if isinstance(entry, dict):
                    consider(
                        entry.get("provider"),
                        entry.get("model") or entry.get("default"),
                        entry.get("base_url") or entry.get("api_base"),
                        f"{where}.{pool_key}[{i}]",
                    )

    def deep(obj: Any, path: str, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(obj, dict):
            keys = {str(k).lower() for k in obj}
            if keys & {"provider", "base_url", "api_base", "api_base_url"}:
                consider(
                    obj.get("provider"),
                    obj.get("model") or obj.get("default") or obj.get("model_name") or obj.get("model_id"),
                    obj.get("base_url") or obj.get("api_base") or obj.get("api_base_url"),
                    path,
                )
            for k, v in obj.items():
                deep(v, f"{path}.{k}", depth + 1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                deep(v, f"{path}[{i}]", depth + 1)

    deep(cfg, where)

    seen: set[str] = set()
    out: list[str] = []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def or_guardrail_allowed_models() -> list[str]:
    models = sorted(OR_ALLOWED_EXACT)
    for x in (
        "google/gemini-2.5-flash-lite:batch",
        "google/gemini-2.5-flash:batch",
        "google/gemini-3.7-flash:batch",
        "google/gemini-3.1-flash-lite:batch",
        "google/gemini-3.5-flash-lite:batch",
    ):
        if x not in models:
            models.append(x)
    return models


def self_test() -> None:
    # MUST BLOCK — Claude/Grok on OpenRouter (any shape)
    blockers = [
        ("openrouter", "anthropic/claude-sonnet-4-6", None),
        ("openrouter", "anthropic/claude-sonnet-5", None),
        ("openrouter", "claude-sonnet-4-6", None),
        ("openrouter", "claude-opus-4", None),
        ("openrouter", "x-ai/grok-4.5", None),
        ("openrouter", "x-ai/grok-4", None),
        ("openrouter", "grok-4.5", None),
        ("OPENROUTER", "Grok-beta", None),
        ("openrouter", "google/gemini-2.5-pro", None),
        ("openrouter", "openai/gpt-4o", None),
        ("openrouter", "openai/o1-pro", None),
        ("custom", "claude-sonnet-4-6", "https://openrouter.ai/api/v1"),
        ("xai", "grok-4.5", None),
        ("anthropic", "claude-sonnet-4-6", "https://openrouter.ai/api/v1"),
        ("together", "anthropic/claude-3.5-sonnet", None),
    ]
    for p, m, bu in blockers:
        assert is_billing_violation(p, m, bu), f"expected block {p}/{m} bu={bu}"

    assert check_alias_value("s", "openrouter/x-ai/grok-4.5")
    assert check_alias_value("q", "openrouter/anthropic/claude-sonnet-4-6")

    # MUST ALLOW
    allow = [
        ("openrouter", "deepseek/deepseek-v4-flash-0731", None),
        ("openrouter", "deepseek/deepseek-chat-v3-0324", None),
        ("openrouter", "google/gemini-2.5-flash-lite", None),
        ("openrouter", "google/gemini-3.7-flash", None),
        ("openrouter", "openai/gpt-oss-120b", None),
        ("anthropic", "claude-sonnet-4-6", None),
        ("anthropic", "claude-sonnet-5", None),
        ("xai-oauth", "grok-4.5", None),
        ("xai-oauth", "grok-4.6", None),
    ]
    for p, m, bu in allow:
        assert not is_billing_violation(p, m, bu), f"false positive {p}/{m}: {violation_message(p,m,bu)}"

    # --- OpenAI guard probes ---
    # MUST BLOCK (API key / metered paths)
    assert is_billing_violation("openai", "gpt-4o", None), "bare openai provider must block"
    assert is_billing_violation("openai-key", "gpt-4o", None), "openai-key provider must block"
    assert is_billing_violation("openrouter", "openai/gpt-4o", None), "OR gpt-4o must block"
    assert is_billing_violation("openrouter", "openai/o1", None), "OR o1 must block"
    assert "OPENAI_API_KEY" in FORBIDDEN_ENV_KEYS
    assert "OPENAI_KEY" in FORBIDDEN_ENV_KEYS
    # MUST ALLOW (OAuth subscription path)
    assert not is_billing_violation("openai-oauth", "gpt-4o-mini", None), "openai-oauth cheap must allow"
    assert not is_billing_violation("openai-oauth", "gpt-4o", None), "openai-oauth mid must allow"
    assert not is_billing_violation("openai-oauth", "o3", None), "openai-oauth frontier must allow"
    assert not is_billing_violation("openrouter", "openai/gpt-oss-120b", None), "gpt-oss must allow"

    # Deep walk
    cfg = {
        "model": {
            "provider": "openrouter",
            "default": "anthropic/claude-sonnet-5",
            "aliases": {"bad": "openrouter/x-ai/grok-4"},
        },
        "fallback_providers": [{"provider": "openrouter", "model": "x-ai/grok-4.5"}],
    }
    errs = walk_config_routes(cfg, "evil")
    assert len(errs) >= 2, errs


if __name__ == "__main__":
    self_test()
    print("or_billing_policy: self_test OK (OR allowlist + absolute Claude/Grok deny)")

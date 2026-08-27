"""Tests: OpenAI OAuth billing guard — no API keys, subscription-only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from or_billing_policy import is_billing_violation, FORBIDDEN_ENV_KEYS, METERED_PROVIDERS, FORBIDDEN_API_KEY_PROVIDERS


def test_openai_api_key_provider_blocked():
    assert is_billing_violation("openai", "gpt-4o", None), "bare openai (API key path) must block"


def test_openai_key_provider_blocked():
    assert is_billing_violation("openai-key", "gpt-4o", None), "openai-key must block"


def test_or_openai_frontier_blocked():
    assert is_billing_violation("openrouter", "openai/gpt-4o", None), "OR gpt-4o must block"
    assert is_billing_violation("openrouter", "openai/o1", None), "OR o1 must block"
    assert is_billing_violation("openrouter", "openai/o3", None), "OR o3 must block"


def test_openai_oauth_allowed():
    assert not is_billing_violation("openai-oauth", "gpt-4o-mini", None), "openai-oauth cheap must allow"
    assert not is_billing_violation("openai-oauth", "gpt-4o", None), "openai-oauth mid must allow"
    assert not is_billing_violation("openai-oauth", "o3", None), "openai-oauth frontier must allow"


def test_or_gpt_oss_allowed():
    assert not is_billing_violation("openrouter", "openai/gpt-oss-120b", None), "gpt-oss must allow"


def test_forbidden_env_keys_present():
    for key in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_API_TOKEN", "OPENAI_AUTH_TOKEN"):
        assert key in FORBIDDEN_ENV_KEYS, f"{key} must be in FORBIDDEN_ENV_KEYS"


def test_openai_in_metered_providers():
    assert "openai" in METERED_PROVIDERS, "bare openai must be in METERED_PROVIDERS"
    assert "openai-key" in METERED_PROVIDERS


def test_openai_oauth_NOT_metered():
    assert "openai-oauth" not in METERED_PROVIDERS, "openai-oauth is subscription, not metered"


def test_openai_in_forbidden_api_key_providers():
    assert "openai" in FORBIDDEN_API_KEY_PROVIDERS
    assert "openai-key" in FORBIDDEN_API_KEY_PROVIDERS


def test_openai_oauth_NOT_forbidden_api_key_provider():
    assert "openai-oauth" not in FORBIDDEN_API_KEY_PROVIDERS

"""
carrier_provider_driver.py — Driver SPI (Service Provider Interface) for carrier fleet AI providers.

Translated from OpenMausBot's contracts.ts + drivers/claude.ts patterns.
Defines a Python Protocol so any provider can be swapped without touching
task dispatch logic.

Key rule from upstream:
  "Token counting: ONLY count from turn_complete event, never accumulate intermediates."

Usage:
    from scripts.carrier_provider_driver import DRIVERS, AnthropicOAuthDriver

    driver = DRIVERS["anthropic"]
    result = driver.route(messages=[{"role": "user", "content": "Hello"}], context={})
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

# ── Token usage model ──────────────────────────────────────────────────────────
# RULE: Only count tokens reported in the turn_complete event.
# Never accumulate from streaming intermediates — they're unreliable and
# lead to double-counting. This mirrors OpenMausBot's contracts.ts intent.


class TokenUsage:
    """Canonical token count from a single completed turn."""

    def __init__(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        provider: str = "",
        model: str = "",
        turn_id: str = "",
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.provider = provider
        self.model = model
        self.turn_id = turn_id

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "provider": self.provider,
            "model": self.model,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_turn_complete_event(cls, event: dict) -> "TokenUsage":
        """
        Parse token usage ONLY from a turn_complete event dict.
        Never call this from streaming chunk events.
        """
        usage = event.get("usage", {})
        return cls(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
            provider=event.get("provider", ""),
            model=event.get("model", ""),
            turn_id=event.get("turn_id", ""),
        )


# ── Provider Driver Protocol ───────────────────────────────────────────────────

@runtime_checkable
class ProviderDriver(Protocol):
    """
    SPI contract every provider driver must satisfy.

    Mirrors OpenMausBot contracts.ts ProviderDriver interface, translated to
    Python duck-typing via Protocol.
    """

    @property
    def driver_kind(self) -> str:
        """Unique slug for this driver (e.g. 'anthropic', 'xai', 'ollama')."""
        ...

    def route(self, messages: list[dict], context: dict) -> dict:
        """
        Send messages to the provider and return a completion.

        Returns:
            {
                "content": str,           # assistant text
                "turn_id": str,
                "model": str,
                "usage": TokenUsage,      # from turn_complete ONLY
                "raw": dict,              # raw provider response
            }
        """
        ...

    def on_turn_complete(self, usage: TokenUsage) -> dict:
        """
        Called once per completed turn with the final token usage.
        Use this to update billing ledger, emit metrics, etc.

        Returns a dict with any side-effect metadata (e.g. ledger entry id).

        RULE: Never accumulate tokens from streaming events — only call
        this once per turn with the turn_complete usage object.
        """
        ...

    def on_billing_violation(self, provider: str, model: str) -> None:
        """
        Called when a billing limit or policy violation is detected.
        Should block/throw rather than silently dropping the request.
        """
        ...


# ── Anthropic OAuth driver ─────────────────────────────────────────────────────

class AnthropicOAuthDriver:
    """
    Claude via the `claude` CLI in OAuth (Claude Max subscription) mode.

    Uses subprocess to invoke `claude --output-format stream-json` so the
    transport is identical to what the fleet bots actually run. Token counting
    is taken exclusively from the final `result` event (turn_complete analog).
    """

    driver_kind = "anthropic"
    DEFAULT_MODEL = "claude-sonnet-4-5"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        cli_path: str = "claude",
        max_tokens: int = 8192,
    ):
        self.model = model
        self.cli_path = cli_path
        self.max_tokens = max_tokens

    def _find_cli(self) -> str:
        import shutil
        found = shutil.which(self.cli_path)
        if not found:
            raise RuntimeError(
                f"Claude CLI not found at '{self.cli_path}'. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )
        return found

    def route(self, messages: list[dict], context: dict) -> dict:
        """
        Route messages through the Claude CLI.

        Streams JSON events, extracts the final `result` event for usage.
        Does NOT accumulate tokens from intermediate `content_block_delta`
        or `message_delta` events.
        """
        cli = self._find_cli()
        # Build prompt from messages (simplified: last user message as stdin)
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if c.get("type") == "text"
                )
            prompt_parts.append(f"{role}: {content}")
        prompt = "\n".join(prompt_parts)

        model = context.get("model", self.model)
        cmd = [
            cli,
            "--model", model,
            "--output-format", "stream-json",
            "--max-turns", "1",
            "-p", prompt,
        ]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "CLAUDE_CODE_AUTO_APPROVE_EVERYTHING": "0"},
            )
        except subprocess.TimeoutExpired:
            return {"content": "", "error": "timeout", "usage": TokenUsage(provider=self.driver_kind, model=model)}
        except FileNotFoundError:
            return {"content": "", "error": "cli_not_found", "usage": TokenUsage(provider=self.driver_kind, model=model)}

        # Parse stream-json output — only look at the `result` event
        content = ""
        usage = TokenUsage(provider=self.driver_kind, model=model)
        turn_id = ""

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")
            if event_type == "result":
                # This is the turn_complete analog — the ONLY place we read tokens
                content = event.get("result", "")
                raw_usage = event.get("usage", {})
                turn_id = event.get("session_id", "")
                usage = TokenUsage(
                    input_tokens=raw_usage.get("input_tokens", 0),
                    output_tokens=raw_usage.get("output_tokens", 0),
                    cache_read_tokens=raw_usage.get("cache_read_input_tokens", 0),
                    cache_write_tokens=raw_usage.get("cache_creation_input_tokens", 0),
                    provider=self.driver_kind,
                    model=model,
                    turn_id=turn_id,
                )
                # Do NOT read tokens from any other event type

        return {
            "content": content,
            "turn_id": turn_id,
            "model": model,
            "usage": usage,
            "raw": {"stdout": proc.stdout[-2000:], "returncode": proc.returncode},
        }

    def on_turn_complete(self, usage: TokenUsage) -> dict:
        """Log token usage to carrier billing ledger."""
        entry = {
            "event": "turn_complete",
            "provider": usage.provider,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "total_tokens": usage.total_tokens,
            "turn_id": usage.turn_id,
            "timestamp": time.time(),
        }
        # Append to ledger file (non-blocking; errors don't fail the turn)
        try:
            ledger_path = Path(os.environ.get(
                "HERMES_HOME", "C:/Users/micha/AppData/Local/hermes"
            )) / "carrier" / "billing_ledger.jsonl"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(ledger_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            print(f"[AnthropicOAuthDriver] Ledger write failed (non-fatal): {exc}")
        return entry

    def on_billing_violation(self, provider: str, model: str) -> None:
        raise RuntimeError(
            f"Billing violation: provider={provider} model={model}. "
            "Request blocked by carrier billing policy. "
            "Check C:/Users/micha/AppData/Local/hermes/carrier/billing_ledger.jsonl"
        )


# ── xAI (Grok) OAuth driver ───────────────────────────────────────────────────

class XaiOAuthDriver:
    """
    Grok via xAI API with OAuth token from environment/Doppler.

    Mirrors AnthropicOAuthDriver structure. Token counting from
    the API response object only (the single final completion, not streamed chunks).
    """

    driver_kind = "xai"
    DEFAULT_MODEL = "grok-3"
    API_BASE = "https://api.x.ai/v1"

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 8192):
        self.model = model
        self.max_tokens = max_tokens

    def _get_api_key(self) -> str:
        key = os.environ.get("XAI_API_KEY")
        if key:
            return key
        try:
            result = subprocess.run(
                ["doppler", "secrets", "get", "XAI_API_KEY", "--plain"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        raise RuntimeError("XAI_API_KEY not found in env or Doppler")

    def route(self, messages: list[dict], context: dict) -> dict:
        import urllib.request
        import urllib.error

        model = context.get("model", self.model)
        try:
            api_key = self._get_api_key()
        except RuntimeError as exc:
            return {"content": "", "error": str(exc), "usage": TokenUsage(provider=self.driver_kind, model=model)}

        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }).encode()

        req = urllib.request.Request(
            f"{self.API_BASE}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return {"content": "", "error": f"HTTP {exc.code}", "usage": TokenUsage(provider=self.driver_kind, model=model)}
        except Exception as exc:
            return {"content": "", "error": str(exc), "usage": TokenUsage(provider=self.driver_kind, model=model)}

        # Extract from the single completion object — turn_complete analog
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        raw_usage = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=raw_usage.get("prompt_tokens", 0),
            output_tokens=raw_usage.get("completion_tokens", 0),
            provider=self.driver_kind,
            model=model,
            turn_id=data.get("id", ""),
        )
        return {
            "content": content,
            "turn_id": data.get("id", ""),
            "model": model,
            "usage": usage,
            "raw": data,
        }

    def on_turn_complete(self, usage: TokenUsage) -> dict:
        entry = {
            "event": "turn_complete",
            "provider": usage.provider,
            "model": usage.model,
            "total_tokens": usage.total_tokens,
            "turn_id": usage.turn_id,
            "timestamp": time.time(),
        }
        return entry

    def on_billing_violation(self, provider: str, model: str) -> None:
        raise RuntimeError(f"Billing violation: xAI provider={provider} model={model}")


# ── Ollama local driver ────────────────────────────────────────────────────────

class OllamaLocalDriver:
    """
    Local Ollama inference — no billing, no OAuth.

    Uses Ollama's HTTP API (default localhost:11434).
    Token counting from the final response's `eval_count` / `prompt_eval_count`.
    """

    driver_kind = "ollama"
    DEFAULT_MODEL = "mistral"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def route(self, messages: list[dict], context: dict) -> dict:
        import urllib.request

        model = context.get("model", self.model)
        body = json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            return {"content": "", "error": str(exc), "usage": TokenUsage(provider=self.driver_kind, model=model)}

        content = data.get("message", {}).get("content", "")
        # Turn-complete token counts from final response object
        usage = TokenUsage(
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            provider=self.driver_kind,
            model=data.get("model", model),
            turn_id=str(data.get("created_at", "")),
        )
        return {
            "content": content,
            "turn_id": usage.turn_id,
            "model": usage.model,
            "usage": usage,
            "raw": data,
        }

    def on_turn_complete(self, usage: TokenUsage) -> dict:
        # Local — no billing needed, just log
        return {"event": "turn_complete", "provider": "ollama", "model": usage.model, "total_tokens": usage.total_tokens}

    def on_billing_violation(self, provider: str, model: str) -> None:
        # Ollama is local — no billing violations
        pass


# ── Driver registry ────────────────────────────────────────────────────────────

DRIVERS: dict[str, ProviderDriver] = {
    "anthropic": AnthropicOAuthDriver(),
    "xai": XaiOAuthDriver(),
    "ollama": OllamaLocalDriver(),
}


def get_driver(provider_kind: str) -> ProviderDriver:
    """Look up a driver by kind slug. Raises KeyError if not registered."""
    if provider_kind not in DRIVERS:
        raise KeyError(
            f"Unknown provider '{provider_kind}'. "
            f"Available: {list(DRIVERS.keys())}"
        )
    return DRIVERS[provider_kind]


# ── Smoke test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("DRIVERS:", list(DRIVERS.keys()))
    for name, driver in DRIVERS.items():
        assert isinstance(driver, ProviderDriver), f"{name} does not satisfy ProviderDriver protocol"
        print(f"  {name}: {type(driver).__name__} ✓")
    print("Protocol conformance check passed")

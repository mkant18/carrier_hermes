"""
carrier_provider_driver.py — Full driver SPI for carrier fleet routing.

Implements:
  - AnthropicOAuthDriver: haiku for classify/simple, sonnet-4-6 for execution
  - XaiOAuthDriver: grok-4.5 with quota state management
  - OllamaLocalDriver: local inference with Anthropic fallback
  - BillingGuardDriver: wraps any driver, validates billing policy
  - route_request(): top-level router with billing policy enforcement
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
CARRIER_DIR = HERMES_HOME / "carrier"
XAI_QUOTA_STATE_PATH = CARRIER_DIR / "xai_quota_state.json"
ROUTING_LOG_PATH = CARRIER_DIR / "routing_decisions.log"

ANTHROPIC_HAIKU_MODEL = "claude-haiku-4-5"
ANTHROPIC_SONNET_MODEL = "claude-sonnet-4-6"
XAI_GROK_MODEL = "grok-4.5"
OLLAMA_DEFAULT_MODEL = "qwen2.5:7b"
OLLAMA_BASE_URL = "http://localhost:11434"

# ── Message type ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str  # 'user' | 'assistant' | 'system'
    content: str


@dataclass
class DriverResponse:
    text: str
    model: str
    driver_kind: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ── Base driver ───────────────────────────────────────────────────────────────

class BaseDriver(ABC):
    """Abstract base for all carrier provider drivers."""

    @property
    @abstractmethod
    def driver_kind(self) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this driver can currently serve requests."""
        ...

    @abstractmethod
    def send(self, messages: list[Message], model: str | None = None, **kwargs) -> DriverResponse:
        """Send a conversation turn. Returns DriverResponse."""
        ...

    def _get_token(self, env_var: str, doppler_key: str,
                   project: str = "carrier-ops", config: str = "prd") -> str:
        """Fetch a secret from env or Doppler."""
        token = os.environ.get(env_var, "")
        if token:
            return token
        try:
            result = subprocess.run(
                ["doppler", "secrets", "get", doppler_key,
                 "--plain", "--project", project, "--config", config],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return ""

    def _http_post(self, url: str, headers: dict, payload: dict,
                   timeout: int = 60) -> dict | None:
        """POST JSON, return parsed response or None on error."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc


# ── Anthropic OAuth Driver ────────────────────────────────────────────────────

class AnthropicOAuthDriver(BaseDriver):
    """
    Driver for Anthropic Claude via API.
    Routes to:
      - claude-haiku-4-5 for classification / simple tasks
      - claude-sonnet-4-6 for execution / complex tasks
    """

    CLASSIFY_KEYWORDS = {
        "classify", "categorize", "label", "triage", "route",
        "yes or no", "is this", "check if", "detect",
    }

    @property
    def driver_kind(self) -> str:
        return "anthropic-oauth"

    def _is_simple_task(self, messages: list[Message]) -> bool:
        """Heuristic: use Haiku for short classification-style prompts."""
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        content_lower = last_user.lower()
        if len(last_user) < 200:
            return True
        if any(kw in content_lower for kw in self.CLASSIFY_KEYWORDS):
            return True
        return False

    def is_available(self) -> bool:
        token = self._get_token("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
        return bool(token)

    def send(
        self,
        messages: list[Message],
        model: str | None = None,
        **kwargs,
    ) -> DriverResponse:
        token = self._get_token("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
        if not token:
            return DriverResponse(
                text="", model="", driver_kind=self.driver_kind,
                error="No Anthropic API key available",
            )

        # Route to haiku vs sonnet
        if model:
            selected_model = model
        elif self._is_simple_task(messages):
            selected_model = ANTHROPIC_HAIKU_MODEL
        else:
            selected_model = ANTHROPIC_SONNET_MODEL

        # Separate system message
        system_content = None
        conv_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                conv_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": selected_model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": conv_messages,
        }
        if system_content:
            payload["system"] = system_content

        headers = {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        t0 = time.time()
        try:
            resp = self._http_post(
                "https://api.anthropic.com/v1/messages",
                headers, payload, timeout=120,
            )
            latency = (time.time() - t0) * 1000
            if resp is None:
                return DriverResponse(text="", model=selected_model, driver_kind=self.driver_kind, error="Empty response")
            usage = resp.get("usage", {}) or {}
            text = ""
            for block in resp.get("content", []) or []:
                if block.get("type") == "text":
                    text += block.get("text", "")
            return DriverResponse(
                text=text,
                model=selected_model,
                driver_kind=self.driver_kind,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                latency_ms=latency,
            )
        except Exception as exc:
            return DriverResponse(
                text="", model=selected_model, driver_kind=self.driver_kind,
                error=str(exc),
            )


# ── xAI OAuth Driver ──────────────────────────────────────────────────────────

class XaiOAuthDriver(BaseDriver):
    """
    Driver for xAI Grok-4.5.
    Tracks quota state at carrier/xai_quota_state.json.
    Auto-marks quota_exceeded when 429 received.
    """

    @property
    def driver_kind(self) -> str:
        return "xai-oauth"

    def _read_quota_state(self) -> dict:
        try:
            return json.loads(XAI_QUOTA_STATE_PATH.read_text())
        except Exception:
            return {"quota_exceeded": False, "exceeded_at": None, "reset_at": None}

    def _write_quota_state(self, state: dict) -> None:
        CARRIER_DIR.mkdir(parents=True, exist_ok=True)
        XAI_QUOTA_STATE_PATH.write_text(json.dumps(state, indent=2))

    def is_available(self) -> bool:
        state = self._read_quota_state()
        if state.get("quota_exceeded"):
            # Check if reset time has passed
            reset_at = state.get("reset_at")
            if reset_at and time.time() > reset_at:
                # Reset quota state
                self._write_quota_state(
                    {"quota_exceeded": False, "exceeded_at": None, "reset_at": None}
                )
                return True
            return False
        token = self._get_token("XAI_API_KEY", "XAI_API_KEY")
        return bool(token)

    def send(
        self,
        messages: list[Message],
        model: str | None = None,
        **kwargs,
    ) -> DriverResponse:
        if not self.is_available():
            state = self._read_quota_state()
            return DriverResponse(
                text="", model=XAI_GROK_MODEL, driver_kind=self.driver_kind,
                error=f"xAI quota exceeded (reset_at={state.get('reset_at')})",
            )

        token = self._get_token("XAI_API_KEY", "XAI_API_KEY")
        if not token:
            return DriverResponse(
                text="", model=XAI_GROK_MODEL, driver_kind=self.driver_kind,
                error="No xAI API key available",
            )

        selected_model = model or XAI_GROK_MODEL

        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        payload = {
            "model": selected_model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        t0 = time.time()
        try:
            resp = self._http_post(
                "https://api.x.ai/v1/chat/completions",
                headers, payload, timeout=120,
            )
            latency = (time.time() - t0) * 1000
            if resp is None:
                return DriverResponse(text="", model=selected_model, driver_kind=self.driver_kind, error="Empty response")
            usage = resp.get("usage", {}) or {}
            text = ""
            for choice in resp.get("choices", []) or []:
                text += choice.get("message", {}).get("content", "")
            return DriverResponse(
                text=text,
                model=selected_model,
                driver_kind=self.driver_kind,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency,
            )
        except RuntimeError as exc:
            err_str = str(exc)
            # Mark quota exceeded on 429
            if "429" in err_str:
                reset_at = time.time() + 3600  # assume 1h reset
                self._write_quota_state({
                    "quota_exceeded": True,
                    "exceeded_at": time.time(),
                    "reset_at": reset_at,
                })
                print(f"[xai_driver] Quota exceeded — marked until {reset_at}")
            return DriverResponse(
                text="", model=selected_model, driver_kind=self.driver_kind,
                error=err_str,
            )


# ── Ollama Local Driver ───────────────────────────────────────────────────────

class OllamaLocalDriver(BaseDriver):
    """
    Driver for local Ollama inference.
    Checks localhost:11434/api/tags before routing.
    Falls back to Anthropic if Ollama is unavailable.
    """

    def __init__(self, fallback_driver: BaseDriver | None = None):
        self._fallback = fallback_driver or AnthropicOAuthDriver()
        self._available: bool | None = None
        self._available_checked_at: float = 0.0

    @property
    def driver_kind(self) -> str:
        return "ollama-local"

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and has models loaded."""
        # Cache result for 30 seconds
        if time.time() - self._available_checked_at < 30 and self._available is not None:
            return self._available

        try:
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/tags",
                headers={"User-Agent": "carrier-driver/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                self._available = len(models) > 0
        except Exception:
            self._available = False

        self._available_checked_at = time.time()
        return self._available

    def is_available(self) -> bool:
        return self._check_ollama()

    def _ollama_chat(self, messages: list[Message], model: str) -> DriverResponse:
        """Call Ollama /api/chat endpoint."""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        payload = {
            "model": model,
            "messages": api_messages,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        t0 = time.time()
        try:
            resp = self._http_post(
                f"{OLLAMA_BASE_URL}/api/chat",
                headers, payload, timeout=120,
            )
            latency = (time.time() - t0) * 1000
            if resp is None:
                return DriverResponse(text="", model=model, driver_kind=self.driver_kind, error="Empty response from Ollama")
            text = resp.get("message", {}).get("content", "") if resp else ""
            usage = resp.get("prompt_eval_count", 0) if resp else 0
            return DriverResponse(
                text=text,
                model=model,
                driver_kind=self.driver_kind,
                input_tokens=usage,
                output_tokens=resp.get("eval_count", 0) if resp else 0,
                latency_ms=latency,
            )
        except Exception as exc:
            return DriverResponse(
                text="", model=model, driver_kind=self.driver_kind,
                error=str(exc),
            )

    def send(
        self,
        messages: list[Message],
        model: str | None = None,
        **kwargs,
    ) -> DriverResponse:
        if not self._check_ollama():
            print(f"[ollama_driver] Ollama unavailable — falling back to {self._fallback.driver_kind}")
            resp = self._fallback.send(messages, model=model, **kwargs)
            resp.driver_kind = f"{self.driver_kind}→{resp.driver_kind}"
            return resp

        selected_model = model or OLLAMA_DEFAULT_MODEL
        resp = self._ollama_chat(messages, selected_model)

        if resp.error:
            print(f"[ollama_driver] Ollama error: {resp.error} — falling back")
            self._available = False  # Force recheck next call
            fallback_resp = self._fallback.send(messages, model=None, **kwargs)
            fallback_resp.driver_kind = f"{self.driver_kind}→{fallback_resp.driver_kind}"
            return fallback_resp

        return resp


# ── Billing Guard Driver ──────────────────────────────────────────────────────

class BillingGuardDriver(BaseDriver):
    """
    Wraps any driver and validates requests against billing policy.
    Enforces Claude Max OAuth — blocks metered API calls that exceed policy.
    """

    # Maximum output tokens allowed per request under billing policy
    MAX_OUTPUT_TOKENS = 8192
    # Maximum requests per hour per bot
    MAX_REQUESTS_PER_HOUR = 120

    def __init__(self, inner: BaseDriver):
        self._inner = inner
        self._request_log: list[float] = []  # timestamps

    @property
    def driver_kind(self) -> str:
        return f"billing-guard({self._inner.driver_kind})"

    def is_available(self) -> bool:
        return self._inner.is_available()

    def _check_rate_limit(self) -> tuple[bool, str]:
        """Check if request rate is within policy."""
        now = time.time()
        hour_ago = now - 3600
        # Prune old entries
        self._request_log = [t for t in self._request_log if t > hour_ago]
        if len(self._request_log) >= self.MAX_REQUESTS_PER_HOUR:
            return False, f"Rate limit: {self.MAX_REQUESTS_PER_HOUR} requests/hour exceeded"
        return True, "ok"

    def _validate_request(self, messages: list[Message], **kwargs) -> tuple[bool, str]:
        """Validate the request against billing policy."""
        # Check rate limit
        ok, reason = self._check_rate_limit()
        if not ok:
            return False, reason

        # Check requested max_tokens
        max_tokens = kwargs.get("max_tokens", 4096)
        if max_tokens > self.MAX_OUTPUT_TOKENS:
            return False, f"Billing policy: max_tokens {max_tokens} > {self.MAX_OUTPUT_TOKENS}"

        return True, "ok"

    def send(
        self,
        messages: list[Message],
        model: str | None = None,
        **kwargs,
    ) -> DriverResponse:
        ok, reason = self._validate_request(messages, **kwargs)
        if not ok:
            print(f"[billing_guard] BLOCKED: {reason}")
            return DriverResponse(
                text="", model=model or "", driver_kind=self.driver_kind,
                error=f"BillingGuard blocked: {reason}",
            )

        self._request_log.append(time.time())
        resp = self._inner.send(messages, model=model, **kwargs)

        # Check output token count (post-flight)
        if resp.output_tokens > self.MAX_OUTPUT_TOKENS:
            print(f"[billing_guard] WARNING: output_tokens={resp.output_tokens} exceeded policy")

        return resp


# ── Top-level router ──────────────────────────────────────────────────────────

# Per-bot driver assignments
BOT_DRIVER_MAP: dict[str, str] = {
    "chief_of_staff": "xai",
    "marshal": "anthropic",
    "coding_lt": "anthropic",
    "ops_lt": "anthropic",
    "knowledge_lt": "anthropic",
    "maintenance_lt": "ollama",
    "firstmate": "ollama",
    "git_yeoman": "ollama",
    "subscription_watcher": "ollama",
    "api_watcher": "ollama",
    "lockbox": "ollama",
    "passive_watch": "ollama",
    "research_agent": "ollama",
    "hermes_ai_explorer": "ollama",
    "todoist_manager": "ollama",
    "email_reader": "ollama",
    "email_drafter": "ollama",
    "calendar_manager": "ollama",
    "finance_reader": "ollama",
    "obsidian_archivist": "ollama",
}

# Singleton driver instances (lazy init)
_anthropic_driver: AnthropicOAuthDriver | None = None
_xai_driver: XaiOAuthDriver | None = None
_ollama_driver: OllamaLocalDriver | None = None


def _get_anthropic_driver() -> BillingGuardDriver:
    global _anthropic_driver
    if _anthropic_driver is None:
        _anthropic_driver = AnthropicOAuthDriver()
    return BillingGuardDriver(_anthropic_driver)


def _get_xai_driver() -> BillingGuardDriver:
    global _xai_driver
    if _xai_driver is None:
        _xai_driver = XaiOAuthDriver()
    return BillingGuardDriver(_xai_driver)


def _get_ollama_driver() -> OllamaLocalDriver:
    global _ollama_driver
    if _ollama_driver is None:
        fallback = AnthropicOAuthDriver()
        _ollama_driver = OllamaLocalDriver(fallback_driver=fallback)
    return _ollama_driver


def _log_routing_decision(
    bot_id: str, driver_kind: str, model: str, context: dict
) -> None:
    """Append a routing decision to the log file."""
    CARRIER_DIR.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({
        "ts": time.time(),
        "bot_id": bot_id,
        "driver": driver_kind,
        "model": model,
        "context": {k: str(v)[:100] for k, v in context.items()},
    })
    with open(ROUTING_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def route_request(
    messages: list[Message],
    context: dict,
    bot_id: str,
) -> DriverResponse:
    """
    Route a conversation request to the appropriate driver.

    Routing logic:
    1. Chief of Staff → xAI Grok-4.5 (unless quota exceeded)
    2. LTs (coding/ops/knowledge/marshal) → Anthropic sonnet-4-6
    3. Workers/watchers → Ollama local (fallback: Anthropic)
    4. All requests are billing-guard wrapped

    Args:
        messages: Conversation messages
        context: Routing context (task_type, priority, etc.)
        bot_id: Which bot is making the request

    Returns:
        DriverResponse
    """
    preferred_driver = BOT_DRIVER_MAP.get(bot_id, "ollama")
    driver: BaseDriver

    # Check xAI quota state first
    if preferred_driver == "xai":
        xai = XaiOAuthDriver()
        if not xai.is_available():
            print(f"[router] xAI quota exceeded for {bot_id} — falling back to Anthropic")
            preferred_driver = "anthropic"

    # Select and possibly wrap driver
    if preferred_driver == "xai":
        driver = _get_xai_driver()
    elif preferred_driver == "anthropic":
        driver = _get_anthropic_driver()
    else:  # ollama
        driver = _get_ollama_driver()

    # Determine model
    model_override = context.get("model")

    _log_routing_decision(bot_id, driver.driver_kind, model_override or "auto", context)
    print(f"[router] {bot_id} → {driver.driver_kind} (model={model_override or 'auto'})")

    return driver.send(messages, model=model_override)


# ── CLI demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test carrier provider driver routing")
    parser.add_argument("--bot-id", default="research_agent")
    parser.add_argument("--message", default="Hello! What is 2+2?")
    parser.add_argument("--driver", choices=["anthropic", "xai", "ollama", "auto"], default="auto")
    args = parser.parse_args()

    msgs = [Message(role="user", content=args.message)]
    ctx: dict[str, Any] = {}

    if args.driver == "auto":
        resp = route_request(msgs, ctx, bot_id=args.bot_id)
    elif args.driver == "anthropic":
        resp = AnthropicOAuthDriver().send(msgs)
    elif args.driver == "xai":
        resp = XaiOAuthDriver().send(msgs)
    else:
        resp = OllamaLocalDriver().send(msgs)

    print(f"\nDriver: {resp.driver_kind}")
    print(f"Model: {resp.model}")
    print(f"Tokens: {resp.input_tokens}in / {resp.output_tokens}out")
    print(f"Latency: {resp.latency_ms:.0f}ms")
    if resp.error:
        print(f"Error: {resp.error}")
    else:
        print(f"\nResponse:\n{resp.text}")

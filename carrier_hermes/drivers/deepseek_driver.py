from __future__ import annotations
import logging
import uuid
import json
import os
import urllib.request
import urllib.error
from typing import Iterator
from carrier_hermes.core.events import (
    RuntimeEvent, SessionStarted, TurnStarted, ItemStarted,
    ItemCompleted, TurnCompleted, SessionExited, RuntimeError_
)

logger = logging.getLogger("carrier_hermes.drivers.deepseek")

OR_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324:free"


class DeepSeekDriver:
    driver_kind = "deepseek"
    display_name = "DeepSeek Flash (OR allowlist)"
    default_model = DEFAULT_MODEL
    available_models = [
        {"id": DEFAULT_MODEL, "label": "DeepSeek Chat V3 (free)", "context_window": 65536},
    ]
    effort_levels: list[str] = []
    supports_images = False
    supports_streaming = False

    def snapshot(self) -> dict:
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            return {"state": "unavailable", "reason": "OPENROUTER_API_KEY not set", "billing": "openrouter-free"}
        return {"state": "available", "reason": "OR key present", "billing": "openrouter-free"}

    def send_turn(self, thread_id: str, text: str, **kwargs) -> Iterator[RuntimeEvent]:
        base = dict(provider=self.driver_kind, thread_id=thread_id)
        turn_id = str(uuid.uuid4())
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            yield RuntimeError_(**base, turn_id=turn_id, message="OPENROUTER_API_KEY not set", setup=True)  # type: ignore[arg-type]
            yield SessionExited(**base, reason="OPENROUTER_API_KEY not set", code="setup_error")  # type: ignore[arg-type]
            return
        try:
            yield SessionStarted(**base, model=self.default_model)  # type: ignore[arg-type]
            yield TurnStarted(**base, turn_id=turn_id)  # type: ignore[arg-type]
            item_id = str(uuid.uuid4())
            yield ItemStarted(**base, turn_id=turn_id, item_id=item_id, item_type="text")  # type: ignore[arg-type]
            payload = json.dumps({
                "model": self.default_model,
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            }).encode()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://github.com/carrier-hermes",
                "X-Title": "carrier_hermes",
            }
            req = urllib.request.Request(OR_URL, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
            choice = body.get("choices", [{}])[0]
            full_text = choice.get("message", {}).get("content", "")
            usage = body.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            yield ItemCompleted(**base, turn_id=turn_id, item_id=item_id, item_type="text", ok=True, text=full_text)  # type: ignore[arg-type]
            yield TurnCompleted(**base, turn_id=turn_id, ok=True, usage={"input": input_tokens, "output": output_tokens})  # type: ignore[arg-type]
        except urllib.error.URLError as exc:
            logger.exception("DeepSeekDriver: network error: %s", exc)
            yield RuntimeError_(**base, turn_id=turn_id, message=str(exc), setup=False)  # type: ignore[arg-type]
            yield SessionExited(**base, reason=str(exc))  # type: ignore[arg-type]
        except Exception as exc:
            logger.exception("DeepSeekDriver.send_turn error: %s", exc)
            yield RuntimeError_(**base, turn_id=turn_id, message=str(exc), setup=False)  # type: ignore[arg-type]
            yield SessionExited(**base, reason=str(exc))  # type: ignore[arg-type]

    def interrupt_turn(self, thread_id: str) -> None:
        pass

    def respond_to_request(self, thread_id: str, request_id: str, behavior: str) -> str:
        return "unavailable"

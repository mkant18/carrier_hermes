from __future__ import annotations
import logging
import uuid
import json
import urllib.request
import urllib.error
from typing import Iterator
from carrier_hermes.core.events import (
    RuntimeEvent, SessionStarted, TurnStarted, ItemStarted,
    ItemCompleted, TurnCompleted, SessionExited, RuntimeError_
)

logger = logging.getLogger("carrier_hermes.drivers.ollama")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"


class OllamaDriver:
    driver_kind = "ollama"
    display_name = "Ollama Local (Qwen2.5-7B)"
    default_model = DEFAULT_MODEL
    available_models = [
        {"id": DEFAULT_MODEL, "label": "Qwen2.5 Coder 7B Q4_K_M", "context_window": 32768},
    ]
    effort_levels: list[str] = []
    supports_images = False
    supports_streaming = False

    def snapshot(self) -> dict:
        try:
            req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            if req.status == 200:
                return {"state": "available", "reason": "Ollama running", "billing": "local"}
        except Exception as exc:
            return {"state": "unavailable", "reason": str(exc), "billing": "local"}
        return {"state": "unavailable", "reason": "unexpected", "billing": "local"}

    def send_turn(self, thread_id: str, text: str, model: str | None = None, **kwargs) -> Iterator[RuntimeEvent]:
        base = dict(provider=self.driver_kind, thread_id=thread_id)
        turn_id = str(uuid.uuid4())
        m = model or self.default_model
        try:
            yield SessionStarted(**base, model=m)  # type: ignore[arg-type]
            yield TurnStarted(**base, turn_id=turn_id)  # type: ignore[arg-type]
            item_id = str(uuid.uuid4())
            yield ItemStarted(**base, turn_id=turn_id, item_id=item_id, item_type="text")  # type: ignore[arg-type]
            payload = json.dumps({"model": m, "prompt": text, "stream": False}).encode()
            req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            full_text = body.get("response", "")
            input_tokens = body.get("prompt_eval_count", 0)
            output_tokens = body.get("eval_count", 0)
            yield ItemCompleted(**base, turn_id=turn_id, item_id=item_id, item_type="text", ok=True, text=full_text)  # type: ignore[arg-type]
            yield TurnCompleted(**base, turn_id=turn_id, ok=True, usage={"input": input_tokens, "output": output_tokens})  # type: ignore[arg-type]
        except urllib.error.URLError as exc:
            logger.exception("OllamaDriver: network error: %s", exc)
            yield RuntimeError_(**base, turn_id=turn_id, message=str(exc), setup=True)  # type: ignore[arg-type]
            yield SessionExited(**base, reason=str(exc), code="setup_error")  # type: ignore[arg-type]
        except Exception as exc:
            logger.exception("OllamaDriver.send_turn error: %s", exc)
            yield RuntimeError_(**base, turn_id=turn_id, message=str(exc), setup=False)  # type: ignore[arg-type]
            yield SessionExited(**base, reason=str(exc))  # type: ignore[arg-type]

    def interrupt_turn(self, thread_id: str) -> None:
        pass

    def respond_to_request(self, thread_id: str, request_id: str, behavior: str) -> str:
        return "unavailable"

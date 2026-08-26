from __future__ import annotations
import logging
import uuid
from typing import Iterator
from carrier_hermes.core.events import (
    RuntimeEvent, SessionStarted, TurnStarted, ItemStarted,
    ContentDelta, ItemCompleted, TurnCompleted, SessionExited, RuntimeError_
)

logger = logging.getLogger("carrier_hermes.drivers.grok")


class GrokDriver:
    driver_kind = "grok"
    display_name = "Grok 4.5 (xai-oauth)"
    default_model = "grok-4"
    available_models = [
        {"id": "grok-4", "label": "Grok 4", "context_window": 131072},
        {"id": "grok-4-5", "label": "Grok 4.5", "context_window": 131072},
    ]
    effort_levels = ["low", "medium", "high"]
    supports_images = False
    supports_streaming = True

    def snapshot(self) -> dict:
        return {"state": "available", "reason": "Grok xai-oauth active", "billing": "subscription"}

    def send_turn(self, thread_id: str, text: str, **kwargs) -> Iterator[RuntimeEvent]:
        base = dict(provider=self.driver_kind, thread_id=thread_id)
        turn_id = str(uuid.uuid4())
        try:
            yield SessionStarted(**base, model=self.default_model)  # type: ignore[arg-type]
            yield TurnStarted(**base, turn_id=turn_id)  # type: ignore[arg-type]
            item_id = str(uuid.uuid4())
            yield ItemStarted(**base, turn_id=turn_id, item_id=item_id, item_type="text")  # type: ignore[arg-type]
            yield ContentDelta(**base, turn_id=turn_id, item_id=item_id, delta="[Grok response placeholder]")  # type: ignore[arg-type]
            yield ItemCompleted(**base, turn_id=turn_id, item_id=item_id, item_type="text", ok=True, text="[Grok response placeholder]")  # type: ignore[arg-type]
            yield TurnCompleted(**base, turn_id=turn_id, ok=True, usage={"input": 0, "output": 0})  # type: ignore[arg-type]
        except Exception as exc:
            logger.exception("GrokDriver.send_turn error: %s", exc)
            yield RuntimeError_(**base, turn_id=turn_id, message=str(exc), setup=False)  # type: ignore[arg-type]
            yield SessionExited(**base, reason=str(exc))  # type: ignore[arg-type]

    def interrupt_turn(self, thread_id: str) -> None:
        pass

    def respond_to_request(self, thread_id: str, request_id: str, behavior: str) -> str:
        return "unavailable"

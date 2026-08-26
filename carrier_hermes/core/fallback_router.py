from __future__ import annotations
import logging
from typing import Callable
from carrier_hermes.core.events import SessionExited, RuntimeError_
from carrier_hermes.core.event_bus import HelmEventBus

logger = logging.getLogger("carrier_hermes.fallback_router")

# Error codes that trigger provider advance
ADVANCE_ON_SESSION_EXITED = {
    "inactive_subscription",
    "quota_or_region_restriction",
    "setup_error",
    None,  # unspecified exit also advances
}

FALLBACK_CHAIN = ["claude", "grok", "ollama", "deepseek"]


class FallbackRouter:
    """
    Subscribes to session.exited and runtime.error events.
    On a qualifying event, calls _advance_provider_callback with the next provider name.
    Caller must wire _advance_provider_callback to actually switch the driver and retry.
    """

    def __init__(self, bus: HelmEventBus, advance_cb: Callable[[str, str, str], None]) -> None:
        """
        advance_cb(thread_id, current_provider, next_provider) — called when fallback triggered.
        """
        self._advance = advance_cb
        bus.subscribe(["session.exited", "runtime.error"], self._handle)

    def _handle(self, event) -> None:
        if isinstance(event, SessionExited):
            if event.code in ADVANCE_ON_SESSION_EXITED:
                self._try_advance(event.thread_id, event.provider)
        elif isinstance(event, RuntimeError_):
            if event.setup:
                self._try_advance(event.thread_id, event.provider)

    def _try_advance(self, thread_id: str, current: str) -> None:
        try:
            idx = FALLBACK_CHAIN.index(current)
        except ValueError:
            logger.error("FallbackRouter: unknown provider %r — cannot advance", current)
            return
        if idx + 1 >= len(FALLBACK_CHAIN):
            logger.error("FallbackRouter: end of chain reached from %r on thread %s", current, thread_id)
            return
        nxt = FALLBACK_CHAIN[idx + 1]
        logger.info("FallbackRouter: %s → %s (thread=%s)", current, nxt, thread_id)
        try:
            self._advance(thread_id, current, nxt)
        except Exception as exc:
            logger.exception("FallbackRouter: advance_cb raised: %s", exc)

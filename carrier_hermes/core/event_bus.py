from __future__ import annotations
import logging
import threading
from collections import defaultdict
from typing import Callable

logger = logging.getLogger("carrier_hermes.event_bus")


class HelmEventBus:
    """Synchronous fan-out event bus. Thread-safe subscribe/publish."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # event_type -> list of handlers
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        # "*" key means subscribe-to-all
        self._wildcard: list[Callable] = []

    def subscribe(self, event_types: list[str], handler: Callable) -> Callable:
        """
        Register handler for the given event type strings.
        Pass ["*"] to receive all events.
        Returns an unsubscribe callable.
        """
        with self._lock:
            for et in event_types:
                if et == "*":
                    self._wildcard.append(handler)
                else:
                    self._handlers[et].append(handler)

        def _unsub():
            with self._lock:
                for et in event_types:
                    if et == "*":
                        try:
                            self._wildcard.remove(handler)
                        except ValueError:
                            pass
                    else:
                        try:
                            self._handlers[et].remove(handler)
                        except ValueError:
                            pass
        return _unsub

    def publish(self, event) -> None:
        """Fan-out event to all matching subscribers. Errors in handlers are logged, not raised."""
        etype: str | None = getattr(event, "type", None)
        with self._lock:
            handlers = list(self._handlers.get(etype or "", [])) + list(self._wildcard)
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.exception("HelmEventBus: handler %s raised for %s: %s", handler, etype, exc)


# Module-level singleton — import and use directly
bus = HelmEventBus()

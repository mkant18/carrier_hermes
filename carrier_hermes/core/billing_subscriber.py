from __future__ import annotations
import logging
from collections import defaultdict
from carrier_hermes.core.events import TurnCompleted
from carrier_hermes.core.event_bus import HelmEventBus

logger = logging.getLogger("carrier_hermes.billing_subscriber")


class BillingSubscriber:
    """
    Accumulates token usage from turn.completed events only.
    Token accounting rule: only turn.completed.usage is authoritative.
    Never sum thread-level or streaming token counters.
    """

    def __init__(
        self,
        bus: HelmEventBus,
        fleet_limit_tokens: int = 2_000_000,
        per_thread_limit_tokens: int = 200_000,
    ) -> None:
        self._fleet_total: int = 0
        self._per_thread: dict[str, int] = defaultdict(int)
        self._fleet_limit = fleet_limit_tokens
        self._per_thread_limit = per_thread_limit_tokens
        bus.subscribe(["turn.completed"], self._handle)

    def _handle(self, event: TurnCompleted) -> None:
        usage = event.usage or {}
        tokens = usage.get("input", 0) + usage.get("output", 0)
        if tokens <= 0:
            return
        self._fleet_total += tokens
        self._per_thread[event.thread_id] += tokens
        logger.debug(
            "BillingSubscriber: thread=%s +%d tokens (thread_total=%d, fleet_total=%d)",
            event.thread_id, tokens, self._per_thread[event.thread_id], self._fleet_total,
        )
        if self._per_thread[event.thread_id] >= self._per_thread_limit:
            logger.warning(
                "BillingSubscriber: thread %s reached per-thread limit (%d tokens)",
                event.thread_id, self._per_thread_limit,
            )
        if self._fleet_total >= self._fleet_limit:
            logger.warning(
                "BillingSubscriber: FLEET limit reached (%d tokens)", self._fleet_total,
            )

    def fleet_total(self) -> int:
        return self._fleet_total

    def thread_total(self, thread_id: str) -> int:
        return self._per_thread.get(thread_id, 0)

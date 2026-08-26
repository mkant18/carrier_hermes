from __future__ import annotations
from typing import Protocol, Iterator, runtime_checkable
from carrier_hermes.core.events import RuntimeEvent


@runtime_checkable
class ProviderDriver(Protocol):
    driver_kind: str              # "claude", "grok", "ollama", "deepseek"
    display_name: str
    default_model: str
    available_models: list[dict]  # [{"id": str, "label": str, "context_window": int}]
    effort_levels: list[str]      # subset of ["none","low","medium","high","xhigh","max"]
    supports_images: bool
    supports_streaming: bool

    def snapshot(self) -> dict:
        """Return {"state": "available"|"unavailable", "reason": str, "billing": str}"""
        ...

    def send_turn(self, thread_id: str, text: str, **kwargs) -> Iterator[RuntimeEvent]:
        """Yield RuntimeEvent objects as the provider produces output."""
        ...

    def interrupt_turn(self, thread_id: str) -> None: ...

    def respond_to_request(self, thread_id: str, request_id: str, behavior: str) -> str:
        """Returns "allowed-once" | "rejected" | "answered" | "unavailable" """
        ...

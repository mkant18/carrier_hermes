# Spec B: Provider-Normalized Event Stream for carrier_hermes Routing Layer

**Pattern source:** OpenMausBot `server/contracts.ts` (`RuntimeEvent` union, `ProviderAdapter`, `ProviderDriver`)  
**Assignee:** coding_lt  
**Priority:** 2 (blocked on human review)

---

## Problem

Each provider in carrier_hermes (Claude Max, Grok 4.5, Ollama/Qwen, DeepSeek Flash) has bespoke integration code scattered across bot prompts, scripts, and routing decisions. There is no unified way to:
- Observe token usage fleet-wide (billing guard has to instrument each provider separately)
- Detect provider failures and trigger fallback routing automatically
- Stream bot output to Discord as it arrives (not just after turn completion)
- Surface tool calls and approval requests uniformly regardless of provider

## Proposed Solution

Adopt OpenMausBot's canonical `RuntimeEvent` union as a Python dataclass hierarchy. Every provider driver emits `RuntimeEvent` objects. A central `HelmEventBus` fan-outs each event to registered subscribers (billing guard, Discord bridge, approval handler, activity logger).

---

## Canonical Event Types (Python translation)

```python
# Base fields on every event
@dataclass
class RuntimeEventBase:
    event_id: str              # uuid
    provider: str              # "claude", "grok", "ollama", "deepseek"
    thread_id: str             # bot profile ID + session
    created_at: str            # ISO timestamp
    turn_id: str | None = None
    item_id: str | None = None
    request_id: str | None = None
    raw: dict | None = None    # original provider message for debugging

# Session lifecycle
SessionStarted = TypedDict('SessionStarted', {'type': Literal['session.started'], 'session_id': str | None, 'model': str | None})
SessionExited  = TypedDict('SessionExited',  {'type': Literal['session.exited'],  'reason': str | None})

# Turn lifecycle
TurnStarted   = TypedDict('TurnStarted',   {'type': Literal['turn.started']})
TurnRetrying  = TypedDict('TurnRetrying',  {'type': Literal['turn.retrying'], 'attempt': int, 'delay_ms': int, 'reason': str})
TurnCompleted = TypedDict('TurnCompleted', {
    'type': Literal['turn.completed'],
    'ok': bool,
    'stop_reason': str | None,
    'cost': float | None,
    'denials': list[str],
    'usage': dict[str, int] | None,  # {'input': N, 'output': N} — THIS turn only, never sum thread.token-usage
})

# Tool and text items
ItemStarted   = TypedDict('ItemStarted',   {'type': Literal['item.started'],    'item_type': str, 'title': str | None})
ItemCompleted = TypedDict('ItemCompleted', {'type': Literal['item.completed'],  'item_type': str, 'ok': bool | None, 'text': str | None})
ContentDelta  = TypedDict('ContentDelta',  {'type': Literal['content.delta'],   'stream_kind': str, 'delta': str})

# Human-in-the-loop (feeds Spec A approval cards)
RequestOpened   = TypedDict('RequestOpened',   {'type': Literal['request.opened'],   'request_type': str, 'tool': str, 'summary': str, 'choices': list[str] | None})
RequestResolved = TypedDict('RequestResolved', {'type': Literal['request.resolved'], 'behavior': str, 'source': str})

# Errors
RuntimeError_ = TypedDict('RuntimeError_', {'type': Literal['runtime.error'], 'message': str, 'setup': bool})

RuntimeEvent = RuntimeEventBase  # base; typed by 'type' discriminator in practice
```

---

## Provider Driver Protocol

```python
from typing import Protocol, Iterator

class ProviderDriver(Protocol):
    driver_kind: str              # "claude", "grok", "ollama", "deepseek"
    display_name: str
    default_model: str
    available_models: list[dict]  # [{id, label, context_window}]
    effort_levels: list[str]      # subset of ["none","low","medium","high","xhigh","max"]
    supports_images: bool
    supports_streaming: bool

    def snapshot(self) -> dict:
        """Return {'state': 'available'|'unavailable', 'reason': str, 'billing': str}"""
        ...

    def send_turn(self, thread_id: str, text: str, **kwargs) -> Iterator[RuntimeEvent]:
        """Yield RuntimeEvent objects as the provider produces output."""
        ...

    def interrupt_turn(self, thread_id: str) -> None: ...

    def respond_to_request(self, thread_id: str, request_id: str, behavior: str) -> str:
        """Returns 'allowed-once' | 'rejected' | 'answered' | 'unavailable'"""
        ...
```

---

## HelmEventBus

```python
# carrier_hermes/core/event_bus.py (pseudocode)
class HelmEventBus:
    def subscribe(self, event_types: list[str], handler: Callable) -> Callable:
        """Returns unsubscribe function."""
        ...

    def publish(self, event: RuntimeEvent) -> None:
        """Fan-out to all matching subscribers synchronously."""
        ...
```

**Subscribers:**

| Subscriber | Event Types | Action |
|-----------|------------|--------|
| `billing_guard` | `turn.completed` | Accumulate token usage; check spend limits |
| `discord_bridge` | `content.delta` | Edit Discord message in real-time (streaming) |
| `discord_bridge` | `item.started` (tool) | Post "🔧 Running {title}..." message |
| `approval_handler` | `request.opened` | Trigger Spec A approval card |
| `activity_logger` | all | Write to per-bot activity log |
| `fallback_router` | `session.exited`, `runtime.error` | Try next provider in chain |
| `fleet_checkin` | `turn.completed`, `session.exited` | Update fleet status in Discord |

---

## Provider Chain + Fallback Routing

```
Claude Max (OAuth) 
  → on session.exited with code=inactive_subscription → Grok 4.5
Grok 4.5
  → on session.exited or quota_or_region_restriction → Ollama (local)
Ollama (local, Qwen2.5-7B Q4_K_M)
  → on runtime.error with setup=true → DeepSeek Flash
DeepSeek Flash
  → on failure → runtime.error published; task marked failed
```

The `fallback_router` subscriber intercepts `session.exited` and `runtime.error` events, checks error codes against `ProviderErrorCode` values (ported from contracts.ts), and re-issues `send_turn()` with the next driver. The `raw` field on the event preserves the original provider error for logging.

---

## Streaming vs. Non-Streaming

- **Streaming (Claude, Grok):** yield `content.delta` events, then `item.completed` at turn end. Discord bridge edits the message incrementally.
- **Non-streaming (Ollama in current integration, DeepSeek):** buffer output, yield single `item.completed`. Discord bridge posts once. Flag `supports_streaming=False` on the driver.

---

## Token Accounting Rule (critical, from OpenMausBot)

> `turn.completed.usage` is the ONE authoritative per-turn figure. `thread.token-usage.updated` is a live indicator whose meaning differs per driver (per-call delta vs. thread total vs. per-step figure) and **must never be summed**.

The billing guard should only accumulate from `turn.completed.usage`.

---

## Implementation Path

1. Define `RuntimeEvent` dataclasses in `carrier_hermes/core/events.py`
2. Implement `HelmEventBus` in `carrier_hermes/core/event_bus.py`
3. Refactor `ClaudeDriver` (already mostly isolated) to yield events
4. Implement `GrokDriver`, `OllamaDriver`, `DeepSeekDriver` as one file each
5. Wire `billing_guard.py` to subscribe to `turn.completed`
6. Wire Discord bridge to subscribe to `content.delta` + `item.started`
7. Wire `fallback_router` to subscribe to `session.exited` + `runtime.error`

---

## Out of Scope (this spec)

- Full `ProviderDriver` capability matrix UI (not applicable — Discord is the UI)
- Multi-instance providers (two Claude instances) — future
- Effort level controls exposed to users — future

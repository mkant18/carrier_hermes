from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class RuntimeEventBase:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = ""               # "claude", "grok", "ollama", "deepseek"
    thread_id: str = ""              # bot profile ID + session
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turn_id: str | None = None
    item_id: str | None = None
    request_id: str | None = None
    raw: dict | None = None          # original provider message for debugging


# --- Session lifecycle ---
@dataclass
class SessionStarted(RuntimeEventBase):
    type: Literal["session.started"] = "session.started"
    session_id: str | None = None
    model: str | None = None


@dataclass
class SessionExited(RuntimeEventBase):
    type: Literal["session.exited"] = "session.exited"
    reason: str | None = None
    code: str | None = None          # e.g. "inactive_subscription", "quota_or_region_restriction"


# --- Turn lifecycle ---
@dataclass
class TurnStarted(RuntimeEventBase):
    type: Literal["turn.started"] = "turn.started"


@dataclass
class TurnRetrying(RuntimeEventBase):
    type: Literal["turn.retrying"] = "turn.retrying"
    attempt: int = 0
    delay_ms: int = 0
    reason: str = ""


@dataclass
class TurnCompleted(RuntimeEventBase):
    type: Literal["turn.completed"] = "turn.completed"
    ok: bool = True
    stop_reason: str | None = None
    cost: float | None = None
    denials: list[str] = field(default_factory=list)
    # CRITICAL: only THIS turn's usage — never sum thread-level token counters
    usage: dict[str, int] | None = None  # {"input": N, "output": N}


# --- Content items ---
@dataclass
class ItemStarted(RuntimeEventBase):
    type: Literal["item.started"] = "item.started"
    item_type: str = ""              # "text", "tool_use", "tool_result"
    title: str | None = None


@dataclass
class ItemCompleted(RuntimeEventBase):
    type: Literal["item.completed"] = "item.completed"
    item_type: str = ""
    ok: bool | None = None
    text: str | None = None


@dataclass
class ContentDelta(RuntimeEventBase):
    type: Literal["content.delta"] = "content.delta"
    stream_kind: str = "text"
    delta: str = ""


# --- Human-in-the-loop ---
@dataclass
class RequestOpened(RuntimeEventBase):
    type: Literal["request.opened"] = "request.opened"
    request_type: str = ""
    tool: str = ""
    summary: str = ""
    choices: list[str] | None = None


@dataclass
class RequestResolved(RuntimeEventBase):
    type: Literal["request.resolved"] = "request.resolved"
    behavior: str = ""               # "allowed-once", "rejected", "answered"
    source: str = ""                 # "human", "auto"


# --- Errors ---
@dataclass
class RuntimeError_(RuntimeEventBase):
    type: Literal["runtime.error"] = "runtime.error"
    message: str = ""
    setup: bool = False              # True = provider not reachable at all


# Union type alias
RuntimeEvent = (
    SessionStarted | SessionExited |
    TurnStarted | TurnRetrying | TurnCompleted |
    ItemStarted | ItemCompleted | ContentDelta |
    RequestOpened | RequestResolved |
    RuntimeError_
)

# Map type strings to classes for deserialization
EVENT_TYPE_MAP: dict[str, type] = {
    "session.started": SessionStarted,
    "session.exited": SessionExited,
    "turn.started": TurnStarted,
    "turn.retrying": TurnRetrying,
    "turn.completed": TurnCompleted,
    "item.started": ItemStarted,
    "item.completed": ItemCompleted,
    "content.delta": ContentDelta,
    "request.opened": RequestOpened,
    "request.resolved": RequestResolved,
    "runtime.error": RuntimeError_,
}

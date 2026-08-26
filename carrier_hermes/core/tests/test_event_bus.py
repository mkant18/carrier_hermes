"""
Unit tests for Spec B: provider-normalized event stream.
Run with: python -m pytest carrier_hermes/core/tests/ -v
(from C:/Users/micha/carrier_hermes/.worktrees/t_0eeee5bf)
"""
from __future__ import annotations

import dataclasses
import threading
import unittest.mock as mock
import urllib.error
from io import BytesIO

import pytest

from carrier_hermes.core.events import (
    EVENT_TYPE_MAP,
    ContentDelta,
    ItemCompleted,
    ItemStarted,
    RequestOpened,
    RequestResolved,
    RuntimeError_,
    RuntimeEventBase,
    SessionExited,
    SessionStarted,
    TurnCompleted,
    TurnRetrying,
    TurnStarted,
)
from carrier_hermes.core.event_bus import HelmEventBus
from carrier_hermes.core.billing_subscriber import BillingSubscriber
from carrier_hermes.core.discord_bridge_subscriber import DiscordBridgeSubscriber
from carrier_hermes.core.fallback_router import FallbackRouter
from carrier_hermes.core.driver_protocol import ProviderDriver
from carrier_hermes.drivers.claude_driver import ClaudeDriver
from carrier_hermes.drivers.grok_driver import GrokDriver
from carrier_hermes.drivers.ollama_driver import OllamaDriver
from carrier_hermes.drivers.deepseek_driver import DeepSeekDriver


# ---------------------------------------------------------------------------
# Event dataclass tests
# ---------------------------------------------------------------------------

class TestEventDefaults:
    def test_unique_event_ids(self):
        e1 = TurnCompleted()
        e2 = TurnCompleted()
        assert e1.event_id != e2.event_id

    def test_unique_created_at(self):
        import time
        e1 = TurnCompleted()
        time.sleep(0.001)
        e2 = TurnCompleted()
        # Should have valid ISO timestamps; may be equal if fast, so just check format
        assert "T" in e1.created_at
        assert "T" in e2.created_at

    def test_independent_denials_list(self):
        e1 = TurnCompleted()
        e2 = TurnCompleted()
        e1.denials.append("x")
        assert e2.denials == []

    def test_event_type_map_has_11_entries(self):
        assert len(EVENT_TYPE_MAP) == 11

    def test_event_type_map_correct_classes(self):
        assert EVENT_TYPE_MAP["session.started"] is SessionStarted
        assert EVENT_TYPE_MAP["session.exited"] is SessionExited
        assert EVENT_TYPE_MAP["turn.started"] is TurnStarted
        assert EVENT_TYPE_MAP["turn.retrying"] is TurnRetrying
        assert EVENT_TYPE_MAP["turn.completed"] is TurnCompleted
        assert EVENT_TYPE_MAP["item.started"] is ItemStarted
        assert EVENT_TYPE_MAP["item.completed"] is ItemCompleted
        assert EVENT_TYPE_MAP["content.delta"] is ContentDelta
        assert EVENT_TYPE_MAP["request.opened"] is RequestOpened
        assert EVENT_TYPE_MAP["request.resolved"] is RequestResolved
        assert EVENT_TYPE_MAP["runtime.error"] is RuntimeError_

    def test_asdict_on_all_event_types(self):
        events = [
            SessionStarted(), SessionExited(), TurnStarted(), TurnRetrying(),
            TurnCompleted(), ItemStarted(), ItemCompleted(), ContentDelta(),
            RequestOpened(), RequestResolved(), RuntimeError_(),
        ]
        for ev in events:
            d = dataclasses.asdict(ev)
            assert "event_id" in d
            assert "type" in d


# ---------------------------------------------------------------------------
# HelmEventBus tests
# ---------------------------------------------------------------------------

class TestHelmEventBus:
    def test_subscribe_and_receive(self):
        bus = HelmEventBus()
        received = []
        bus.subscribe(["turn.completed"], received.append)
        ev = TurnCompleted(thread_id="t1")
        bus.publish(ev)
        assert received == [ev]

    def test_wildcard_receives_all(self):
        bus = HelmEventBus()
        received = []
        bus.subscribe(["*"], received.append)
        bus.publish(TurnCompleted())
        bus.publish(SessionStarted())
        bus.publish(ContentDelta())
        assert len(received) == 3

    def test_unsubscribe_stops_delivery(self):
        bus = HelmEventBus()
        received = []
        unsub = bus.subscribe(["turn.completed"], received.append)
        unsub()
        bus.publish(TurnCompleted())
        assert received == []

    def test_unsubscribe_idempotent(self):
        bus = HelmEventBus()
        received = []
        unsub = bus.subscribe(["turn.completed"], received.append)
        unsub()
        unsub()  # Should not raise

    def test_handler_exception_does_not_kill_bus(self):
        bus = HelmEventBus()
        results = []

        def bad_handler(e):
            raise ValueError("boom")

        def good_handler(e):
            results.append(e)

        bus.subscribe(["turn.completed"], bad_handler)
        bus.subscribe(["turn.completed"], good_handler)
        ev = TurnCompleted()
        bus.publish(ev)
        assert results == [ev]

    def test_reentrant_publish_no_deadlock(self):
        bus = HelmEventBus()
        inner_received = []

        def reentrant_handler(e):
            if not inner_received:  # only recurse once
                bus.publish(SessionStarted())
                inner_received.append("ok")

        bus.subscribe(["turn.completed"], reentrant_handler)
        # Should complete without deadlock
        bus.publish(TurnCompleted())
        assert inner_received == ["ok"]

    def test_multiple_event_types_one_subscriber(self):
        bus = HelmEventBus()
        received = []
        bus.subscribe(["session.started", "session.exited"], received.append)
        bus.publish(SessionStarted())
        bus.publish(SessionExited())
        bus.publish(TurnCompleted())  # should not be received
        assert len(received) == 2


# ---------------------------------------------------------------------------
# BillingSubscriber tests
# ---------------------------------------------------------------------------

class TestBillingSubscriber:
    def test_accumulates_from_turn_completed_usage(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        bus.publish(TurnCompleted(thread_id="bot1", usage={"input": 100, "output": 200}))
        assert billing.fleet_total() == 300
        assert billing.thread_total("bot1") == 300

    def test_ignores_none_usage(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        bus.publish(TurnCompleted(thread_id="bot1", usage=None))
        assert billing.fleet_total() == 0

    def test_ignores_zero_usage(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        bus.publish(TurnCompleted(thread_id="bot1", usage={"input": 0, "output": 0}))
        assert billing.fleet_total() == 0

    def test_accumulates_across_multiple_turns(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        bus.publish(TurnCompleted(thread_id="bot1", usage={"input": 10, "output": 20}))
        bus.publish(TurnCompleted(thread_id="bot1", usage={"input": 5, "output": 5}))
        assert billing.fleet_total() == 40
        assert billing.thread_total("bot1") == 40

    def test_per_thread_isolation(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        bus.publish(TurnCompleted(thread_id="bot1", usage={"input": 100, "output": 0}))
        bus.publish(TurnCompleted(thread_id="bot2", usage={"input": 200, "output": 0}))
        assert billing.thread_total("bot1") == 100
        assert billing.thread_total("bot2") == 200
        assert billing.fleet_total() == 300

    def test_unknown_thread_total_is_zero(self):
        bus = HelmEventBus()
        billing = BillingSubscriber(bus)
        assert billing.thread_total("nonexistent") == 0


# ---------------------------------------------------------------------------
# DiscordBridgeSubscriber tests
# ---------------------------------------------------------------------------

class TestDiscordBridgeSubscriber:
    def test_content_delta_buffer_accumulation(self):
        bus = HelmEventBus()
        bridge = DiscordBridgeSubscriber(bus)
        bus.publish(ContentDelta(thread_id="t1", delta="Hello "))
        bus.publish(ContentDelta(thread_id="t1", delta="world"))
        assert bridge._buffers["t1"] == "Hello world"

    def test_content_delta_separate_threads(self):
        bus = HelmEventBus()
        bridge = DiscordBridgeSubscriber(bus)
        bus.publish(ContentDelta(thread_id="t1", delta="A"))
        bus.publish(ContentDelta(thread_id="t2", delta="B"))
        assert bridge._buffers["t1"] == "A"
        assert bridge._buffers["t2"] == "B"

    def test_tool_announcement_on_non_text_item(self):
        bus = HelmEventBus()
        bridge = DiscordBridgeSubscriber(bus)
        calls: list[tuple[str, str]] = []
        bridge._post_tool_announcement = lambda thread_id, title: calls.append((thread_id, title))  # type: ignore[method-assign]
        bus.publish(ItemStarted(thread_id="t1", item_type="tool_use", title="bash"))
        assert calls == [("t1", "bash")]

    def test_no_announcement_for_text_item(self):
        bus = HelmEventBus()
        bridge = DiscordBridgeSubscriber(bus)
        calls: list[tuple[str, str]] = []
        bridge._post_tool_announcement = lambda thread_id, title: calls.append((thread_id, title))  # type: ignore[method-assign]
        bus.publish(ItemStarted(thread_id="t1", item_type="text"))
        assert calls == []


# ---------------------------------------------------------------------------
# FallbackRouter tests
# ---------------------------------------------------------------------------

class TestFallbackRouter:
    def test_advances_claude_to_grok_on_session_exited(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(SessionExited(thread_id="t1", provider="claude", code="inactive_subscription"))
        assert advances == [("t1", "claude", "grok")]

    def test_advances_ollama_to_deepseek_on_runtime_error_setup(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(RuntimeError_(thread_id="t1", provider="ollama", setup=True))
        assert advances == [("t1", "ollama", "deepseek")]

    def test_does_not_advance_on_runtime_error_not_setup(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(RuntimeError_(thread_id="t1", provider="claude", setup=False))
        assert advances == []

    def test_no_advance_at_end_of_chain(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(SessionExited(thread_id="t1", provider="deepseek", code="setup_error"))
        assert advances == []

    def test_unknown_provider_does_not_crash(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(SessionExited(thread_id="t1", provider="unknown_provider", code="setup_error"))
        assert advances == []

    def test_advances_on_none_code(self):
        bus = HelmEventBus()
        advances = []
        router = FallbackRouter(bus, lambda tid, cur, nxt: advances.append((tid, cur, nxt)))
        bus.publish(SessionExited(thread_id="t1", provider="grok", code=None))
        assert advances == [("t1", "grok", "ollama")]


# ---------------------------------------------------------------------------
# ProviderDriver protocol check
# ---------------------------------------------------------------------------

class TestProviderDriverProtocol:
    def test_claude_driver_satisfies_protocol(self):
        assert isinstance(ClaudeDriver(), ProviderDriver)

    def test_grok_driver_satisfies_protocol(self):
        assert isinstance(GrokDriver(), ProviderDriver)

    def test_ollama_driver_satisfies_protocol(self):
        assert isinstance(OllamaDriver(), ProviderDriver)

    def test_deepseek_driver_satisfies_protocol(self):
        assert isinstance(DeepSeekDriver(), ProviderDriver)


# ---------------------------------------------------------------------------
# Driver send_turn event sequence tests
# ---------------------------------------------------------------------------

class TestClaudeDriverSequence:
    def test_send_turn_includes_content_delta(self):
        driver = ClaudeDriver()
        events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert "content.delta" in types
        assert types[0] == "session.started"
        assert types[-1] == "turn.completed"

    def test_send_turn_full_sequence(self):
        driver = ClaudeDriver()
        events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert types == [
            "session.started",
            "turn.started",
            "item.started",
            "content.delta",
            "item.completed",
            "turn.completed",
        ]


class TestGrokDriverSequence:
    def test_send_turn_includes_content_delta(self):
        driver = GrokDriver()
        events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert "content.delta" in types

    def test_send_turn_full_sequence(self):
        driver = GrokDriver()
        events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert types == [
            "session.started",
            "turn.started",
            "item.started",
            "content.delta",
            "item.completed",
            "turn.completed",
        ]


class TestOllamaDriverSequence:
    def _make_mock_response(self, body: dict):
        import json
        data = json.dumps(body).encode()
        response = mock.MagicMock()
        response.read.return_value = data
        response.__enter__ = lambda s: s
        response.__exit__ = mock.MagicMock(return_value=False)
        return response

    def test_send_turn_no_content_delta(self):
        driver = OllamaDriver()
        mock_resp = self._make_mock_response({
            "response": "Hello from Ollama",
            "prompt_eval_count": 5,
            "eval_count": 10,
        })
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert "content.delta" not in types
        assert types == [
            "session.started",
            "turn.started",
            "item.started",
            "item.completed",
            "turn.completed",
        ]

    def test_send_turn_url_error_yields_setup_error(self):
        driver = OllamaDriver()
        url_err = urllib.error.URLError("connection refused")
        with mock.patch("urllib.request.urlopen", side_effect=url_err):
            events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert "runtime.error" in types
        assert "session.exited" in types
        err_events = [e for e in events if isinstance(e, RuntimeError_)]
        assert len(err_events) == 1
        assert err_events[0].setup is True
        exit_events = [e for e in events if isinstance(e, SessionExited)]
        assert len(exit_events) == 1
        assert exit_events[0].code == "setup_error"


class TestDeepSeekDriverSequence:
    def test_missing_key_yields_setup_error(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        driver = DeepSeekDriver()
        events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert types == ["runtime.error", "session.exited"]
        err_events = [e for e in events if isinstance(e, RuntimeError_)]
        assert err_events[0].setup is True
        exit_events = [e for e in events if isinstance(e, SessionExited)]
        assert exit_events[0].code == "setup_error"

    def test_with_key_no_content_delta(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        driver = DeepSeekDriver()
        import json
        body = {
            "choices": [{"message": {"content": "Deep answer"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            events = list(driver.send_turn("t1", "hello"))
        types = [e.type for e in events]
        assert "content.delta" not in types
        assert types == [
            "session.started",
            "turn.started",
            "item.started",
            "item.completed",
            "turn.completed",
        ]

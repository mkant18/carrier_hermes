"""Smoke test for ob1-fleet-brain (no external deps needed for basic path)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent))

from embedder import Embedder, chunk_text
from store import FleetBrainStore


@pytest.fixture
def tmp_store(tmp_path):
    db = tmp_path / "test_brain.db"
    store = FleetBrainStore(db)
    yield store
    store.close()


def test_write_and_get(tmp_store):
    vec = np.random.rand(384).astype(np.float32)
    vec /= np.linalg.norm(vec)
    tid = tmp_store.write_thought(
        content="Probe found that the carrier fleet needs a shared memory layer.",
        source="probe",
        scope="fleet",
        category="research",
        summary="Probe research finding",
        chunks=[("Probe found that the carrier fleet needs a shared memory layer.", vec)],
    )
    assert tid
    thought = tmp_store.get_thought(tid)
    assert thought is not None
    assert thought["source"] == "probe"
    assert thought["scope"] == "fleet"


def test_search(tmp_store):
    dim = 384
    base = np.random.rand(dim).astype(np.float32)
    base /= np.linalg.norm(base)
    for i, text in enumerate(["carrier fleet decision alpha", "probe research beta", "discord error gamma"]):
        v = base + np.random.rand(dim).astype(np.float32) * 0.1
        v /= np.linalg.norm(v)
        tmp_store.write_thought(content=text, source="test", scope="fleet",
                                chunks=[(text, v)])
    hits = tmp_store.search(base, top_k=3)
    assert len(hits) >= 1
    assert hits[0].score > 0.0


def test_keyword_search(tmp_store):
    tid = tmp_store.write_thought(
        content="Mate hit an ImportError when loading the billing guard plugin.",
        source="firstmate",
        scope="fleet",
        category="failure",
    )
    results = tmp_store.keyword_search("billing guard ImportError", top_k=5)
    assert any(r["id"] == tid for r in results)


def test_discord_capture(tmp_store):
    tid = tmp_store.write_thought(
        content="First Watch detected a new message in #fleet-general.",
        source="discord",
        scope="fleet",
        category="discord",
        chunks=[],
    )
    tmp_store.upsert_discord_message(
        message_id="111222333",
        channel_id="999",
        channel_name="fleet-general",
        guild_name="carrier",
        author="michael#0001",
        content="First Watch detected a new message in #fleet-general.",
        thought_id=tid,
    )
    stats = tmp_store.stats()
    assert stats["discord_messages"] == 1


def test_scope_filter(tmp_store):
    vec = np.random.rand(384).astype(np.float32)
    vec /= np.linalg.norm(vec)
    tmp_store.write_thought(content="fleet wide", scope="fleet", chunks=[("fleet wide", vec)])
    tmp_store.write_thought(content="firstmate private", scope="bot:firstmate", chunks=[])
    fleet = tmp_store.list_thoughts(scope="fleet")
    bot = tmp_store.list_thoughts(scope="bot:firstmate")
    assert all(t["scope"] == "fleet" for t in fleet)
    assert all(t["scope"] == "bot:firstmate" for t in bot)


def test_chunk_text():
    long_text = "word " * 300
    chunks = chunk_text(long_text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 950


def test_embedder_fallback():
    """Embedder should return a unit vector even with hash fallback."""
    emb = Embedder("nonexistent-model-that-wont-load")
    vec = emb.embed_one("hello world")
    assert vec.shape == (384,)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 0.01
    assert emb.backend == "hash-fallback"


def test_stats(tmp_store):
    stats = tmp_store.stats()
    assert "thoughts" in stats
    assert "chunks" in stats
    assert "discord_messages" in stats
    assert "db_path" in stats

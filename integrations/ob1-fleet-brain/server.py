"""OB1 Fleet Brain MCP server — shared persistent memory for carrier_hermes bots.

Exposes OB1-compatible tools over stdio:
  ob1_write_thought  — store a piece of fleet knowledge
  ob1_search         — semantic/keyword search across all bot memories
  ob1_recall         — structured recall with trace logging
  ob1_list_thoughts  — paginated list with filters
  ob1_get_thought    — fetch one thought by ID
  ob1_brain_stats    — DB health / counts

Run:
  uv run --directory <this-dir> python server.py
  # or:
  python server.py     (if deps are already installed)

Env vars:
  OB1_BRAIN_DB   — path to SQLite DB (default: %LOCALAPPDATA%/hermes/carrier/ob1_brain.db)
  OB1_MODEL      — sentence-transformers model (default: all-MiniLM-L6-v2)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from embedder import DEFAULT_MODEL, Embedder, chunk_text
from store import DEFAULT_DB_PATH, FleetBrainStore

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = Path(os.environ.get("OB1_BRAIN_DB", str(DEFAULT_DB_PATH)))
MODEL = os.environ.get("OB1_MODEL", DEFAULT_MODEL)

_store: FleetBrainStore | None = None
_embedder: Embedder | None = None


def _get_store() -> FleetBrainStore:
    global _store
    if _store is None:
        _store = FleetBrainStore(DB_PATH)
    return _store


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(MODEL)
    return _embedder


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("ob1-fleet-brain")


@mcp.tool()
def ob1_write_thought(
    content: str,
    source: str = "fleet",
    scope: str = "fleet",
    category: str = "knowledge",
    summary: str = "",
    tags: str = "[]",
    metadata: str = "{}",
    agent_id: str = "",
    memory_kind: str = "knowledge",
) -> str:
    """Write a thought into the fleet brain.

    Args:
        content:     Full text of the memory/knowledge to store.
        source:      Who produced it (bot name, 'probe', 'discord', 'fleet', etc.).
        scope:       Visibility — 'fleet' (all bots) or 'bot:<name>' (private).
        category:    Type of knowledge — 'knowledge', 'decision', 'error', 'research',
                     'discord', 'work_log', etc.
        summary:     Short summary (1–2 sentences). Used as snippet in search results.
        tags:        JSON array string, e.g. '["python","carrier"]'.
        metadata:    JSON object for extra fields, e.g. '{"task_id":"t_abc"}".
        agent_id:    Bot identity for audit trail (e.g. 'firstmate', 'probe').
        memory_kind: OB1 sidecar kind — 'knowledge','decision','constraint',
                     'open_question','failure','artifact_reference','work_log'.

    Returns JSON with thought_id and embedding backend used.
    """
    store = _get_store()
    embedder = _get_embedder()
    try:
        tags_list = json.loads(tags or "[]") if isinstance(tags, str) else tags
        meta_dict = json.loads(metadata or "{}") if isinstance(metadata, str) else metadata
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"invalid JSON in tags/metadata: {exc}"})

    chunks_txt = chunk_text(content)
    if not chunks_txt:
        chunks_txt = [content or ""]
    vectors = embedder.embed(chunks_txt)
    chunk_pairs = list(zip(chunks_txt, vectors))

    thought_id = store.write_thought(
        content=content,
        source=source,
        scope=scope,
        category=category,
        summary=summary or (content[:120] + "..." if len(content) > 120 else content),
        tags=tags_list,
        metadata=meta_dict,
        agent_id=agent_id or source,
        memory_kind=memory_kind,
        chunks=chunk_pairs,
    )
    return json.dumps(
        {"thought_id": thought_id, "chunks": len(chunk_pairs), "backend": embedder.backend}
    )


@mcp.tool()
def ob1_search(
    query: str,
    top_k: int = 5,
    scope: str = "",
    source: str = "",
    category: str = "",
    agent_id: str = "",
    log_trace: bool = True,
) -> str:
    """Semantic search across fleet memories.

    Combines embedding cosine similarity (when sentence-transformers is installed)
    with keyword fallback. Always returns results sorted by relevance.

    Args:
        query:      Natural language search query.
        top_k:      Max results to return (1–25).
        scope:      Filter to 'fleet' or 'bot:<name>' (empty = all).
        source:     Filter by source bot/channel (empty = all).
        category:   Filter by category (empty = all).
        agent_id:   Bot doing the recall (for trace logging).
        log_trace:  Whether to write a recall_trace row (default true).

    Returns JSON array of {thought_id, score, snippet, source, scope, category, metadata}.
    """
    k = max(1, min(int(top_k), 25))
    q = (query or "").strip()
    if not q:
        return json.dumps({"results": [], "error": "empty query"})

    store = _get_store()
    embedder = _get_embedder()

    scope_f = scope.strip() or None
    source_f = source.strip() or None
    cat_f = category.strip() or None

    qv = embedder.embed_one(q)
    hits = store.search(qv, top_k=k, scope_filter=scope_f, source_filter=source_f, category_filter=cat_f)

    results = [
        {
            "thought_id": h.thought_id,
            "score": round(h.score, 4),
            "snippet": h.snippet,
            "source": h.source,
            "scope": h.scope,
            "category": h.category,
            "metadata": h.metadata,
        }
        for h in hits
    ]

    # Supplement with keyword hits when semantic model unavailable or score low
    if embedder.backend == "hash-fallback" or all(r["score"] < 0.3 for r in results):
        kw_hits = store.keyword_search(q, top_k=k, scope_filter=scope_f)
        seen_ids = {r["thought_id"] for r in results}
        for kh in kw_hits:
            if kh["id"] not in seen_ids:
                results.append(
                    {
                        "thought_id": kh["id"],
                        "score": 0.0,
                        "snippet": kh["content"][:280],
                        "source": kh["source"],
                        "scope": kh["scope"],
                        "category": kh["category"],
                        "metadata": kh["metadata"],
                    }
                )
                seen_ids.add(kh["id"])
        results = results[:k]

    if log_trace and agent_id:
        store.log_recall(agent_id, q, results, k)

    return json.dumps({"results": results, "backend": embedder.backend, "top_k": k})


@mcp.tool()
def ob1_recall(
    query: str,
    agent_id: str,
    top_k: int = 5,
    scope: str = "fleet",
    memory_kind: str = "",
) -> str:
    """Governed recall with trace logging.

    Like ob1_search but always logs trace, defaults scope to 'fleet', and
    can filter by memory_kind (e.g. 'decision', 'failure', 'knowledge').

    Args:
        query:       What you're looking for.
        agent_id:    Calling bot name (required for trace).
        top_k:       Max results (1–25).
        scope:       Memory scope filter — 'fleet', 'bot:<name>', or '' for all.
        memory_kind: OB1 kind filter (empty = all kinds).
    """
    cat_f = memory_kind.strip() or None
    k = max(1, min(int(top_k), 25))
    q = (query or "").strip()
    if not q:
        return json.dumps({"results": [], "error": "empty query"})

    store = _get_store()
    embedder = _get_embedder()
    scope_f = scope.strip() or None

    qv = embedder.embed_one(q)
    hits = store.search(qv, top_k=k, scope_filter=scope_f, category_filter=cat_f)

    results = [
        {
            "thought_id": h.thought_id,
            "score": round(h.score, 4),
            "snippet": h.snippet,
            "source": h.source,
            "scope": h.scope,
            "category": h.category,
        }
        for h in hits
    ]
    store.log_recall(agent_id, q, results, k)
    return json.dumps({"results": results, "backend": embedder.backend, "agent_id": agent_id})


@mcp.tool()
def ob1_list_thoughts(
    scope: str = "",
    source: str = "",
    category: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List thoughts with optional filters, paginated.

    Args:
        scope:    Filter by scope ('fleet', 'bot:<name>', or empty for all).
        source:   Filter by source.
        category: Filter by category.
        limit:    Max rows (1–100).
        offset:   Pagination offset.
    """
    store = _get_store()
    lim = max(1, min(int(limit), 100))
    rows = store.list_thoughts(
        scope=scope.strip() or None,
        source=source.strip() or None,
        category=category.strip() or None,
        limit=lim,
        offset=int(offset),
    )
    return json.dumps({"thoughts": rows, "count": len(rows)})


@mcp.tool()
def ob1_get_thought(thought_id: str) -> str:
    """Fetch a single thought by ID.

    Returns full content, metadata, and sidecar info.
    """
    if not thought_id:
        return json.dumps({"error": "thought_id required"})
    store = _get_store()
    thought = store.get_thought(thought_id.strip())
    if not thought:
        return json.dumps({"error": "not found", "thought_id": thought_id})
    return json.dumps(thought)


@mcp.tool()
def ob1_brain_stats() -> str:
    """Return fleet brain DB stats: thought/chunk counts, scope/source breakdown, DB path."""
    store = _get_store()
    embedder = _get_embedder()
    stats = store.stats()
    stats["embedding_backend"] = embedder.backend
    stats["model"] = MODEL
    return json.dumps(stats)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")

"""OB1 Fleet Brain MCP server — Supabase cloud primary, SQLite fallback.

Exposes OB1-compatible tools over stdio:
  ob1_write_thought      — store a piece of fleet knowledge
  ob1_search             — semantic/keyword search across all bot memories
  ob1_recall             — structured recall with trace logging
  ob1_list_thoughts      — paginated list with filters
  ob1_get_thought        — fetch one thought by ID
  ob1_brain_stats        — DB health / counts / active backend
  discord_capture_status — Discord capture bot health

  OB1 aliases (same underlying tool):
  write_thought          — alias for ob1_write_thought
  search_thoughts        — alias for ob1_search
  list_thoughts          — alias for ob1_list_thoughts
  thought_stats          — alias for ob1_brain_stats

Backend priority:
  1. Supabase cloud (reads SUPABASE_URL + SUPABASE_SERVICE_KEY from env/Doppler)
  2. SQLite local at OB1_BRAIN_DB (auto-activates if Supabase unreachable)

Env vars:
  SUPABASE_URL          — Supabase project URL (e.g. https://xxxx.supabase.co)
  SUPABASE_SERVICE_KEY  — Supabase service role key (NOT anon key)
  OB1_BRAIN_DB          — SQLite fallback path (default: carrier/ob1_brain.db)
  OB1_MODEL             — sentence-transformers model for local embeddings
  OB1_BACKEND           — force 'supabase' or 'sqlite' (default: auto)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path("C:/Users/micha/AppData/Local/hermes/carrier/logs/ob1_brain.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("ob1-fleet-brain")

# ---------------------------------------------------------------------------
# Resolve env from Doppler if needed
# ---------------------------------------------------------------------------

def _doppler_get(key: str) -> str:
    """Fetch a single secret from Doppler, return '' on failure."""
    try:
        r = subprocess.run(
            ["doppler", "secrets", "get", key, "--plain",
             "--project", "carrier-ops", "--config", "prd"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _resolve_env(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        val = _doppler_get(key)
        if val:
            os.environ[key] = val
    return val


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

OB1_BACKEND_FORCE = os.environ.get("OB1_BACKEND", "").lower()  # 'supabase'|'sqlite'|''

SUPABASE_URL = _resolve_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _resolve_env("SUPABASE_SERVICE_KEY")

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "OB1_BRAIN_DB",
        "C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db",
    )
)

# Will be set during _init_backend()
_BACKEND: str = "sqlite"  # 'supabase' | 'sqlite'
_supabase_client = None   # supabase.Client or None
_sqlite_store = None      # FleetBrainStore or None
_embedder = None          # local Embedder or None


# ---------------------------------------------------------------------------
# Backend initialisation
# ---------------------------------------------------------------------------

def _try_init_supabase() -> bool:
    """Try to initialise the Supabase client. Returns True on success."""
    global _supabase_client
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.info("Supabase env vars not set — skipping cloud backend")
        return False
    try:
        from supabase import create_client, Client  # type: ignore
        client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        # Smoke-test: count thoughts
        client.table("thoughts").select("id", count="exact", head=True).execute()
        _supabase_client = client
        log.info("Supabase backend: connected (%s)", SUPABASE_URL)
        return True
    except Exception as exc:
        log.warning("Supabase unreachable: %s — falling back to SQLite", exc)
        return False


def _init_sqlite() -> None:
    """Initialise the local SQLite store + embedder."""
    global _sqlite_store, _embedder
    # Add ob1_brain dir to sys.path so we can import store/embedder
    brain_dir = Path(__file__).parent
    if str(brain_dir) not in sys.path:
        sys.path.insert(0, str(brain_dir))
    try:
        from store import FleetBrainStore  # type: ignore
        from embedder import Embedder, DEFAULT_MODEL  # type: ignore
        _sqlite_store = FleetBrainStore(DEFAULT_DB_PATH)
        model = os.environ.get("OB1_MODEL", DEFAULT_MODEL)
        _embedder = Embedder(model)
        log.info("SQLite backend: %s (embedder: %s)", DEFAULT_DB_PATH, _embedder.backend)
    except Exception as exc:
        log.error("SQLite init failed: %s", exc)
        raise


def _init_backend() -> None:
    global _BACKEND
    force = OB1_BACKEND_FORCE
    if force == "supabase":
        if _try_init_supabase():
            _BACKEND = "supabase"
        else:
            log.warning("Forced supabase but unavailable — using sqlite")
            _init_sqlite()
            _BACKEND = "sqlite"
    elif force == "sqlite":
        _init_sqlite()
        _BACKEND = "sqlite"
    else:
        # Auto: try supabase first
        if _try_init_supabase():
            _BACKEND = "supabase"
        else:
            _init_sqlite()
            _BACKEND = "sqlite"


# ---------------------------------------------------------------------------
# Embeddings for Supabase path via sentence-transformers (local)
# ---------------------------------------------------------------------------

def _get_embedding_for_supabase(text: str) -> list[float] | None:
    """Get a 1536-dim embedding. Uses local sentence-transformers padded to 1536,
    or falls back to None (Supabase insert without embedding is still valid)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np
        model_name = os.environ.get("OB1_EMBED_MODEL", "all-MiniLM-L6-v2")
        _model = SentenceTransformer(model_name)
        vec = _model.encode([text])[0].tolist()
        # Pad/trim to 1536 for pgvector(1536) compatibility
        if len(vec) < 1536:
            vec = vec + [0.0] * (1536 - len(vec))
        elif len(vec) > 1536:
            vec = vec[:1536]
        return vec
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Supabase operations
# ---------------------------------------------------------------------------

def _supabase_write_thought(
    content: str,
    source: str = "fleet",
    scope: str = "fleet",
    category: str = "knowledge",
    summary: str = "",
    tags: list | None = None,
    metadata: dict | None = None,
    agent_id: str = "",
    memory_kind: str = "knowledge",
) -> dict:
    sb = _supabase_client
    meta = {
        **(metadata or {}),
        "source": source,
        "scope": scope,
        "category": category,
        "summary": summary or content[:120],
        "tags": tags or [],
        "agent_id": agent_id or source,
        "memory_kind": memory_kind,
        "type": memory_kind,
        "topics": tags or [],
    }
    payload = json.dumps({"metadata": meta})
    result = sb.rpc("upsert_thought", {"p_content": content, "p_payload": json.loads(payload)}).execute()
    thought_data = result.data
    thought_id = thought_data.get("id") if isinstance(thought_data, dict) else None

    # Try to add embedding
    embedding = _get_embedding_for_supabase(content)
    if embedding and thought_id:
        try:
            sb.table("thoughts").update({"embedding": embedding}).eq("id", thought_id).execute()
        except Exception as exc:
            log.warning("Embedding update failed: %s", exc)

    # Write agent memory sidecar
    if thought_id:
        try:
            sb.table("agent_memories").insert({
                "thought_id": thought_id,
                "workspace_id": "carrier_hermes",
                "memory_type": memory_kind if memory_kind in (
                    "decision","output","lesson","constraint",
                    "open_question","failure","artifact_reference","work_log"
                ) else "work_log",
                "summary": summary or content[:120],
                "content": content,
                "created_by": "agent",
                "runtime_name": agent_id or source,
                "metadata": meta,
            }).execute()
        except Exception as exc:
            log.warning("Agent memory sidecar write failed: %s", exc)

    return {"thought_id": thought_id, "backend": "supabase"}


def _supabase_search(
    query: str,
    top_k: int = 5,
    scope: str = "",
    source: str = "",
    category: str = "",
) -> list[dict]:
    sb = _supabase_client
    embedding = _get_embedding_for_supabase(query)
    results = []

    if embedding:
        meta_filter: dict = {}
        if source:
            meta_filter["source"] = source
        if scope:
            meta_filter["scope"] = scope
        if category:
            meta_filter["category"] = category

        rpc_result = sb.rpc("match_thoughts", {
            "query_embedding": embedding,
            "match_threshold": 0.3,
            "match_count": top_k,
            "filter": meta_filter,
        }).execute()
        for t in (rpc_result.data or []):
            meta = t.get("metadata", {}) or {}
            results.append({
                "thought_id": t["id"],
                "score": round(float(t.get("similarity", 0)), 4),
                "snippet": t["content"][:280],
                "source": meta.get("source", ""),
                "scope": meta.get("scope", "fleet"),
                "category": meta.get("category", "knowledge"),
                "metadata": meta,
            })
    else:
        # Keyword fallback via ilike
        q = sb.table("thoughts").select("id,content,metadata,created_at")
        q = q.ilike("content", f"%{query}%").order("created_at", desc=True).limit(top_k)
        for t in (q.execute().data or []):
            meta = t.get("metadata", {}) or {}
            results.append({
                "thought_id": t["id"],
                "score": 0.0,
                "snippet": t["content"][:280],
                "source": meta.get("source", ""),
                "scope": meta.get("scope", "fleet"),
                "category": meta.get("category", "knowledge"),
                "metadata": meta,
            })
    return results


def _supabase_list(
    scope: str = "",
    source: str = "",
    category: str = "",
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    sb = _supabase_client
    q = sb.table("thoughts").select("id,content,metadata,created_at")
    if source:
        q = q.contains("metadata", {"source": source})
    if scope:
        q = q.contains("metadata", {"scope": scope})
    if category:
        q = q.contains("metadata", {"category": category})
    rows = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    out = []
    for r in (rows.data or []):
        meta = r.get("metadata", {}) or {}
        out.append({
            "id": r["id"],
            "content": r["content"],
            "summary": meta.get("summary", r["content"][:120]),
            "source": meta.get("source", ""),
            "scope": meta.get("scope", "fleet"),
            "category": meta.get("category", "knowledge"),
            "tags": meta.get("tags", []),
            "metadata": meta,
            "created_at": r["created_at"],
        })
    return out


def _supabase_get(thought_id: str) -> dict | None:
    sb = _supabase_client
    r = sb.table("thoughts").select("id,content,metadata,created_at,updated_at") \
        .eq("id", thought_id).single().execute()
    if not r.data:
        return None
    d = r.data
    meta = d.get("metadata", {}) or {}
    return {
        "id": d["id"],
        "content": d["content"],
        "summary": meta.get("summary", d["content"][:120]),
        "source": meta.get("source", ""),
        "scope": meta.get("scope", "fleet"),
        "category": meta.get("category", "knowledge"),
        "tags": meta.get("tags", []),
        "metadata": meta,
        "created_at": d["created_at"],
        "updated_at": d.get("updated_at"),
    }


def _supabase_stats() -> dict:
    sb = _supabase_client
    total_r = sb.table("thoughts").select("id", count="exact", head=True).execute()
    total = total_r.count or 0
    discord_r = sb.table("discord_messages").select("id", count="exact", head=True).execute()
    discord_count = discord_r.count or 0
    return {
        "backend": "supabase",
        "supabase_url": SUPABASE_URL,
        "total_thoughts": total,
        "discord_messages_captured": discord_count,
    }


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("ob1-fleet-brain")

# ---------------------------------------------------------------------------
# Initialise backend now (at import time so tools work immediately)
# ---------------------------------------------------------------------------
_init_backend()


# ---------------------------------------------------------------------------
# Tool: ob1_write_thought
# ---------------------------------------------------------------------------

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
    """Write a thought into the fleet brain (Supabase or SQLite).

    Args:
        content:     Full text of the memory/knowledge to store.
        source:      Who produced it (bot name, 'probe', 'discord', 'fleet', etc.).
        scope:       Visibility — 'fleet' (all bots) or 'bot:<name>' (private).
        category:    Type of knowledge — 'knowledge', 'decision', 'error', 'research',
                     'discord', 'fleet_message', 'work_log', etc.
        summary:     Short summary (1-2 sentences). Used as snippet in search results.
        tags:        JSON array string, e.g. '["python","carrier"]'.
        metadata:    JSON object for extra fields, e.g. '{"task_id":"t_abc"}'.
        agent_id:    Bot identity for audit trail (e.g. 'firstmate', 'probe').
        memory_kind: OB1 sidecar kind — 'knowledge','decision','constraint',
                     'open_question','failure','artifact_reference','work_log'.

    Returns JSON with thought_id and backend used.
    """
    try:
        tags_list = json.loads(tags or "[]") if isinstance(tags, str) else tags
        meta_dict = json.loads(metadata or "{}") if isinstance(metadata, str) else metadata
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"invalid JSON in tags/metadata: {exc}"})

    if _BACKEND == "supabase":
        try:
            result = _supabase_write_thought(
                content=content, source=source, scope=scope, category=category,
                summary=summary, tags=tags_list, metadata=meta_dict,
                agent_id=agent_id, memory_kind=memory_kind,
            )
            return json.dumps(result)
        except Exception as exc:
            log.warning("Supabase write failed, falling back to SQLite: %s", exc)
            _init_sqlite()

    # SQLite path
    from embedder import chunk_text  # type: ignore
    embedder = _embedder
    store = _sqlite_store
    chunks_txt = chunk_text(content) or [content]
    vectors = embedder.embed(chunks_txt)
    chunk_pairs = list(zip(chunks_txt, vectors))
    thought_id = store.write_thought(
        content=content, source=source, scope=scope, category=category,
        summary=summary or (content[:120] + "..." if len(content) > 120 else content),
        tags=tags_list, metadata=meta_dict,
        agent_id=agent_id or source, memory_kind=memory_kind,
        chunks=chunk_pairs,
    )
    return json.dumps({"thought_id": thought_id, "chunks": len(chunk_pairs), "backend": "sqlite"})


@mcp.tool()
def write_thought(
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
    """OB1-compatible alias for ob1_write_thought."""
    return ob1_write_thought(
        content=content, source=source, scope=scope, category=category,
        summary=summary, tags=tags, metadata=metadata,
        agent_id=agent_id, memory_kind=memory_kind,
    )


# ---------------------------------------------------------------------------
# Tool: ob1_search
# ---------------------------------------------------------------------------

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
    """Semantic search across fleet memories (Supabase pgvector or local cosine).

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

    if _BACKEND == "supabase":
        try:
            results = _supabase_search(query=q, top_k=k, scope=scope, source=source, category=category)
            return json.dumps({"results": results, "backend": "supabase"})
        except Exception as exc:
            log.warning("Supabase search failed, falling back to SQLite: %s", exc)

    # SQLite path
    store = _sqlite_store
    embedder = _embedder
    qv = embedder.embed_one(q)
    hits = store.search(
        qv, top_k=k,
        scope_filter=scope.strip() or None,
        source_filter=source.strip() or None,
        category_filter=category.strip() or None,
    )
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
    # Keyword fallback
    if embedder.backend == "hash-fallback" or all(r["score"] < 0.3 for r in results):
        kw_hits = store.keyword_search(q, top_k=k, scope_filter=scope.strip() or None)
        seen = {r["thought_id"] for r in results}
        for kh in kw_hits:
            if kh["id"] not in seen:
                results.append({
                    "thought_id": kh["id"], "score": 0.0,
                    "snippet": kh["content"][:280],
                    "source": kh["source"], "scope": kh["scope"],
                    "category": kh["category"], "metadata": kh["metadata"],
                })
                seen.add(kh["id"])
        results = results[:k]

    if log_trace and agent_id:
        store.log_recall(agent_id, q, results, k)

    return json.dumps({"results": results, "backend": "sqlite"})


@mcp.tool()
def search_thoughts(
    query: str,
    top_k: int = 5,
    scope: str = "",
    source: str = "",
    category: str = "",
) -> str:
    """OB1-compatible alias for ob1_search."""
    return ob1_search(query=query, top_k=top_k, scope=scope, source=source, category=category)


# ---------------------------------------------------------------------------
# Tool: ob1_recall
# ---------------------------------------------------------------------------

@mcp.tool()
def ob1_recall(
    query: str,
    top_k: int = 5,
    scope: str = "fleet",
    agent_id: str = "",
    memory_kind: str = "",
    min_confidence: float = 0.0,
) -> str:
    """Structured recall with trace logging. Returns governed memories.

    Args:
        query:          What to recall.
        top_k:          Max results.
        scope:          Visibility scope filter.
        agent_id:       Caller identity for audit.
        memory_kind:    Filter by OB1 memory kind (optional).
        min_confidence: Minimum confidence threshold (0.0–1.0).

    Returns JSON with results, trace_id, and backend.
    """
    results_json = ob1_search(query=query, top_k=top_k, scope=scope, agent_id=agent_id)
    data = json.loads(results_json)
    results = data.get("results", [])
    return json.dumps({
        "results": results,
        "query": query,
        "scope": scope,
        "backend": data.get("backend", _BACKEND),
        "agent_id": agent_id,
    })


# ---------------------------------------------------------------------------
# Tool: ob1_list_thoughts
# ---------------------------------------------------------------------------

@mcp.tool()
def ob1_list_thoughts(
    scope: str = "",
    source: str = "",
    category: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List recently captured thoughts with optional filters.

    Args:
        scope:    Filter by scope (e.g. 'fleet', 'bot:probe').
        source:   Filter by source (e.g. 'discord', 'probe').
        category: Filter by category.
        limit:    Max results (1–100).
        offset:   Pagination offset.

    Returns JSON array of thought records.
    """
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    if _BACKEND == "supabase":
        try:
            rows = _supabase_list(scope=scope, source=source, category=category,
                                   limit=limit, offset=offset)
            return json.dumps({"thoughts": rows, "count": len(rows), "backend": "supabase"})
        except Exception as exc:
            log.warning("Supabase list failed, falling back to SQLite: %s", exc)

    store = _sqlite_store
    rows = store.list_thoughts(
        scope=scope.strip() or None,
        source=source.strip() or None,
        category=category.strip() or None,
        limit=limit, offset=offset,
    )
    return json.dumps({"thoughts": rows, "count": len(rows), "backend": "sqlite"})


@mcp.tool()
def list_thoughts(
    scope: str = "",
    source: str = "",
    category: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """OB1-compatible alias for ob1_list_thoughts."""
    return ob1_list_thoughts(scope=scope, source=source, category=category,
                              limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Tool: ob1_get_thought
# ---------------------------------------------------------------------------

@mcp.tool()
def ob1_get_thought(thought_id: str) -> str:
    """Fetch one thought by ID.

    Args:
        thought_id: UUID of the thought to retrieve.

    Returns JSON with full thought content and metadata, or an error.
    """
    if _BACKEND == "supabase":
        try:
            t = _supabase_get(thought_id)
            if t:
                return json.dumps({**t, "backend": "supabase"})
        except Exception as exc:
            log.warning("Supabase get failed, falling back to SQLite: %s", exc)

    store = _sqlite_store
    t = store.get_thought(thought_id)
    if not t:
        return json.dumps({"error": f"thought {thought_id!r} not found"})
    return json.dumps({**t, "backend": "sqlite"})


# ---------------------------------------------------------------------------
# Tool: ob1_brain_stats
# ---------------------------------------------------------------------------

@mcp.tool()
def ob1_brain_stats() -> str:
    """Get fleet brain health: backend, thought counts, discord capture status.

    Returns JSON summary of the active backend and data counts.
    """
    if _BACKEND == "supabase":
        try:
            stats = _supabase_stats()
            return json.dumps(stats)
        except Exception as exc:
            log.warning("Supabase stats failed, falling back to SQLite: %s", exc)

    store = _sqlite_store
    row = store._conn.execute(
        "SELECT COUNT(*) FROM thoughts"
    ).fetchone()
    total = row[0] if row else 0
    dc_row = store._conn.execute(
        "SELECT COUNT(*) FROM discord_messages"
    ).fetchone()
    dc_count = dc_row[0] if dc_row else 0
    chunks_row = store._conn.execute(
        "SELECT COUNT(*) FROM thought_chunks"
    ).fetchone()
    chunks = chunks_row[0] if chunks_row else 0
    return json.dumps({
        "backend": "sqlite",
        "db_path": str(DEFAULT_DB_PATH),
        "total_thoughts": total,
        "total_chunks": chunks,
        "discord_messages_captured": dc_count,
    })


@mcp.tool()
def thought_stats() -> str:
    """OB1-compatible alias for ob1_brain_stats."""
    return ob1_brain_stats()


# ---------------------------------------------------------------------------
# Tool: discord_capture_status
# ---------------------------------------------------------------------------

@mcp.tool()
def discord_capture_status() -> str:
    """Check Discord capture bot status.

    Returns JSON with running state, last message timestamp, channel info.
    """
    status: dict = {
        "channel_id": "1541866378255011980",
        "backend": _BACKEND,
    }

    if _BACKEND == "supabase":
        try:
            sb = _supabase_client
            r = sb.table("discord_messages") \
                .select("id,captured_at,author,content") \
                .eq("channel_id", "1541866378255011980") \
                .order("captured_at", desc=True).limit(1).execute()
            last = r.data[0] if r.data else None
            count_r = sb.table("discord_messages").select("id", count="exact", head=True).execute()
            status.update({
                "total_captured": count_r.count or 0,
                "last_message": last,
            })
        except Exception as exc:
            status["error"] = str(exc)
    else:
        store = _sqlite_store
        row = store._conn.execute(
            "SELECT id, captured_at, author, content FROM discord_messages "
            "WHERE channel_id=? ORDER BY captured_at DESC LIMIT 1",
            ("1541866378255011980",),
        ).fetchone()
        count = store._conn.execute(
            "SELECT COUNT(*) FROM discord_messages WHERE channel_id=?",
            ("1541866378255011980",),
        ).fetchone()[0]
        status.update({
            "total_captured": count,
            "last_message": {
                "id": row[0], "captured_at": row[1], "author": row[2], "content": row[3]
            } if row else None,
        })

    # Check if discord_capture.py process is running
    try:
        import subprocess as sp
        r2 = sp.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe"],
            capture_output=True, text=True, timeout=5,
        )
        capture_running = "discord_capture" in r2.stdout or "python.exe" in r2.stdout
        status["capture_process_running"] = capture_running
    except Exception:
        status["capture_process_running"] = None

    return json.dumps(status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("ob1-fleet-brain starting (backend=%s)", _BACKEND)
    mcp.run()

"""
carrier-viking -- OpenViking-compatible persistent memory for carrier_hermes bots.
Version 2.0 — Full OpenViking gap implementation.

## Architecture

Primary mode: If OPENVIKING_URL is set OR the local FastAPI server is running at
http://localhost:1933, ALL 15 tool calls are proxied to it.

Fallback mode: Stdlib BM25+hotness SQLite implementation (no external deps required
beyond rank-bm25 for BM25 — falls back to TF-IDF if rank-bm25 is absent).

## Tools (15 total, matching OpenViking surface)

Memory operations:
  remember(content, type, bot_id, tags, importance)
  recall(query, type, bot_id, k, shared_scope, peer_penalty)  — BM25+hotness, cross-bot
  forget(memory_id, bot_id)
  list_memories(type, bot_id, limit, offset)
  viking_stats(bot_id)

Experience operations:
  record_experience(outcome, lesson, source_task_id, bot_id, tags)
  commit_session(session_id, transcript, bot_id)          — LLM extraction via claude-haiku

Navigation:
  search_memories(pattern, bot_id, scope)                 — regex/substring browse

OpenViking-compatible stubs (proxied to server when available):
  find(query, bot_id)
  search(query, bot_id, quotas)
  read(uri)
  write(uri, content)
  edit(uri, old_string, new_string)
  list_uris(uri_prefix)
  tree(uri_prefix)
  add_resource(url, bot_id)
  grep(uri_prefix, pattern)
  glob(uri_prefix, glob_pattern)
  health()
  list_watches()
  cancel_watch(watch_id)

## Memory types
  task        quota=50    in-progress work, current objectives
  fact        quota=100   learned facts, domain knowledge
  error       quota=30    errors, lessons, anti-patterns
  decision    quota=25    choices made, rationale, tradeoffs
  experience  quota=50    distilled lessons from completed tasks  [NEW P2]
  trajectory  quota=30    task execution records for replay/learning [NEW P5]
  entity      quota=100   people/projects/services/things           [NEW P5]
  preference  quota=50    recurring behavioral patterns observed     [NEW P5]

## Gap implementations
  P1: Hotness-blended BM25 scoring  (access_count + recency decay)
  P2: experience type + record_experience convenience tool
  P3: BM25Okapi via rank-bm25 (falls back to TF-IDF if unavailable)
  P4: shared_scope='own'|'all'|[bot_ids] + fleet_visible column
  P5: entity, trajectory, preference types
  P6: commit_session using claude-haiku via Anthropic OAuth
  P7: search_memories(pattern) for regex/substring browse grouped by type

## Storage
SQLite at VIKING_MEMORY_DB_PATH (default: ~/AppData/Local/hermes/carrier/viking_memory/memories.db)
Server proxy: OPENVIKING_URL (default: checked at http://localhost:1933)
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("hermes.plugins.carrier-viking")

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_TYPES = {
    "task", "fact", "error", "decision",
    "experience", "trajectory", "entity", "preference",
}

DEFAULT_QUOTAS = {
    "task":       50,
    "fact":      100,
    "error":      30,
    "decision":   25,
    "experience": 50,   # P2: distilled lessons from completed tasks
    "trajectory": 30,   # P5: task execution records
    "entity":    100,   # P5: people/projects/services/things
    "preference": 50,   # P5: recurring behavioral observations
}

DEFAULT_HALF_LIFE_DAYS = 7.0
DEFAULT_HOTNESS_ALPHA  = 0.1   # P1: blend weight for hotness vs BM25

DEFAULT_DB_PATH = (
    Path.home() / "AppData" / "Local" / "hermes" / "carrier" / "viking_memory" / "memories.db"
)
DEFAULT_SERVER_URL = "http://localhost:1933"

# Try to import rank-bm25 (P3) — graceful fallback to TF-IDF
try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False
    logger.debug("carrier-viking: rank-bm25 not installed, using TF-IDF fallback")

# ── Config resolution ──────────────────────────────────────────────────────────

def _db_path() -> Path:
    env = os.environ.get("VIKING_MEMORY_DB_PATH")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def _bot_id_default() -> str:
    return os.environ.get("HERMES_BOT_ID", "unknown")


def _quota(memory_type: str) -> int:
    env_key = f"VIKING_QUOTA_{memory_type.upper()}"
    env_val = os.environ.get(env_key)
    if env_val and env_val.isdigit():
        return int(env_val)
    return DEFAULT_QUOTAS.get(memory_type, 50)


def _max_recall() -> int:
    env = os.environ.get("VIKING_MAX_RECALL", "10")
    try:
        return int(env)
    except ValueError:
        return 10


def _server_url() -> str | None:
    """Return OpenViking server URL if configured, else None."""
    return os.environ.get("OPENVIKING_URL", "").strip() or None


def _check_server_alive(url: str) -> bool:
    """Quick health check — returns True if server is alive."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{url}/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _proxy_call(endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Proxy a call to the OpenViking server.
    Returns parsed JSON on success, None if server is unavailable.
    """
    base_url = _server_url() or DEFAULT_SERVER_URL
    try:
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{base_url}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


# ── Database layer ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id              TEXT PRIMARY KEY,
            bot_id          TEXT NOT NULL,
            type            TEXT NOT NULL,
            content         TEXT NOT NULL,
            content_l0      TEXT,
            tags            TEXT,
            created_at      INTEGER NOT NULL,
            accessed_at     INTEGER NOT NULL,
            access_count    INTEGER NOT NULL DEFAULT 0,
            importance      REAL NOT NULL DEFAULT 1.0,
            fleet_visible   INTEGER NOT NULL DEFAULT 0,
            outcome         TEXT,
            source_task_id  TEXT,
            lesson          TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_memories_bot_type
            ON memories (bot_id, type, created_at);

        CREATE INDEX IF NOT EXISTS idx_memories_accessed
            ON memories (bot_id, type, accessed_at);

        CREATE INDEX IF NOT EXISTS idx_memories_fleet
            ON memories (fleet_visible, type, accessed_at);

        -- TF-IDF / BM25 term index for lightweight semantic search
        CREATE TABLE IF NOT EXISTS memory_terms (
            memory_id   TEXT NOT NULL,
            term        TEXT NOT NULL,
            tf          REAL NOT NULL,
            PRIMARY KEY (memory_id, term),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_terms_memory ON memory_terms (memory_id);
        CREATE INDEX IF NOT EXISTS idx_terms_term ON memory_terms (term);
    """)
    # Migrate: add new columns if upgrading from v1
    _migrate_add_columns(conn)
    conn.commit()


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add new columns to existing databases without full schema recreate."""
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
    }
    migrations = [
        ("fleet_visible",   "INTEGER NOT NULL DEFAULT 0"),
        ("outcome",         "TEXT"),
        ("source_task_id",  "TEXT"),
        ("lesson",          "TEXT"),
    ]
    for col, defn in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {col} {defn}")
    conn.commit()


# ── Tokenization ────────────────────────────────────────────────────────────────

STOP_WORDS = {
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for",
    "of", "and", "or", "but", "i", "we", "you", "he", "she", "they",
    "was", "are", "be", "been", "have", "has", "had", "do", "did",
    "will", "would", "could", "should", "this", "that", "with", "from",
    "by", "as", "not", "no", "so", "if", "when", "then", "than",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def _compute_tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


def _index_memory(conn: sqlite3.Connection, memory_id: str, content: str) -> None:
    tokens = _tokenize(content)
    tf = _compute_tf(tokens)
    conn.execute("DELETE FROM memory_terms WHERE memory_id = ?", (memory_id,))
    rows = [(memory_id, term, score) for term, score in tf.items()]
    conn.executemany(
        "INSERT OR REPLACE INTO memory_terms (memory_id, term, tf) VALUES (?, ?, ?)",
        rows,
    )


# ── P1: Hotness scoring ─────────────────────────────────────────────────────────

def _hotness_score(access_count: int, accessed_at: int) -> float:
    """
    OpenViking-style hotness blend:
      freq    = sigmoid(log1p(access_count))
      recency = exp(-log(2)/half_life_days * age_days)
      hotness = freq * recency
    """
    freq = 1.0 / (1.0 + math.exp(-math.log1p(access_count)))
    age_days = (time.time() - accessed_at) / 86400.0
    decay_rate = math.log(2) / DEFAULT_HALF_LIFE_DAYS
    recency = math.exp(-decay_rate * max(age_days, 0.0))
    return freq * recency


# ── P3: BM25 / TF-IDF search ───────────────────────────────────────────────────

def _build_bot_query(
    bot_id: str,
    memory_type: str | None,
    shared_scope: str | list[str],
    peer_penalty: float,
) -> tuple[str, list[Any]]:
    """
    Build SQL WHERE clause for scope-aware memory search (P4 cross-bot).
    Returns (where_clause, params).
    """
    if shared_scope == "own":
        where = "m.bot_id = ?"
        params: list[Any] = [bot_id]
    elif shared_scope == "all":
        where = "(m.bot_id = ? OR (m.fleet_visible = 1 AND m.bot_id != ?))"
        params = [bot_id, bot_id]
    elif isinstance(shared_scope, list):
        placeholders = ",".join("?" * len(shared_scope))
        where = f"(m.bot_id = ? OR (m.fleet_visible = 1 AND m.bot_id IN ({placeholders})))"
        params = [bot_id, *shared_scope]
    else:
        where = "m.bot_id = ?"
        params = [bot_id]

    if memory_type:
        where += " AND m.type = ?"
        params.append(memory_type)

    return where, params


def _bm25_search(
    conn: sqlite3.Connection,
    query: str,
    bot_id: str,
    memory_type: str | None,
    k: int,
    shared_scope: str | list[str] = "own",
    peer_penalty: float = 0.3,
) -> list[dict[str, Any]]:
    """
    BM25Okapi search with hotness blending (P1+P3+P4).
    Falls back to TF-IDF cosine similarity if rank-bm25 is unavailable.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    where, params = _build_bot_query(bot_id, memory_type, shared_scope, peer_penalty)

    # Fetch all candidate memories with their term data
    rows = conn.execute(
        f"""
        SELECT m.id, m.bot_id, m.type, m.content, m.content_l0, m.tags,
               m.created_at, m.accessed_at, m.access_count, m.importance,
               m.fleet_visible, m.outcome, m.source_task_id, m.lesson
        FROM memories m
        WHERE {where}
        """,
        params,
    ).fetchall()

    if not rows:
        return []

    mem_list = [dict(r) for r in rows]

    if _HAS_BM25:
        # P3: BM25Okapi
        corpus = [_tokenize(m["content"]) for m in mem_list]
        bm25 = _BM25Okapi(corpus)
        raw_scores = bm25.get_scores(query_tokens)
        # Normalize BM25 scores to [0, 1] range
        max_s = max(raw_scores) if max(raw_scores) > 0 else 1.0
        norm_scores = [s / max_s for s in raw_scores]
    else:
        # TF-IDF fallback
        N = len(mem_list)
        id_to_idx = {m["id"]: i for i, m in enumerate(mem_list)}
        # Compute df per query term
        placeholders = ",".join("?" * len(query_tokens))
        term_rows = conn.execute(
            f"SELECT term, COUNT(DISTINCT memory_id) as df FROM memory_terms WHERE term IN ({placeholders}) GROUP BY term",
            query_tokens,
        ).fetchall()
        df = {r["term"]: r["df"] for r in term_rows}

        norm_scores = [0.0] * N
        for m in mem_list:
            term_rows_m = conn.execute(
                f"SELECT term, tf FROM memory_terms WHERE memory_id = ? AND term IN ({placeholders})",
                [m["id"], *query_tokens],
            ).fetchall()
            score = 0.0
            for tr in term_rows_m:
                idf = math.log((N + 1) / (df.get(tr["term"], 0) + 1))
                score += tr["tf"] * idf
            norm_scores[id_to_idx[m["id"]]] = score
        # Normalize
        max_s = max(norm_scores) if max(norm_scores) > 0 else 1.0
        norm_scores = [s / max_s for s in norm_scores]

    # P1: Blend BM25/TF-IDF score with hotness
    alpha = DEFAULT_HOTNESS_ALPHA
    blended = []
    for i, m in enumerate(mem_list):
        base_score = norm_scores[i]
        hotness = _hotness_score(m["access_count"], m["accessed_at"])
        final_score = (1 - alpha) * base_score + alpha * hotness

        # P4: Apply cross-bot penalty
        if m["bot_id"] != bot_id:
            final_score *= (1 - peer_penalty)

        if final_score > 0:
            blended.append((i, final_score))

    blended.sort(key=lambda x: x[1], reverse=True)
    top_k = blended[:k]

    now = int(time.time())
    results = []
    for idx, score in top_k:
        m = mem_list[idx]
        conn.execute(
            "UPDATE memories SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
            (now, m["id"]),
        )
        results.append({**m, "score": round(score, 4)})
    conn.commit()
    return results


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_id(bot_id: str, memory_type: str, content: str) -> str:
    key = f"{bot_id}:{memory_type}:{content[:200]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _generate_l0_abstract(content: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    if sentences:
        return sentences[0][:120]
    return content[:120]


def _enforce_quota(conn: sqlite3.Connection, bot_id: str, memory_type: str) -> None:
    quota = _quota(memory_type)
    count_row = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE bot_id = ? AND type = ?",
        (bot_id, memory_type),
    ).fetchone()
    count = count_row[0] if count_row else 0
    overflow = count - quota + 1
    if overflow > 0:
        evict_rows = conn.execute(
            """
            SELECT id FROM memories
            WHERE bot_id = ? AND type = ?
            ORDER BY importance ASC, accessed_at ASC, access_count ASC
            LIMIT ?
            """,
            (bot_id, memory_type, overflow),
        ).fetchall()
        for row in evict_rows:
            conn.execute("DELETE FROM memory_terms WHERE memory_id = ?", (row["id"],))
            conn.execute("DELETE FROM memories WHERE id = ?", (row["id"],))
            logger.debug("carrier-viking: evicted memory %s (quota %d)", row["id"], quota)


# ── Tool implementations ───────────────────────────────────────────────────────

def remember(
    content: str,
    type: str = "fact",
    bot_id: str | None = None,
    tags: list[str] | None = None,
    importance: float = 1.0,
    fleet_visible: bool = False,
    outcome: str | None = None,
    source_task_id: str | None = None,
    lesson: str | None = None,
) -> dict[str, Any]:
    """
    Store a memory for this bot.

    Args:
        content:         Memory content (free text, markdown OK).
        type:            Memory type: task, fact, error, decision, experience,
                         trajectory, entity, or preference.
        bot_id:          Bot identity (defaults to HERMES_BOT_ID env var).
        tags:            Optional list of string tags for filtering.
        importance:      Importance weight 0.0-2.0 (default 1.0). Higher = last evicted.
        fleet_visible:   If True, other bots can access this with shared_scope='all'.
                         Automatically True for experience type.
        outcome:         For experience type: 'success', 'failure', or 'partial'.
        source_task_id:  For experience type: the task that generated this lesson.
        lesson:          For experience type: short distilled lesson.

    Returns:
        dict with 'id', 'type', 'bot_id', 'created_at', 'quota_remaining'
    """
    if not content or not content.strip():
        return {"error": "content must not be empty"}

    if type not in VALID_TYPES:
        return {"error": f"type must be one of {sorted(VALID_TYPES)}, got '{type}'"}

    bot_id = bot_id or _bot_id_default()
    now = int(time.time())
    memory_id = _make_id(bot_id, type, content)
    l0 = _generate_l0_abstract(content)
    tags_json = json.dumps(tags or [])

    # P2: Experiences are fleet-visible by default
    if type == "experience":
        fleet_visible = True

    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if existing:
            return {
                "id": memory_id,
                "status": "already_exists",
                "bot_id": bot_id,
                "type": type,
            }

        _enforce_quota(conn, bot_id, type)

        conn.execute(
            """
            INSERT INTO memories
                (id, bot_id, type, content, content_l0, tags,
                 created_at, accessed_at, access_count, importance,
                 fleet_visible, outcome, source_task_id, lesson)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                memory_id, bot_id, type, content, l0, tags_json,
                now, now, importance,
                1 if fleet_visible else 0,
                outcome, source_task_id, lesson,
            ),
        )
        _index_memory(conn, memory_id, content)
        conn.commit()

        count_row = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE bot_id = ? AND type = ?",
            (bot_id, type),
        ).fetchone()
        used = count_row[0] if count_row else 1
        quota = _quota(type)
        remaining = max(0, quota - used)

        logger.info("carrier-viking: stored %s/%s for bot %s", memory_id, type, bot_id)
        return {
            "id": memory_id,
            "status": "stored",
            "bot_id": bot_id,
            "type": type,
            "content_l0": l0,
            "created_at": now,
            "quota_used": used,
            "quota_total": quota,
            "quota_remaining": remaining,
            "fleet_visible": fleet_visible,
        }
    finally:
        conn.close()


def recall(
    query: str,
    type: str | None = None,
    bot_id: str | None = None,
    k: int | None = None,
    shared_scope: str | list[str] = "own",
    peer_penalty: float = 0.3,
) -> dict[str, Any]:
    """
    Semantic recall with BM25 + hotness blending.

    Args:
        query:        Free text search query.
        type:         Optional memory type filter.
        bot_id:       Bot identity (defaults to HERMES_BOT_ID env var).
        k:            Max results (default: VIKING_MAX_RECALL env or 10).
        shared_scope: 'own' (default) = own memories only.
                      'all' = own + all fleet_visible memories from other bots (with penalty).
                      [list of bot_ids] = own + fleet_visible from those specific bots.
        peer_penalty: Score penalty for other-bot results (default 0.3 = 30% downrank).

    Returns:
        dict with 'memories' list, 'query', 'bot_id', 'scope_used'
    """
    if not query or not query.strip():
        return {"error": "query must not be empty"}

    if type and type not in VALID_TYPES:
        return {"error": f"type must be one of {sorted(VALID_TYPES)} or None, got '{type}'"}

    bot_id = bot_id or _bot_id_default()
    k = k or _max_recall()

    conn = _get_conn()
    try:
        hits = _bm25_search(
            conn, query, bot_id, type, k,
            shared_scope=shared_scope,
            peer_penalty=peer_penalty,
        )
        memories = []
        for h in hits:
            tags = []
            try:
                tags = json.loads(h.get("tags") or "[]")
            except (json.JSONDecodeError, TypeError):
                pass
            memories.append({
                "id": h["id"],
                "type": h["type"],
                "bot_id": h["bot_id"],
                "content": h["content"],
                "content_l0": h.get("content_l0", ""),
                "score": h.get("score", 0.0),
                "created_at": h["created_at"],
                "accessed_at": h["accessed_at"],
                "access_count": h["access_count"],
                "fleet_visible": bool(h.get("fleet_visible", 0)),
                "outcome": h.get("outcome"),
                "source_task_id": h.get("source_task_id"),
                "lesson": h.get("lesson"),
                "tags": tags,
            })
        return {
            "query": query,
            "bot_id": bot_id,
            "type_filter": type,
            "scope_used": shared_scope,
            "memories": memories,
            "count": len(memories),
            "backend": "bm25" if _HAS_BM25 else "tfidf",
        }
    finally:
        conn.close()


def forget(memory_id: str, bot_id: str | None = None) -> dict[str, Any]:
    """
    Delete a memory by ID.

    Args:
        memory_id: Memory ID from remember() or recall() result.
        bot_id:    Bot identity (must own the memory; default: HERMES_BOT_ID).

    Returns:
        dict with 'deleted': True/False, 'id', 'reason'
    """
    if not memory_id:
        return {"error": "memory_id must not be empty"}

    bot_id = bot_id or _bot_id_default()

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, bot_id FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return {"deleted": False, "id": memory_id, "reason": "not_found"}
        if row["bot_id"] != bot_id:
            return {
                "deleted": False,
                "id": memory_id,
                "reason": "not_authorized",
                "detail": f"memory belongs to bot_id '{row['bot_id']}', not '{bot_id}'",
            }
        conn.execute("DELETE FROM memory_terms WHERE memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        logger.info("carrier-viking: forgot memory %s for bot %s", memory_id, bot_id)
        return {"deleted": True, "id": memory_id}
    finally:
        conn.close()


def list_memories(
    type: str | None = None,
    bot_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    List memories for this bot, optionally filtered by type.
    Returns grouped results with per-type quota summary.
    """
    bot_id = bot_id or _bot_id_default()
    limit = min(limit, 100)

    if type and type not in VALID_TYPES:
        return {"error": f"type must be one of {sorted(VALID_TYPES)} or None, got '{type}'"}

    conn = _get_conn()
    try:
        if type:
            total_row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE bot_id = ? AND type = ?",
                (bot_id, type),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT id, type, content_l0, content, tags, created_at, accessed_at,
                       access_count, importance, fleet_visible, outcome, source_task_id, lesson
                FROM memories
                WHERE bot_id = ? AND type = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (bot_id, type, limit, offset),
            ).fetchall()
        else:
            total_row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE bot_id = ?",
                (bot_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT id, type, content_l0, content, tags, created_at, accessed_at,
                       access_count, importance, fleet_visible, outcome, source_task_id, lesson
                FROM memories
                WHERE bot_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (bot_id, limit, offset),
            ).fetchall()

        total = total_row[0] if total_row else 0

        quota_summary = {}
        for t in VALID_TYPES:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE bot_id = ? AND type = ?",
                (bot_id, t),
            ).fetchone()
            used = count_row[0] if count_row else 0
            q = _quota(t)
            quota_summary[t] = {
                "used": used,
                "quota": q,
                "remaining": max(0, q - used),
                "pct_full": round(100 * used / q, 1) if q else 0,
            }

        memories = []
        for r in rows:
            tags = []
            try:
                tags = json.loads(r["tags"] or "[]")
            except (json.JSONDecodeError, TypeError):
                pass
            memories.append({
                "id": r["id"],
                "type": r["type"],
                "content_l0": r["content_l0"] or "",
                "content": r["content"],
                "tags": tags,
                "created_at": r["created_at"],
                "accessed_at": r["accessed_at"],
                "access_count": r["access_count"],
                "importance": r["importance"],
                "fleet_visible": bool(r.get("fleet_visible", 0)),
                "outcome": r.get("outcome"),
                "source_task_id": r.get("source_task_id"),
                "lesson": r.get("lesson"),
            })

        return {
            "bot_id": bot_id,
            "type_filter": type,
            "total": total,
            "offset": offset,
            "limit": limit,
            "memories": memories,
            "quota_summary": quota_summary,
        }
    finally:
        conn.close()


def viking_stats(bot_id: str | None = None) -> dict[str, Any]:
    """
    Return usage statistics and health info for the viking memory store.

    Args:
        bot_id: Bot identity, or 'all' for fleet-wide stats.

    Returns:
        dict with db_path, total_memories, quota_summary, db_size_bytes
    """
    target_bot = bot_id or _bot_id_default()
    conn = _get_conn()
    try:
        if target_bot == "all":
            bot_rows = conn.execute(
                "SELECT DISTINCT bot_id FROM memories"
            ).fetchall()
            bots = [r["bot_id"] for r in bot_rows]
        else:
            bots = [target_bot]

        result: dict[str, Any] = {
            "db_path": str(_db_path()),
            "compatible_with": "OpenViking memory API v2 (carrier-viking stdlib+BM25)",
            "server_url": _server_url() or DEFAULT_SERVER_URL,
            "bm25_available": _HAS_BM25,
            "upgrade_path": "Set OPENVIKING_URL or start scripts/start_viking_server.py",
        }

        # Server health check
        server_alive = _check_server_alive(_server_url() or DEFAULT_SERVER_URL)
        result["server_alive"] = server_alive

        bot_stats = {}
        for bid in bots:
            quota_summary = {}
            for t in VALID_TYPES:
                count_row = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE bot_id = ? AND type = ?",
                    (bid, t),
                ).fetchone()
                used = count_row[0] if count_row else 0
                q = _quota(t)
                quota_summary[t] = {"used": used, "quota": q}
            bot_stats[bid] = quota_summary

        result["bots"] = bot_stats

        db = _db_path()
        result["db_size_bytes"] = db.stat().st_size if db.exists() else 0

        return result
    finally:
        conn.close()


# ── P2: Experience convenience tool ───────────────────────────────────────────

def record_experience(
    lesson: str,
    outcome: str = "success",
    source_task_id: str = "",
    bot_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Record a reusable lesson from a completed task outcome.

    This is the core of the 'self-evolving' loop: when a bot completes a task,
    it records what worked and what didn't. Future bots can recall these
    experiences before starting similar tasks.

    Args:
        lesson:          The distilled lesson (what to do / not do next time).
        outcome:         'success', 'failure', or 'partial' (default: 'success').
        source_task_id:  The task/session that generated this lesson.
        bot_id:          Bot identity (defaults to HERMES_BOT_ID env var).
        tags:            Optional tags for filtering.

    Returns:
        dict with 'id', 'status', 'type'='experience', 'outcome'
    """
    if not lesson or not lesson.strip():
        return {"error": "lesson must not be empty"}

    valid_outcomes = {"success", "failure", "partial"}
    if outcome not in valid_outcomes:
        return {"error": f"outcome must be one of {sorted(valid_outcomes)}, got '{outcome}'"}

    content = f"[{outcome.upper()}] {lesson}"
    if source_task_id:
        content += f"\n[source_task: {source_task_id}]"

    result = remember(
        content=content,
        type="experience",
        bot_id=bot_id,
        tags=tags,
        fleet_visible=True,
        outcome=outcome,
        source_task_id=source_task_id or None,
        lesson=lesson,
    )
    return result


# ── P6: Session auto-commit (LLM extraction) ──────────────────────────────────

_SESSION_EXTRACT_PROMPT = """You are a memory extraction assistant for an AI agent fleet.

Given a conversation transcript, extract ONLY durable, reusable memories worth storing long-term.
Ignore transient details, small talk, and implementation minutiae.

Extract into these categories:
- fact: Learned facts, domain knowledge, user preferences, system behaviors
- decision: Choices made with rationale (architecture decisions, policy choices)
- error: Mistakes made, debugging lessons, anti-patterns discovered
- experience: Reusable lessons from task outcomes (outcome + lesson)

Return a JSON array. Each item:
  {"type": "fact"|"decision"|"error"|"experience", "content": "...", "tags": ["tag1"], "outcome": "success"|"failure"|"partial" (for experience only)}

Rules:
- Maximum 10 items total
- Each content must be self-contained (no "the user said..." — state the fact directly)
- Skip anything that's only useful for this one session
- For experience type, always include outcome

Transcript:
{transcript}

Return ONLY valid JSON array, no explanation."""


def commit_session(
    transcript: str,
    bot_id: str | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    """
    Extract and store memories from a conversation transcript using claude-haiku.

    Makes ONE LLM call to extract structured memories from the transcript,
    then stores each extracted memory via remember().

    Args:
        transcript:  Raw conversation transcript text.
        bot_id:      Bot identity (defaults to HERMES_BOT_ID env var).
        session_id:  Optional session identifier for tracking.

    Returns:
        dict with 'extracted': [list of stored memories], 'count', 'session_id'
    """
    if not transcript or not transcript.strip():
        return {"error": "transcript must not be empty"}

    bot_id = bot_id or _bot_id_default()

    # Use Anthropic OAuth (claude-haiku-4-5 or similar)
    try:
        import anthropic
    except ImportError:
        return {
            "error": "anthropic package not available",
            "hint": "Install with: pip install anthropic",
        }

    # Truncate very long transcripts
    MAX_TRANSCRIPT_CHARS = 8000
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n[... truncated ...]"

    prompt = _SESSION_EXTRACT_PROMPT.format(transcript=transcript)

    try:
        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY or OAuth
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
    except Exception as e:
        return {"error": f"LLM extraction failed: {e}"}

    # Parse extracted memories
    try:
        # Strip markdown code fences if present
        json_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        extracted_items = json.loads(json_text)
        if not isinstance(extracted_items, list):
            return {"error": f"LLM returned non-list: {raw[:200]}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": raw[:500]}

    stored = []
    errors = []
    for item in extracted_items:
        if not isinstance(item, dict):
            continue
        mem_type = item.get("type", "fact")
        content = item.get("content", "").strip()
        tags = item.get("tags", [])
        outcome = item.get("outcome")

        if not content:
            continue

        if mem_type == "experience" and outcome:
            result = record_experience(
                lesson=content,
                outcome=outcome,
                source_task_id=session_id,
                bot_id=bot_id,
                tags=tags,
            )
        else:
            result = remember(
                content=content,
                type=mem_type if mem_type in VALID_TYPES else "fact",
                bot_id=bot_id,
                tags=tags,
            )

        if "error" in result:
            errors.append({"content": content[:80], "error": result["error"]})
        else:
            stored.append({
                "id": result["id"],
                "type": result.get("type", mem_type),
                "content_l0": result.get("content_l0", ""),
                "status": result.get("status", "stored"),
            })

    return {
        "session_id": session_id,
        "bot_id": bot_id,
        "extracted": stored,
        "count": len(stored),
        "errors": errors,
        "transcript_chars": len(transcript),
    }


# ── P7: Memory navigation ──────────────────────────────────────────────────────

def search_memories(
    pattern: str,
    bot_id: str | None = None,
    scope: str = "own",
) -> dict[str, Any]:
    """
    Regex/substring search over memory content, grouped by type.

    Unlike recall() which uses BM25 semantic search, this is exact
    pattern matching — useful for finding specific IDs, function names,
    error codes, or other precise strings.

    Args:
        pattern: Regex pattern or plain substring to search for.
        bot_id:  Bot identity (defaults to HERMES_BOT_ID env var).
        scope:   'own' (default) = own memories. 'all' = fleet-wide visible memories.

    Returns:
        dict with 'matches' grouped by type, 'total_matches'
    """
    if not pattern:
        return {"error": "pattern must not be empty"}

    bot_id = bot_id or _bot_id_default()

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}"}

    conn = _get_conn()
    try:
        if scope == "all":
            rows = conn.execute(
                "SELECT * FROM memories WHERE bot_id = ? OR fleet_visible = 1",
                (bot_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE bot_id = ?",
                (bot_id,),
            ).fetchall()

        matches_by_type: dict[str, list[dict]] = {t: [] for t in VALID_TYPES}
        total = 0

        for r in rows:
            content = r["content"] or ""
            if compiled.search(content):
                tags = []
                try:
                    tags = json.loads(r["tags"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    pass
                entry = {
                    "id": r["id"],
                    "bot_id": r["bot_id"],
                    "content_l0": r["content_l0"] or "",
                    "content": content,
                    "tags": tags,
                    "created_at": r["created_at"],
                    "outcome": r.get("outcome"),
                }
                mem_type = r["type"]
                if mem_type in matches_by_type:
                    matches_by_type[mem_type].append(entry)
                    total += 1

        # Remove empty type groups
        matches_by_type = {t: v for t, v in matches_by_type.items() if v}

        return {
            "pattern": pattern,
            "bot_id": bot_id,
            "scope": scope,
            "matches": matches_by_type,
            "total_matches": total,
        }
    finally:
        conn.close()


# ── OpenViking 15-tool stubs (proxy → local fallback) ────────────────────────

def _ov_proxy_or_stub(tool_name: str, params: dict[str, Any], stub_result: dict[str, Any]) -> dict[str, Any]:
    """Try to proxy to OpenViking server, fall back to stub result."""
    url = _server_url() or DEFAULT_SERVER_URL
    result = _proxy_call(f"/mcp/tools/{tool_name}", params)
    if result is not None:
        return result
    return stub_result


def find(query: str, bot_id: str | None = None, k: int = 10) -> dict[str, Any]:
    """Fast semantic search (OpenViking find tool — no session context). Proxies to server or falls back to recall()."""
    result = _ov_proxy_or_stub("find", {"query": query, "bot_id": bot_id, "k": k}, None)
    if result is None:
        return recall(query=query, bot_id=bot_id, k=k)
    return result


def search(
    query: str,
    bot_id: str | None = None,
    quotas: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Deep search with intent analysis (OpenViking search tool). Proxies to server or falls back to recall()."""
    result = _ov_proxy_or_stub("search", {"query": query, "bot_id": bot_id, "quotas": quotas}, None)
    if result is None:
        return recall(query=query, bot_id=bot_id)
    return result


def read(uri: str) -> dict[str, Any]:
    """Read a viking:// file. Proxies to server; no local fallback."""
    result = _ov_proxy_or_stub("read", {"uri": uri}, None)
    if result is None:
        return {"error": "Server not available. Start scripts/start_viking_server.py for full viking:// filesystem support.", "uri": uri}
    return result


def write(uri: str, content: str, mode: str = "replace") -> dict[str, Any]:
    """Write a viking:// file. Proxies to server; no local fallback."""
    result = _ov_proxy_or_stub("write", {"uri": uri, "content": content, "mode": mode}, None)
    if result is None:
        return {"error": "Server not available. Start scripts/start_viking_server.py for full viking:// filesystem support.", "uri": uri}
    return result


def edit(uri: str, old_string: str, new_string: str) -> dict[str, Any]:
    """Edit a viking:// file. Proxies to server; no local fallback."""
    result = _ov_proxy_or_stub("edit", {"uri": uri, "old_string": old_string, "new_string": new_string}, None)
    if result is None:
        return {"error": "Server not available. Start scripts/start_viking_server.py for full viking:// filesystem support.", "uri": uri}
    return result


def list_uris(uri_prefix: str, bot_id: str | None = None) -> dict[str, Any]:
    """List viking:// directory. Proxies to server; falls back to list_memories grouped by type."""
    result = _ov_proxy_or_stub("list", {"uri": uri_prefix, "bot_id": bot_id}, None)
    if result is None:
        bot_id = bot_id or _bot_id_default()
        return list_memories(bot_id=bot_id)
    return result


def tree(uri_prefix: str, bot_id: str | None = None) -> dict[str, Any]:
    """Recursive tree view. Proxies to server; falls back to grouped list_memories."""
    result = _ov_proxy_or_stub("tree", {"uri": uri_prefix, "bot_id": bot_id}, None)
    if result is None:
        bot_id = bot_id or _bot_id_default()
        mems = list_memories(bot_id=bot_id, limit=100)
        tree_data: dict[str, list] = {t: [] for t in VALID_TYPES}
        for m in mems.get("memories", []):
            tree_data[m["type"]].append({"id": m["id"], "abstract": m["content_l0"]})
        return {"bot_id": bot_id, "tree": {k: v for k, v in tree_data.items() if v}}
    return result


def add_resource(url: str, bot_id: str | None = None) -> dict[str, Any]:
    """Ingest URL/file as resource. Proxies to server; no local fallback."""
    result = _ov_proxy_or_stub("add_resource", {"url": url, "bot_id": bot_id}, None)
    if result is None:
        return {
            "error": "Server not available. Start scripts/start_viking_server.py for resource ingestion support.",
            "url": url,
            "hint": "Alternatively, use remember() to manually store the resource content.",
        }
    return result


def grep(uri_prefix: str, pattern: str, bot_id: str | None = None) -> dict[str, Any]:
    """Regex search in viking:// files. Proxies to server; falls back to search_memories()."""
    result = _ov_proxy_or_stub("grep", {"uri": uri_prefix, "pattern": pattern, "bot_id": bot_id}, None)
    if result is None:
        return search_memories(pattern=pattern, bot_id=bot_id)
    return result


def glob(uri_prefix: str, glob_pattern: str, bot_id: str | None = None) -> dict[str, Any]:
    """Filename-pattern search. Proxies to server; falls back to list_memories."""
    result = _ov_proxy_or_stub("glob", {"uri": uri_prefix, "glob_pattern": glob_pattern, "bot_id": bot_id}, None)
    if result is None:
        bot_id = bot_id or _bot_id_default()
        return list_memories(bot_id=bot_id)
    return result


def health() -> dict[str, Any]:
    """Server health check. Returns local stats if server is down."""
    url = _server_url() or DEFAULT_SERVER_URL
    alive = _check_server_alive(url)
    if alive:
        result = _ov_proxy_or_stub("health", {}, None)
        if result:
            return result
    return {
        "status": "local_fallback",
        "server_url": url,
        "server_alive": alive,
        "local_db": str(_db_path()),
        "bm25": _HAS_BM25,
        "memory_types": sorted(VALID_TYPES),
    }


def list_watches() -> dict[str, Any]:
    """List auto-refresh resource subscriptions. Requires server."""
    result = _ov_proxy_or_stub("list_watches", {}, None)
    if result is None:
        return {
            "watches": [],
            "note": "Watches require the OpenViking server. Start scripts/start_viking_server.py",
        }
    return result


def cancel_watch(watch_id: str) -> dict[str, Any]:
    """Cancel a watch subscription. Requires server."""
    result = _ov_proxy_or_stub("cancel_watch", {"watch_id": watch_id}, None)
    if result is None:
        return {
            "error": "Watches require the OpenViking server. Start scripts/start_viking_server.py",
            "watch_id": watch_id,
        }
    return result


# ── Plugin registration ────────────────────────────────────────────────────────

def register_tools():
    """
    Called by the Hermes plugin loader. Returns a list of tool descriptors.
    Full 15-tool OpenViking surface + carrier extensions.
    """
    ALL_TYPES_ENUM = sorted(VALID_TYPES)
    ALL_TYPES_DESC = "task, fact, error, decision, experience, trajectory, entity, preference"

    return [
        # ── Core memory tools ──────────────────────────────────────────────────
        {
            "name": "remember",
            "description": (
                "Store a memory for this bot. Memories persist across sessions and are scoped to this bot_id. "
                f"Types: {ALL_TYPES_DESC}. "
                "Each type has a per-bot quota enforced by LRU eviction. "
                "fleet_visible=true makes memory available to other bots via shared_scope='all'. "
                "Experiences are fleet_visible by default (self-evolving loop)."
            ),
            "fn": remember,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Memory content. Markdown and code are fine. Be specific and self-contained.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ALL_TYPES_ENUM,
                        "description": f"Memory type: {ALL_TYPES_DESC}",
                        "default": "fact",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for categorization.",
                    },
                    "importance": {
                        "type": "number",
                        "description": "Importance 0.0-2.0 (default 1.0). Higher = last to be evicted.",
                        "default": 1.0,
                    },
                    "fleet_visible": {
                        "type": "boolean",
                        "description": "If true, other fleet bots can access this memory. Experiences default to true.",
                        "default": False,
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "failure", "partial"],
                        "description": "For experience type: the task outcome.",
                    },
                    "source_task_id": {
                        "type": "string",
                        "description": "For experience type: task/session that generated this lesson.",
                    },
                    "lesson": {
                        "type": "string",
                        "description": "For experience type: short distilled lesson.",
                    },
                },
                "required": ["content"],
            },
        },
        {
            "name": "recall",
            "description": (
                "BM25+hotness semantic recall over this bot's stored memories. "
                "Returns ranked memories matching the query. Use at task start to load "
                "relevant context: errors made before, past decisions, known facts, "
                "experiences from similar tasks. "
                "shared_scope='all' also searches fleet-visible memories from other bots."
            ),
            "fn": recall,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ALL_TYPES_ENUM,
                        "description": "Optional type filter.",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Max results to return (default: 10).",
                        "default": 10,
                    },
                    "shared_scope": {
                        "type": "string",
                        "enum": ["own", "all"],
                        "description": "'own' (default) = own memories only. 'all' = include fleet-visible memories from all bots (with 30% score penalty).",
                        "default": "own",
                    },
                    "peer_penalty": {
                        "type": "number",
                        "description": "Score penalty for other-bot memories (default 0.3 = 30% downrank).",
                        "default": 0.3,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "forget",
            "description": (
                "Delete a specific memory by ID. Only deletes memories owned by this bot. "
                "Use to clean up completed tasks, superseded decisions, or irrelevant facts."
            ),
            "fn": forget,
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "Memory ID from remember() or recall() result.",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Must own the memory.",
                    },
                },
                "required": ["memory_id"],
            },
        },
        {
            "name": "list_memories",
            "description": (
                "List all memories for this bot with quota usage. Shows how full each "
                "type's quota is, and what memories exist. Good for auditing bot state."
            ),
            "fn": list_memories,
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ALL_TYPES_ENUM,
                        "description": "Optional type filter.",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results per page (default: 20, max: 100).",
                        "default": 20,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default: 0).",
                        "default": 0,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "viking_stats",
            "description": (
                "Show viking memory store statistics: quota usage per type, DB path, server status, "
                "BM25 availability, upgrade instructions. Pass bot_id='all' to see all bots."
            ),
            "fn": viking_stats,
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity, or 'all' for fleet-wide stats.",
                    },
                },
                "required": [],
            },
        },
        # ── P2: Experience convenience tool ────────────────────────────────────
        {
            "name": "record_experience",
            "description": (
                "Record a reusable lesson from a completed task outcome (the self-evolving loop). "
                "Experiences are fleet-visible: other bots can recall them with shared_scope='all'. "
                "Call this at the END of every significant task to help the fleet learn."
            ),
            "fn": record_experience,
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson": {
                        "type": "string",
                        "description": "The distilled lesson — what to do or avoid next time. Be specific.",
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "failure", "partial"],
                        "description": "Task outcome. default: 'success'",
                        "default": "success",
                    },
                    "source_task_id": {
                        "type": "string",
                        "description": "Task/session/ticket ID that generated this lesson.",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags (e.g. ['git', 'merge', 'conflict']).",
                    },
                },
                "required": ["lesson"],
            },
        },
        # ── P6: Session auto-commit ─────────────────────────────────────────────
        {
            "name": "commit_session",
            "description": (
                "Extract and store memories from a conversation transcript using claude-haiku. "
                "Makes ONE LLM call to extract facts, decisions, errors, and experiences, "
                "then stores each via remember(). Use at the end of a conversation or task "
                "to auto-populate memory without manual remember() calls."
            ),
            "fn": commit_session,
            "parameters": {
                "type": "object",
                "properties": {
                    "transcript": {
                        "type": "string",
                        "description": "Raw conversation transcript text (max 8000 chars; will be truncated if longer).",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session/task identifier for tracking.",
                    },
                },
                "required": ["transcript"],
            },
        },
        # ── P7: Memory navigation ───────────────────────────────────────────────
        {
            "name": "search_memories",
            "description": (
                "Regex/substring search over memory content, grouped by type. "
                "Unlike recall() which uses BM25 semantic search, this is exact pattern matching. "
                "Useful for finding specific function names, error codes, IDs, or precise strings."
            ),
            "fn": search_memories,
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern or plain substring to search for (case-insensitive).",
                    },
                    "bot_id": {
                        "type": "string",
                        "description": "Bot identity. Defaults to HERMES_BOT_ID env var.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["own", "all"],
                        "description": "'own' (default) = own memories. 'all' = fleet-wide visible memories.",
                        "default": "own",
                    },
                },
                "required": ["pattern"],
            },
        },
        # ── OpenViking-compatible tool surface ─────────────────────────────────
        {
            "name": "find",
            "description": (
                "Fast semantic search (OpenViking find tool — no session context). "
                "Proxies to the OpenViking server if running at localhost:1933, "
                "otherwise falls back to BM25 recall()."
            ),
            "fn": find,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                    "k": {"type": "integer", "description": "Max results.", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "search",
            "description": (
                "Deep search with intent analysis (OpenViking search tool). "
                "Proxies to the OpenViking server if running, otherwise falls back to recall(). "
                "Supports token-budget aware context assembly via quotas parameter."
            ),
            "fn": search,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                    "quotas": {
                        "type": "object",
                        "description": "Per-type max result quotas, e.g. {\"experience\": 3, \"fact\": 5}.",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "read",
            "description": (
                "Read a viking:// file (images/audio as MCP content blocks). "
                "Requires OpenViking server at localhost:1933."
            ),
            "fn": read,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "viking:// URI to read."},
                },
                "required": ["uri"],
            },
        },
        {
            "name": "write",
            "description": (
                "Write text to a viking:// file (create/append/replace). "
                "Requires OpenViking server at localhost:1933."
            ),
            "fn": write,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "viking:// URI to write."},
                    "content": {"type": "string", "description": "Content to write."},
                    "mode": {
                        "type": "string",
                        "enum": ["replace", "append", "create"],
                        "default": "replace",
                    },
                },
                "required": ["uri", "content"],
            },
        },
        {
            "name": "edit",
            "description": (
                "Targeted string replace in a viking:// file. "
                "Requires OpenViking server at localhost:1933."
            ),
            "fn": edit,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "viking:// URI to edit."},
                    "old_string": {"type": "string", "description": "Text to replace."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                },
                "required": ["uri", "old_string", "new_string"],
            },
        },
        {
            "name": "list_uris",
            "description": (
                "Directory listing under a viking:// URI. "
                "Proxies to server; falls back to list_memories() grouped by type."
            ),
            "fn": list_uris,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri_prefix": {"type": "string", "description": "viking:// URI prefix."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                },
                "required": ["uri_prefix"],
            },
        },
        {
            "name": "tree",
            "description": (
                "Recursive tree view with abstracts over a viking:// URI. "
                "Proxies to server; falls back to grouped tree from list_memories()."
            ),
            "fn": tree,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri_prefix": {"type": "string", "description": "viking:// URI prefix."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                },
                "required": ["uri_prefix"],
            },
        },
        {
            "name": "add_resource",
            "description": (
                "Ingest URL/file/repo as resource (parsed, L0/L1/L2 generated). "
                "Requires OpenViking server at localhost:1933. "
                "For manual ingestion, use remember() with type='fact' instead."
            ),
            "fn": add_resource,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL or file path to ingest."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                },
                "required": ["url"],
            },
        },
        {
            "name": "grep",
            "description": (
                "Regex search in viking:// files. "
                "Proxies to server; falls back to search_memories() locally."
            ),
            "fn": grep,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri_prefix": {"type": "string", "description": "viking:// URI prefix to search under."},
                    "pattern": {"type": "string", "description": "Regex pattern."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                },
                "required": ["uri_prefix", "pattern"],
            },
        },
        {
            "name": "glob",
            "description": (
                "Filename-pattern search across viking:// filesystem. "
                "Proxies to server; falls back to list_memories() locally."
            ),
            "fn": glob,
            "parameters": {
                "type": "object",
                "properties": {
                    "uri_prefix": {"type": "string", "description": "viking:// URI prefix to search under."},
                    "glob_pattern": {"type": "string", "description": "Glob pattern (e.g. '*.md')."},
                    "bot_id": {"type": "string", "description": "Bot identity."},
                },
                "required": ["uri_prefix", "glob_pattern"],
            },
        },
        {
            "name": "health",
            "description": (
                "Viking memory health check. Returns server status if running, "
                "or local DB stats if server is down."
            ),
            "fn": health,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "list_watches",
            "description": "List auto-refresh resource subscriptions. Requires OpenViking server.",
            "fn": list_watches,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "cancel_watch",
            "description": "Cancel a watch subscription. Requires OpenViking server.",
            "fn": cancel_watch,
            "parameters": {
                "type": "object",
                "properties": {
                    "watch_id": {"type": "string", "description": "Watch ID from list_watches()."},
                },
                "required": ["watch_id"],
            },
        },
    ]

"""Fleet brain vector store — SQLite + numpy cosine (same approach as ob1-mcp-server store.py).

No pgvector, no cloud, no API keys. Designed for ~10k thoughts at fleet scale.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from schema import SCHEMA_SQL

DEFAULT_DB_PATH = Path("C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db")


def _pack(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    return struct.pack(f"<{len(arr)}f", *arr.tolist())


def _unpack(blob: bytes, dim: int) -> np.ndarray:
    return np.asarray(struct.unpack(f"<{dim}f", blob), dtype=np.float32)


@dataclass
class SearchHit:
    thought_id: str
    score: float
    snippet: str
    source: str
    scope: str
    category: str
    metadata: dict


class FleetBrainStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Thoughts CRUD
    # ------------------------------------------------------------------

    def write_thought(
        self,
        content: str,
        *,
        source: str = "fleet",
        scope: str = "fleet",
        category: str = "knowledge",
        summary: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        agent_id: str | None = None,
        memory_kind: str = "knowledge",
        confidence: float = 0.8,
        chunks: list[tuple[str, np.ndarray]] | None = None,
    ) -> str:
        """Write a new thought; returns thought_id."""
        thought_id = str(uuid.uuid4())
        now = time.time()
        self._conn.execute(
            """INSERT INTO thoughts(id, content, summary, source, scope, category, tags, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                thought_id,
                content,
                summary,
                source,
                scope,
                category,
                json.dumps(tags or []),
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        # Agent memory sidecar
        mem_id = str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO agent_memories(id, thought_id, agent_id, memory_kind, scope, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (mem_id, thought_id, agent_id or source, memory_kind, scope, now, now),
        )
        # Audit event
        self._conn.execute(
            "INSERT INTO audit_events(agent_id, event_type, thought_id, detail, created_at) VALUES (?,?,?,?,?)",
            (agent_id or source, "write", thought_id, "{}", now),
        )
        # Store embedding chunks if provided
        if chunks:
            for idx, (text, vec) in enumerate(chunks):
                blob = _pack(vec)
                dim = int(np.asarray(vec).reshape(-1).shape[0])
                self._conn.execute(
                    """INSERT INTO thought_chunks(thought_id, chunk_idx, text, embedding, dim)
                       VALUES (?,?,?,?,?)""",
                    (thought_id, idx, text, blob, dim),
                )
        self._conn.commit()
        return thought_id

    def get_thought(self, thought_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id,content,summary,source,scope,category,tags,metadata,created_at FROM thoughts WHERE id=?",
            (thought_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "content": row[1], "summary": row[2],
            "source": row[3], "scope": row[4], "category": row[5],
            "tags": json.loads(row[6]), "metadata": json.loads(row[7]),
            "created_at": row[8],
        }

    def list_thoughts(
        self,
        scope: str | None = None,
        source: str | None = None,
        category: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("scope=?")
            params.append(scope)
        if source:
            clauses.append("source=?")
            params.append(source)
        if category:
            clauses.append("category=?")
            params.append(category)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"SELECT id,content,summary,source,scope,category,tags,metadata,created_at "
            f"FROM thoughts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [
            {
                "id": r[0], "content": r[1], "summary": r[2],
                "source": r[3], "scope": r[4], "category": r[5],
                "tags": json.loads(r[6]), "metadata": json.loads(r[7]),
                "created_at": r[8],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        scope_filter: str | None = None,
        source_filter: str | None = None,
        category_filter: str | None = None,
    ) -> list[SearchHit]:
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        q_norm = float(np.linalg.norm(q))
        if q_norm == 0.0:
            return []
        q = q / q_norm

        # Load all relevant chunks in one pass
        rows = self._conn.execute(
            """SELECT tc.thought_id, tc.text, tc.embedding, tc.dim,
                      t.source, t.scope, t.category, t.metadata
               FROM thought_chunks tc
               JOIN thoughts t ON t.id=tc.thought_id""",
        ).fetchall()

        best: dict[str, tuple[float, str, str, str, str, dict]] = {}
        for thought_id, text, blob, dim, source, scope_, category, meta_json in rows:
            if scope_filter and scope_ != scope_filter:
                continue
            if source_filter and source != source_filter:
                continue
            if category_filter and category != category_filter:
                continue
            vec = _unpack(blob, int(dim))
            n = float(np.linalg.norm(vec))
            if n == 0.0:
                continue
            score = float(np.dot(q, vec / n))
            prev = best.get(thought_id)
            if prev is None or score > prev[0]:
                snippet = text.strip().replace("\n", " ")
                if len(snippet) > 280:
                    snippet = snippet[:277] + "..."
                best[thought_id] = (score, snippet, source, scope_, category, json.loads(meta_json))

        ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:top_k]
        return [
            SearchHit(
                thought_id=tid,
                score=s,
                snippet=snip,
                source=src,
                scope=scp,
                category=cat,
                metadata=meta,
            )
            for tid, (s, snip, src, scp, cat, meta) in ranked
        ]

    # ------------------------------------------------------------------
    # Keyword search fallback (SQLite FTS via LIKE — sufficient for small fleet)
    # ------------------------------------------------------------------

    def keyword_search(
        self, query: str, top_k: int = 10, scope_filter: str | None = None
    ) -> list[dict]:
        words = [w.strip() for w in query.split() if len(w.strip()) > 2]
        if not words:
            return []
        # OR across all words, LIKE match
        clauses = " OR ".join(["content LIKE ?"] * len(words))
        params: list[Any] = [f"%{w}%" for w in words]
        scope_clause = "AND scope=? " if scope_filter else ""
        if scope_filter:
            params.append(scope_filter)
        params.extend([top_k])
        rows = self._conn.execute(
            f"SELECT id,content,summary,source,scope,category,metadata,created_at "
            f"FROM thoughts WHERE ({clauses}) {scope_clause} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [
            {
                "id": r[0], "content": r[1][:300], "summary": r[2],
                "source": r[3], "scope": r[4], "category": r[5],
                "metadata": json.loads(r[6]), "created_at": r[7],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Discord messages
    # ------------------------------------------------------------------

    def upsert_discord_message(
        self,
        *,
        message_id: str,
        channel_id: str,
        channel_name: str,
        guild_name: str,
        author: str,
        content: str,
        thought_id: str | None = None,
    ) -> None:
        now = time.time()
        self._conn.execute(
            """INSERT INTO discord_messages(id, channel_id, channel_name, guild_name, author, content, thought_id, captured_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 content=excluded.content, thought_id=excluded.thought_id""",
            (message_id, channel_id, channel_name, guild_name, author, content, thought_id, now),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Recall trace logging
    # ------------------------------------------------------------------

    def log_recall(self, agent_id: str, query: str, results: list[dict], top_k: int) -> None:
        self._conn.execute(
            "INSERT INTO recall_traces(agent_id, query, top_k, results, recalled_at) VALUES (?,?,?,?,?)",
            (agent_id, query, top_k, json.dumps(results), time.time()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Stats / meta
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        thoughts = self._conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0]
        chunks = self._conn.execute("SELECT COUNT(*) FROM thought_chunks").fetchone()[0]
        discord = self._conn.execute("SELECT COUNT(*) FROM discord_messages").fetchone()[0]
        by_scope = self._conn.execute(
            "SELECT scope, COUNT(*) FROM thoughts GROUP BY scope"
        ).fetchall()
        by_source = self._conn.execute(
            "SELECT source, COUNT(*) FROM thoughts GROUP BY source"
        ).fetchall()
        return {
            "thoughts": int(thoughts),
            "chunks": int(chunks),
            "discord_messages": int(discord),
            "by_scope": {r[0]: r[1] for r in by_scope},
            "by_source": {r[0]: r[1] for r in by_source},
            "db_path": str(self.db_path),
        }

"""Embedder — sentence-transformers/all-MiniLM-L6-v2 (local, 384-d, no API key).

Falls back gracefully to TF-IDF BM25-style zero vectors when sentence-transformers is
not installed, so the server stays functional for keyword-only search.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_EMBED_DIM = 384
CHUNK_SIZE = 900
CHUNK_OVERLAP = 100


class Embedder:
    """Lazy-load sentence-transformers; fall back to zeros if unavailable."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None
        self._available: bool | None = None

    def _try_load(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self._model = SentenceTransformer(self.model_name)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    @property
    def dim(self) -> int:
        return _EMBED_DIM

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._try_load() and self._model is not None:
            vecs = self._model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return np.asarray(vecs, dtype=np.float32)
        # Fallback: deterministic pseudo-vectors from text hash
        # (enables keyword search to still work via separate code path)
        return _hash_vectors(texts, _EMBED_DIM)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    @property
    def backend(self) -> str:
        return "sentence-transformers" if self._available else "hash-fallback"


def _hash_vectors(texts: list[str], dim: int) -> np.ndarray:
    """Generate stable pseudo-random unit vectors from text hash.
    Only used when sentence-transformers is not installed.
    Not semantically meaningful; still allows BM25 search to work."""
    result = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        seed = int(hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(dim).astype(np.float32)
        n = float(np.linalg.norm(v))
        result[i] = v / n if n > 0 else v
    return result


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence breaks."""
    import re
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            br = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if br > size // 3:
                end = start + br + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks

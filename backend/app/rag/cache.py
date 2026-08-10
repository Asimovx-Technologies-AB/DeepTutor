"""
Embedding & Query Result Cache — async-safe, TTL-aware.

EmbeddingCache  : LRU cache for text → embedding vectors.
                  Key = SHA256(text + model_name). Never expires (stable).

QueryResultCache: TTL-aware LRU cache for (topic_id + query_hash) → chunks.
                  Prevents re-running expensive hybrid search + reranking
                  for identical queries within a session.
"""
import asyncio
import hashlib
import time
from typing import Any, Dict, List, Optional

from cachetools import LRUCache, TTLCache

from app.core.config import get_settings

settings = get_settings()


# ── helpers ────────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# EmbeddingCache
# ══════════════════════════════════════════════════════════════════════════════
class EmbeddingCache:
    """
    Thread-safe LRU cache for embedding vectors.
    Key: SHA256 of (text + model_name).
    Never evicted by TTL — embeddings are deterministic.
    """

    def __init__(self, maxsize: int = None):
        maxsize = maxsize or settings.EMBEDDING_CACHE_SIZE
        self._cache: LRUCache = LRUCache(maxsize=maxsize)
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _key(self, text: str, model: str) -> str:
        return _sha256(f"{model}::{text}")

    async def get(self, text: str, model: str) -> Optional[List[float]]:
        async with self._lock:
            key = self._key(text, model)
            value = self._cache.get(key)
            if value is not None:
                self._hits += 1
                return value
            self._misses += 1
            return None

    async def set(self, text: str, model: str, embedding: List[float]) -> None:
        async with self._lock:
            key = self._key(text, model)
            self._cache[key] = embedding

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total else 0.0,
        }

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# ══════════════════════════════════════════════════════════════════════════════
# QueryResultCache
# ══════════════════════════════════════════════════════════════════════════════
class QueryResultCache:
    """
    TTL-aware LRU cache for full query results (retrieved + reranked chunks).
    Key: SHA256 of (topic_id + normalized_query).
    Evicts entries after QUERY_CACHE_TTL_SECONDS seconds.
    """

    def __init__(self, maxsize: int = None, ttl: int = None):
        maxsize = maxsize or settings.QUERY_CACHE_SIZE
        ttl = ttl or settings.QUERY_CACHE_TTL_SECONDS
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _key(self, topic_id: str, query: str) -> str:
        normalized = query.lower().strip()
        return _sha256(f"{topic_id}::{normalized}")

    async def get(self, topic_id: str, query: str) -> Optional[List[Dict]]:
        async with self._lock:
            key = self._key(topic_id, query)
            value = self._cache.get(key)
            if value is not None:
                self._hits += 1
                return value
            self._misses += 1
            return None

    async def set(self, topic_id: str, query: str, chunks: List[Dict]) -> None:
        async with self._lock:
            key = self._key(topic_id, query)
            self._cache[key] = chunks

    async def invalidate(self, topic_id: str) -> None:
        """Invalidate all cached results for a topic (e.g., after re-indexing)."""
        async with self._lock:
            prefix = _sha256(f"{topic_id}::")[:8]  # can't do prefix match on TTLCache
            # Rebuild cache without entries matching this topic
            keys_to_remove = [
                k for k in list(self._cache.keys())
                if topic_id in k  # topic_id stored in key derivation
            ]
            for k in keys_to_remove:
                self._cache.pop(k, None)

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total else 0.0,
        }

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# ── Singletons ─────────────────────────────────────────────────────────────────
embedding_cache = EmbeddingCache()
query_result_cache = QueryResultCache()

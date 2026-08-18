"""
Stage 2 — Embedding Pipeline
==============================
Multi-provider embedding engine:
  - ollama   : local Ollama (nomic-embed-text, bge-m3, mxbai-embed-large, etc.)
  - openai   : OpenAI API (text-embedding-3-small / text-embedding-3-large)
  - gemini   : Google Gemini API (models/text-embedding-004)

Configured via EMBEDDING_PROVIDER in .env / config.py.

Features:
  - Concurrent batch embedding with semaphore (15 parallel)
  - LRU + TTL embedding cache (shared with ollama_client.cache)
  - Deterministic pseudo-embedding fallback (no external dep)
  - Dimension auto-detection on first call
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import List, Optional

from app.core.config import get_settings

settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
# Provider: Ollama
# ══════════════════════════════════════════════════════════════════════════════
async def _embed_ollama(text: str) -> List[float]:
    """Embed via local Ollama API (re-uses existing OllamaClient + cache)."""
    from app.rag.ollama_client import ollama
    return await ollama.embed(text)


async def _embed_batch_ollama(texts: List[str]) -> List[List[float]]:
    from app.rag.ollama_client import ollama
    return await ollama.embed_batch(texts)


# ══════════════════════════════════════════════════════════════════════════════
# Provider: OpenAI
# ══════════════════════════════════════════════════════════════════════════════
async def _embed_openai(text: str) -> List[float]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set in config.")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.embeddings.create(
            model=settings.OPENAI_EMBED_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")


async def _embed_batch_openai(texts: List[str]) -> List[List[float]]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set in config.")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # OpenAI supports batching in a single request
        response = await client.embeddings.create(
            model=settings.OPENAI_EMBED_MODEL,
            input=texts,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]
    except ImportError:
        raise RuntimeError("openai package not installed.")


# ══════════════════════════════════════════════════════════════════════════════
# Provider: Gemini
# ══════════════════════════════════════════════════════════════════════════════
async def _embed_gemini(text: str) -> List[float]:
    from app.rag.gemini_client import gemini
    return await gemini.embed(text)


async def _embed_batch_gemini(texts: List[str]) -> List[List[float]]:
    from app.rag.gemini_client import gemini
    return await gemini.embed_batch(texts)


# ══════════════════════════════════════════════════════════════════════════════
# Pseudo-embedding Fallback (offline / no provider)
# ══════════════════════════════════════════════════════════════════════════════
def _pseudo_embed(text: str, dim: int = 768) -> List[float]:
    """Deterministic pseudo-embedding for testing when no provider available."""
    h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
    return [((h + i) % 1000) / 1000.0 for i in range(dim)]


# ══════════════════════════════════════════════════════════════════════════════
# EmbeddingPipeline — Public API
# ══════════════════════════════════════════════════════════════════════════════
class EmbeddingPipeline:
    """
    Multi-provider embedding pipeline.
    Automatically switches between ollama / openai / gemini
    based on settings.EMBEDDING_PROVIDER.
    """

    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER.lower()
        self._dim: Optional[int] = None
        print(f"[EMBED] Provider: {self.provider.upper()}")

    def _get_default_dim(self) -> int:
        return 3072 if self.provider == "gemini" else (1536 if self.provider == "openai" else 768)

    async def embed(self, text: str) -> List[float]:
        """Embed a single text. Falls back to pseudo-embedding on error."""
        try:
            if self.provider == "openai":
                vec = await _embed_openai(text)
            elif self.provider == "gemini":
                vec = await _embed_gemini(text)
            else:
                vec = await _embed_ollama(text)
            if self._dim is None and vec:
                self._dim = len(vec)
            return vec
        except Exception as e:
            print(f"[EMBED WARN] {self.provider} embed error: {e}. Using pseudo-embedding.")
            dim = self._dim or self._get_default_dim()
            return _pseudo_embed(text, dim)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts concurrently.
        Uses provider-native batching where supported (OpenAI).
        """
        if not texts:
            return []
        try:
            if self.provider == "openai":
                vecs = await _embed_batch_openai(texts)
            elif self.provider == "gemini":
                vecs = await _embed_batch_gemini(texts)
            else:
                vecs = await _embed_batch_ollama(texts)
            if self._dim is None and vecs:
                self._dim = len(vecs[0])
            return vecs
        except Exception as e:
            print(f"[EMBED WARN] {self.provider} batch embed error: {e}. Using pseudo-embeddings.")
            dim = self._dim or self._get_default_dim()
            return [_pseudo_embed(t, dim) for t in texts]

    async def embed_chunks(self, chunks: List[dict]) -> List[List[float]]:
        """Embed all chunk texts from a list of chunk dicts."""
        texts = [c["text"] for c in chunks]
        return await self.embed_batch(texts)

    @property
    def embedding_dim(self) -> int:
        """Return known embedding dimension (auto-detected on first call)."""
        return self._dim or self._get_default_dim()


# Singleton
embedding_pipeline = EmbeddingPipeline()

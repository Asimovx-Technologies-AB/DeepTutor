"""
Stage 3 — FAISS HNSW Vector Store
====================================
Replaces ChromaDB as the primary vector store.

Features:
  - FAISS IndexHNSWFlat (cosine via inner product on L2-normalized vectors)
  - Persistent: saves/loads index + metadata JSON per topic to faiss_data/
  - Built-in BM25+ sparse index for hybrid search
  - Weighted RRF (Reciprocal Rank Fusion) for hybrid results
  - Same public interface as the legacy VectorStore (ChromaDB wrapper)
    → add_chunks(), search(), search_bm25(), search_hybrid()
    → count(), delete_topic(), reset()

FAISS Index type: HNSW
  - HNSW_M = 32         (graph connectivity — higher = more accurate, more RAM)
  - EF_CONSTRUCTION = 200 (build accuracy)
  - EF_SEARCH = 64      (query accuracy vs speed)
"""
from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.core.config import get_settings

settings = get_settings()

_FAISS_DATA = Path(settings.FAISS_DATA_DIR)


# ══════════════════════════════════════════════════════════════════════════════
# BM25+ index (per-topic, in-memory)
# ══════════════════════════════════════════════════════════════════════════════
def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) > 1]


class _BM25Index:
    """BM25+ index over all documents in a topic. K1=1.5, B=0.75, delta=1.0."""
    K1, B, DELTA = 1.5, 0.75, 1.0

    def __init__(self, ids: List[str], docs: List[str], metas: List[Dict]):
        self.ids = ids
        self.docs = docs
        self.metas = metas
        corpus = [_tokenize(d) for d in docs]
        self.n = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.n, 1)
        self.df: Dict[str, int] = {}
        for doc in corpus:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1
        self.tf_docs = []
        for doc in corpus:
            freq: Dict[str, int] = {}
            for t in doc:
                freq[t] = freq.get(t, 0) + 1
            self.tf_docs.append((freq, len(doc)))

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        q = _tokenize(query)
        scores = []
        for i, (freq, dl) in enumerate(self.tf_docs):
            score = 0.0
            for term in q:
                if term not in freq:
                    continue
                tf = freq[term]
                idf = self._idf(term)
                num = tf * (self.K1 + 1)
                denom = tf + self.K1 * (1 - self.B + self.B * dl / self.avgdl)
                score += idf * (self.DELTA + num / denom)
            if score > 0:
                scores.append((i, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def _rrf(
    dense: List[Tuple[str, float]],
    sparse: List[Tuple[str, float]],
    dw: float = 0.70,
    sw: float = 0.30,
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Weighted Reciprocal Rank Fusion."""
    fused: Dict[str, float] = {}
    for rank, (doc_id, _) in enumerate(dense):
        fused[doc_id] = fused.get(doc_id, 0.0) + dw / (k + rank + 1)
    for rank, (doc_id, _) in enumerate(sparse):
        fused[doc_id] = fused.get(doc_id, 0.0) + sw / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# Per-topic FAISS index wrapper
# ══════════════════════════════════════════════════════════════════════════════
class _TopicIndex:
    """Manages one FAISS HNSW index + metadata JSON for a single topic."""

    def __init__(self, topic_id: str):
        self.topic_id = topic_id
        self.dir = _FAISS_DATA / topic_id.replace("-", "_")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.faiss"
        self.meta_path = self.dir / "metadata.json"
        self._index = None
        self._ids: List[str] = []
        self._docs: List[str] = []
        self._metas: List[Dict] = []
        self._bm25: Optional[_BM25Index] = None
        self._load()

    def _load(self):
        """Load existing index and metadata from disk."""
        try:
            import faiss
            if self.index_path.exists() and self.meta_path.exists():
                self._index = faiss.read_index(str(self.index_path))
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                self._ids = meta.get("ids", [])
                self._docs = meta.get("docs", [])
                self._metas = meta.get("metas", [])
                print(f"[FAISS] Loaded topic '{self.topic_id}': {len(self._ids)} vectors")
        except Exception as e:
            print(f"[FAISS] Load error for '{self.topic_id}': {e}")
            self._index = None

    def _save(self):
        """Persist index and metadata to disk."""
        try:
            import faiss
            if self._index is not None:
                faiss.write_index(self._index, str(self.index_path))
            self.meta_path.write_text(
                json.dumps({
                    "ids": self._ids,
                    "docs": self._docs,
                    "metas": self._metas,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[FAISS] Save error for '{self.topic_id}': {e}")

    def _get_or_create_index(self, dim: int):
        """Lazily create HNSW or Flat index on first add."""
        import faiss
        if self._index is not None:
            return self._index

        if settings.FAISS_INDEX_TYPE == "hnsw":
            # HNSW inner product (cosine after L2 normalization)
            index = faiss.IndexHNSWFlat(dim, settings.FAISS_HNSW_M, faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = settings.FAISS_HNSW_EF_CONSTRUCTION
            index.hnsw.efSearch = settings.FAISS_HNSW_EF_SEARCH
        else:
            index = faiss.IndexFlatIP(dim)  # Flat inner product (exact)

        self._index = index
        return index

    @staticmethod
    def _normalize(vecs: np.ndarray) -> np.ndarray:
        """L2-normalize vectors for cosine similarity via inner product."""
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (vecs / norms).astype(np.float32)

    def add(self, ids: List[str], docs: List[str], metas: List[Dict], embeddings: List[List[float]]):
        """Add vectors to the index. Skips duplicate IDs."""
        existing_ids = set(self._ids)
        new_idx = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
        if not new_idx:
            return

        new_ids = [ids[i] for i in new_idx]
        new_docs = [docs[i] for i in new_idx]
        new_metas = [metas[i] for i in new_idx]
        new_embs = [embeddings[i] for i in new_idx]

        # Determine target dimension from majority or existing index
        target_dim = self._index.d if self._index is not None else max((len(e) for e in new_embs if isinstance(e, (list, tuple))), default=3072)

        # Standardize all vectors to target_dim (prevent inhomogeneous shape errors)
        fixed_embs = []
        for e in new_embs:
            if not isinstance(e, (list, tuple)):
                fixed_embs.append([0.0] * target_dim)
            elif len(e) == target_dim:
                fixed_embs.append(e)
            elif len(e) < target_dim:
                fixed_embs.append(list(e) + [0.0] * (target_dim - len(e)))
            else:
                fixed_embs.append(list(e[:target_dim]))

        vecs = np.array(fixed_embs, dtype=np.float32)
        vecs = self._normalize(vecs)
        dim = vecs.shape[1]

        index = self._get_or_create_index(dim)
        index.add(vecs)

        self._ids.extend(new_ids)
        self._docs.extend(new_docs)
        self._metas.extend(new_metas)
        self._bm25 = None  # invalidate BM25 cache
        self._save()

    def search_dense(self, query_vec: List[float], top_k: int, min_score: float) -> List[Dict]:
        """Dense HNSW cosine search. Returns chunks sorted by score desc."""
        if self._index is None or len(self._ids) == 0:
            return []

        try:
            import faiss
            q = np.array([query_vec], dtype=np.float32)
            q = self._normalize(q)
            k = min(top_k, len(self._ids))
            scores, indices = self._index.search(q, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._ids):
                    continue
                s = float(score)
                if s < min_score:
                    continue
                meta = self._metas[idx]
                effective_text = meta.get("parent_text") or self._docs[idx]
                results.append({
                    "id": self._ids[idx],
                    "text": effective_text,
                    "child_text": self._docs[idx] if meta.get("parent_text") else None,
                    "metadata": meta,
                    "score": round(s, 4),
                })
            return results
        except Exception as e:
            print(f"[FAISS] Dense search error: {e}")
            return []

    def _get_bm25(self) -> Optional[_BM25Index]:
        if self._bm25 is None and self._ids:
            self._bm25 = _BM25Index(self._ids, self._docs, self._metas)
        return self._bm25

    def search_bm25(self, query: str, top_k: int) -> List[Dict]:
        """BM25 keyword search. Returns chunks sorted by score desc."""
        bm25 = self._get_bm25()
        if bm25 is None:
            return []
        hits = bm25.search(query, top_k=top_k)
        if not hits:
            return []
        max_s = hits[0][1] if hits else 1.0
        results = []
        for idx, raw_score in hits:
            norm_score = round(raw_score / max(max_s, 1e-6), 4)
            results.append({
                "id": bm25.ids[idx],
                "text": bm25.docs[idx],
                "metadata": bm25.metas[idx],
                "score": norm_score,
                "bm25_raw": round(raw_score, 4),
            })
        return results

    def count(self) -> int:
        return len(self._ids)

    def delete(self):
        """Remove all index files for this topic."""
        import shutil
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
        except Exception:
            pass
        self._index = None
        self._ids = []
        self._docs = []
        self._metas = []
        self._bm25 = None


# ══════════════════════════════════════════════════════════════════════════════
# FAISSVectorStore — Public API (drop-in replacement for ChromaDB VectorStore)
# ══════════════════════════════════════════════════════════════════════════════
class FAISSVectorStore:
    """
    FAISS-backed vector store with hybrid BM25 search and RRF fusion.
    Drop-in replacement for the legacy ChromaDB VectorStore.
    """

    def __init__(self):
        _FAISS_DATA.mkdir(parents=True, exist_ok=True)
        self._topics: Dict[str, _TopicIndex] = {}

    def _topic(self, topic_id: str) -> _TopicIndex:
        if topic_id not in self._topics:
            self._topics[topic_id] = _TopicIndex(topic_id)
        return self._topics[topic_id]

    # ── Add ───────────────────────────────────────────────────────────────────
    def add_chunks(
        self,
        topic_id: str,
        chunks: List[Dict],
        embeddings: List[List[float]],
    ) -> None:
        """Add text chunks with pre-computed embeddings."""
        ids = [f"{topic_id}_{i}_{hash(c['text']) % 10**8}" for i, c in enumerate(chunks)]
        docs = [c["text"] for c in chunks]
        metas = []
        for c in chunks:
            meta = {}
            for k, v in c.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)
            metas.append(meta)
        self._topic(topic_id).add(ids, docs, metas, embeddings)

    # ── Dense search ──────────────────────────────────────────────────────────
    def search(
        self,
        topic_id: str,
        query_embedding: List[float],
        top_k: int = None,
        where: Optional[Dict] = None,
        min_score: float = None,
    ) -> List[Dict]:
        """Dense cosine similarity search via FAISS HNSW."""
        top_k = top_k or settings.TOP_K_RETRIEVAL
        min_score = min_score if min_score is not None else settings.MIN_CHUNK_SCORE
        results = self._topic(topic_id).search_dense(query_embedding, top_k, min_score)
        # Apply metadata filter if provided
        if where and results:
            results = [r for r in results if all(r["metadata"].get(k) == v for k, v in where.items())]
        return results

    # ── BM25 sparse search ────────────────────────────────────────────────────
    def search_bm25(
        self,
        topic_id: str,
        query: str,
        top_k: int = None,
    ) -> List[Dict]:
        """BM25 keyword search."""
        top_k = top_k or settings.TOP_K_RETRIEVAL
        return self._topic(topic_id).search_bm25(query, top_k)

    # ── Hybrid search (Dense + BM25 + RRF) ───────────────────────────────────
    def search_hybrid(
        self,
        topic_id: str,
        query_embedding: List[float],
        query_text: str,
        top_k: int = None,
        min_score: float = None,
    ) -> List[Dict]:
        """
        Hybrid search: FAISS dense + BM25 sparse fused via weighted RRF.
        Returns top_k results with citation metadata.
        """
        if not settings.ENABLE_HYBRID_SEARCH:
            return self.search(topic_id, query_embedding, top_k, min_score=min_score)

        top_k = top_k or settings.TOP_K_RETRIEVAL
        retrieval_k = min(top_k * 2, 20)

        dense_chunks = self.search(topic_id, query_embedding, top_k=retrieval_k, min_score=0.0)
        sparse_chunks = self.search_bm25(topic_id, query_text, top_k=retrieval_k)

        all_chunks: Dict[str, Dict] = {}
        for c in dense_chunks:
            all_chunks[c["id"]] = c
        for c in sparse_chunks:
            if c["id"] not in all_chunks:
                all_chunks[c["id"]] = c

        if not all_chunks:
            return []

        dense_ranked = [(c["id"], c["score"]) for c in dense_chunks]
        sparse_ranked = [(c["id"], c["score"]) for c in sparse_chunks]

        fused = _rrf(dense_ranked, sparse_ranked, dw=settings.DENSE_WEIGHT, sw=settings.SPARSE_WEIGHT)

        max_rrf = (settings.DENSE_WEIGHT + settings.SPARSE_WEIGHT) / 61.0
        results = []
        for doc_id, fused_score in fused[:top_k]:
            if doc_id not in all_chunks:
                continue
            chunk = dict(all_chunks[doc_id])
            norm_rrf = min(1.0, fused_score / max(max_rrf, 1e-6))
            orig = chunk.get("score", 0.5)
            chunk["score"] = round(max(orig, norm_rrf * 0.95), 4)
            chunk["fused_raw"] = round(fused_score, 6)
            chunk["fused"] = True
            # Attach citation fields for Stage 4 precise citations
            meta = chunk.get("metadata", {})
            chunk["citation"] = {
                "source": meta.get("source", ""),
                "page": meta.get("page", 0),
                "section": meta.get("section_title", ""),
                "section_path": meta.get("section_path", ""),
            }
            results.append(chunk)

        return results

    # ── Page-filtered retrieval ───────────────────────────────────────────────
    def get_chunks_by_pages(self, topic_id: str, pages: List[int]) -> List[Dict]:
        """Return all chunks matching given page numbers (metadata filter)."""
        if not pages:
            return []
        topic = self._topic(topic_id)
        if topic.count() == 0 and topic_id.startswith("sec_"):
            parts = topic_id.split("_", 2)
            if len(parts) >= 3:
                raw_topic = parts[2]
                fallback_t = self._topic(raw_topic)
                if fallback_t.count() > 0:
                    topic = fallback_t

        if topic.count() == 0:
            return []

        target = set(int(p) for p in pages) | set(str(p) for p in pages)
        results = []
        for id_, doc, meta in zip(topic._ids, topic._docs, topic._metas):
            p_val = meta.get("page")
            if p_val in target or (p_val is not None and str(p_val) in target):
                effective_text = meta.get("parent_text") or doc
                results.append({
                    "id": id_,
                    "text": effective_text,
                    "metadata": meta,
                    "score": 1.0,
                })
        return results

    # ── Utility ───────────────────────────────────────────────────────────────
    def count(self, topic_id: str) -> int:
        return self._topic(topic_id).count()

    def delete_topic(self, topic_id: str) -> None:
        t = self._topics.pop(topic_id, None)
        if t:
            t.delete()
        else:
            _TopicIndex(topic_id).delete()

    def delete_collection(self, collection_name: str) -> None:
        """Alias for delete_topic (backward compat with ChromaDB interface)."""
        self.delete_topic(collection_name)

    def reset(self) -> None:
        """Delete ALL topic indexes."""
        for t in list(self._topics.values()):
            t.delete()
        self._topics.clear()
        try:
            import shutil
            shutil.rmtree(_FAISS_DATA, ignore_errors=True)
            _FAISS_DATA.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def cache_stats(self) -> Dict:
        return {
            "backend": "faiss",
            "index_type": settings.FAISS_INDEX_TYPE,
            "topics_loaded": len(self._topics),
            "topics": {k: v.count() for k, v in self._topics.items()},
        }

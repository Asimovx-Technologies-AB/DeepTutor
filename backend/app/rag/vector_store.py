"""
Advanced ChromaDB vector store wrapper with:
  - Hybrid search (dense cosine + BM25 sparse, fused via RRF)
  - Per-topic BM25 in-memory index (auto-rebuilt from ChromaDB on first use)
  - Score thresholding (MIN_CHUNK_SCORE)
  - Richer metadata support (section_title, estimated_tokens, chunk_type)
"""
import os
import re
import math
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings

settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
# Minimal BM25 index (same as reranker but stored per-collection for full-corpus search)
# ══════════════════════════════════════════════════════════════════════════════
def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) > 1]


class _BM25CollectionIndex:
    """
    BM25 index over ALL documents in a ChromaDB collection.
    Built lazily on first use and cached in memory per topic_id.
    K1=1.5, b=0.75, delta=1.0 (BM25+).
    """
    K1 = 1.5
    B  = 0.75
    DELTA = 1.0

    def __init__(self, ids: List[str], docs: List[str], metas: List[Dict]):
        self.ids   = ids
        self.docs  = docs
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
            for term in doc:
                freq[term] = freq.get(term, 0) + 1
            self.tf_docs.append((freq, len(doc)))

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Returns list of (doc_index, score) sorted by score desc."""
        q_tokens = _tokenize(query)
        scores = []
        for i, (freq, dl) in enumerate(self.tf_docs):
            score = 0.0
            for term in q_tokens:
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


def _reciprocal_rank_fusion(
    dense_hits: List[Tuple[str, float]],
    sparse_hits: List[Tuple[str, float]],
    dense_weight: float = 0.70,
    sparse_weight: float = 0.30,
    k: int = 60,
) -> List[Tuple[str, float]]:
    """
    Fuse dense and sparse ranked lists via weighted RRF.
    dense_hits / sparse_hits: list of (doc_id, score) sorted best→worst
    Returns fused list of (doc_id, fused_score) sorted best→worst.
    """
    fused: Dict[str, float] = {}

    for rank, (doc_id, _) in enumerate(dense_hits):
        fused[doc_id] = fused.get(doc_id, 0.0) + dense_weight / (k + rank + 1)

    for rank, (doc_id, _) in enumerate(sparse_hits):
        fused[doc_id] = fused.get(doc_id, 0.0) + sparse_weight / (k + rank + 1)

    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# VectorStore
# ══════════════════════════════════════════════════════════════════════════════
class VectorStore:
    def __init__(self):
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Per-topic BM25 index cache: topic_id → _BM25CollectionIndex
        self._bm25_indexes: Dict[str, _BM25CollectionIndex] = {}

    # ── Collection helpers ─────────────────────────────────────────────────────
    def _collection(self, topic_id: str):
        """Get or create collection for a topic."""
        return self._client.get_or_create_collection(
            name=f"topic_{topic_id.replace('-', '_')}",
            metadata={"hnsw:space": "cosine"},
        )

    def _invalidate_bm25(self, topic_id: str) -> None:
        """Invalidate cached BM25 index after new documents are added."""
        self._bm25_indexes.pop(topic_id, None)

    def _get_bm25_index(self, topic_id: str) -> Optional[_BM25CollectionIndex]:
        """
        Get or build the BM25 index for a topic collection.
        Fetches all documents from ChromaDB and builds the index lazily.
        """
        if topic_id in self._bm25_indexes:
            return self._bm25_indexes[topic_id]

        collection = self._collection(topic_id)
        count = collection.count()
        if count == 0:
            return None

        try:
            # Fetch all documents (capped at 10k to avoid memory issues)
            batch_size = min(count, 10_000)
            result = collection.get(
                limit=batch_size,
                include=["documents", "metadatas"],
            )
            if not result or not result.get("ids"):
                return None

            index = _BM25CollectionIndex(
                ids=result["ids"],
                docs=result["documents"],
                metas=result["metadatas"],
            )
            self._bm25_indexes[topic_id] = index
            return index
        except Exception:
            return None

    # ── Add chunks ─────────────────────────────────────────────────────────────
    def add_chunks(
        self,
        topic_id: str,
        chunks: List[Dict],         # [{text, metadata}]
        embeddings: List[List[float]],
    ) -> None:
        """Add text chunks with pre-computed embeddings."""
        collection = self._collection(topic_id)
        ids = [f"{topic_id}_{i}_{hash(c['text']) % 10**8}" for i, c in enumerate(chunks)]
        documents = [c["text"] for c in chunks]
        # Ensure metadata values are JSON-serialisable primitives
        metadatas = []
        for c in chunks:
            meta = {}
            for k, v in c.get("metadata", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)
            metadatas.append(meta)

        if not ids:
            return

        # Avoid duplicate IDs
        existing = set(collection.get(ids=ids)["ids"])
        new_idx = [i for i, id_ in enumerate(ids) if id_ not in existing]
        if not new_idx:
            return

        collection.add(
            ids=[ids[i] for i in new_idx],
            documents=[documents[i] for i in new_idx],
            embeddings=[embeddings[i] for i in new_idx],
            metadatas=[metadatas[i] for i in new_idx],
        )
        # Invalidate BM25 index so it gets rebuilt with new docs
        self._invalidate_bm25(topic_id)

    # ── Dense search ───────────────────────────────────────────────────────────
    def search(
        self,
        topic_id: str,
        query_embedding: List[float],
        top_k: int = None,
        where: Optional[Dict] = None,
        min_score: float = None,
    ) -> List[Dict]:
        """
        Dense cosine similarity search.
        Returns top_k most similar chunks: { text, metadata, score }
        Filters out chunks below min_score threshold.
        """
        top_k = top_k or settings.TOP_K_RETRIEVAL
        min_score = min_score if min_score is not None else settings.MIN_CHUNK_SCORE

        collection = self._collection(topic_id)
        if collection.count() == 0:
            return []

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        try:
            results = collection.query(**query_kwargs)
        except Exception:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]
        ids = results.get("ids", [[]])[0]

        chunks = []
        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
            score = round(1 - dist, 4)
            if score < min_score:
                continue
            chunks.append({
                "id": doc_id,
                "text": doc,
                "metadata": meta,
                "score": score,
            })

        return chunks

    # ── BM25 sparse search ─────────────────────────────────────────────────────
    def search_bm25(
        self,
        topic_id: str,
        query: str,
        top_k: int = None,
    ) -> List[Dict]:
        """
        BM25 keyword search over the full topic collection.
        Returns top_k results: { id, text, metadata, score (normalised 0-1) }
        """
        top_k = top_k or settings.TOP_K_RETRIEVAL
        bm25_idx = self._get_bm25_index(topic_id)
        if bm25_idx is None:
            return []

        hits = bm25_idx.search(query, top_k=top_k)
        if not hits:
            return []

        max_score = hits[0][1] if hits else 1.0
        chunks = []
        for doc_idx, raw_score in hits:
            norm_score = round(raw_score / max(max_score, 1e-6), 4)
            chunks.append({
                "id": bm25_idx.ids[doc_idx],
                "text": bm25_idx.docs[doc_idx],
                "metadata": bm25_idx.metas[doc_idx],
                "score": norm_score,
                "bm25_raw": round(raw_score, 4),
            })
        return chunks

    # ── Hybrid search ──────────────────────────────────────────────────────────
    def search_hybrid(
        self,
        topic_id: str,
        query_embedding: List[float],
        query_text: str,
        top_k: int = None,
        min_score: float = None,
    ) -> List[Dict]:
        """
        Hybrid search: dense (ChromaDB cosine) + sparse (BM25) fused via RRF.
        Returns top_k results sorted by fused relevance score.
        """
        if not settings.ENABLE_HYBRID_SEARCH:
            return self.search(topic_id, query_embedding, top_k, min_score=min_score)

        top_k = top_k or settings.TOP_K_RETRIEVAL
        min_score = min_score if min_score is not None else 0.0  # don't filter before fusion

        # Fetch more candidates for both signals (fused result will be trimmed)
        retrieval_k = min(top_k * 2, 20)

        dense_chunks = self.search(topic_id, query_embedding, top_k=retrieval_k, min_score=0.0)
        sparse_chunks = self.search_bm25(topic_id, query_text, top_k=retrieval_k)

        # Build lookup maps: doc_id → chunk
        all_chunks: Dict[str, Dict] = {}
        for c in dense_chunks:
            all_chunks[c["id"]] = c
        for c in sparse_chunks:
            if c["id"] not in all_chunks:
                all_chunks[c["id"]] = c

        if not all_chunks:
            return []

        # Prepare ranked lists for RRF
        dense_ranked  = [(c["id"], c["score"]) for c in dense_chunks]
        sparse_ranked = [(c["id"], c["score"]) for c in sparse_chunks]

        fused = _reciprocal_rank_fusion(
            dense_ranked,
            sparse_ranked,
            dense_weight=settings.DENSE_WEIGHT,
            sparse_weight=settings.SPARSE_WEIGHT,
        )

        max_rrf = (settings.DENSE_WEIGHT + settings.SPARSE_WEIGHT) / 61.0
        results = []
        for doc_id, fused_score in fused[:top_k]:
            if doc_id not in all_chunks:
                continue
            chunk = dict(all_chunks[doc_id])
            orig_score = chunk.get("score", 0.5)
            norm_rrf = min(1.0, fused_score / max(max_rrf, 1e-6))
            chunk["score"] = round(max(orig_score, norm_rrf * 0.95), 4)
            chunk["fused_raw"] = round(fused_score, 6)
            chunk["fused"] = True
            results.append(chunk)

        return results

    # ── Page-filtered retrieval ────────────────────────────────────────────────
    def get_chunks_by_pages(
        self,
        topic_id: str,
        pages: List[int],
    ) -> List[Dict]:
        """
        Retrieve chunks that belong ONLY to specific page numbers using metadata filter.
        Returns list of chunks where chunk.metadata.page in pages. Skips vector search completely.
        """
        collection = self._collection(topic_id)
        if collection.count() == 0 or not pages:
            return []

        int_pages = [int(p) for p in pages]
        str_pages = [str(p) for p in pages]
        target_set = set(int_pages + str_pages)

        chunks = []
        try:
            # Query int metadata
            where_int = {"page": int_pages[0]} if len(int_pages) == 1 else {"page": {"$in": int_pages}}
            res_int = collection.get(where=where_int, include=["documents", "metadatas"])
            if res_int and res_int.get("documents"):
                ids = res_int.get("ids", [])
                for idx, (doc, meta) in enumerate(zip(res_int["documents"], res_int["metadatas"])):
                    chunks.append({
                        "id": ids[idx] if idx < len(ids) else f"page_{idx}",
                        "text": doc,
                        "metadata": meta,
                        "score": 1.0,
                    })

            # If empty, query string metadata fallback
            if not chunks:
                where_str = {"page": str_pages[0]} if len(str_pages) == 1 else {"page": {"$in": str_pages}}
                res_str = collection.get(where=where_str, include=["documents", "metadatas"])
                if res_str and res_str.get("documents"):
                    ids = res_str.get("ids", [])
                    for idx, (doc, meta) in enumerate(zip(res_str["documents"], res_str["metadatas"])):
                        chunks.append({
                            "id": ids[idx] if idx < len(ids) else f"page_{idx}",
                            "text": doc,
                            "metadata": meta,
                            "score": 1.0,
                        })

            # Strict verification filter: guarantee 100% context precision
            verified_chunks = []
            seen_ids = set()
            for c in chunks:
                p_val = c.get("metadata", {}).get("page")
                if p_val in target_set or (p_val is not None and str(p_val) in str_pages):
                    if c["id"] not in seen_ids:
                        seen_ids.add(c["id"])
                        verified_chunks.append(c)

            return verified_chunks
        except Exception:
            return []

    # ── Utility ────────────────────────────────────────────────────────────────
    def count(self, topic_id: str) -> int:
        return self._collection(topic_id).count()

    def delete_topic(self, topic_id: str) -> None:
        try:
            self._client.delete_collection(f"topic_{topic_id.replace('-', '_')}")
            self._invalidate_bm25(topic_id)
        except Exception:
            pass

    def reset(self) -> None:
        try:
            for col in self._client.list_collections():
                name = col.name if hasattr(col, "name") else str(col)
                self._client.delete_collection(name)
            self._bm25_indexes.clear()
        except Exception:
            pass

    def cache_stats(self) -> Dict:
        """Return stats about BM25 index cache."""
        return {
            "bm25_indexes_cached": len(self._bm25_indexes),
            "topics": list(self._bm25_indexes.keys()),
        }


# Singleton
vector_store = VectorStore()

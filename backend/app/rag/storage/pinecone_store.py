"""
Stage 3 — Pinecone Cloud Serverless Vector Store
=================================================
Cloud serverless vector store adapter for production hosting.

Features:
  - Pinecone Serverless Index (Cosine metric, 3072 dimensions)
  - Topic / User section isolation via Pinecone namespaces
  - Hybrid search (Pinecone dense + in-memory BM25 with weighted RRF)
  - Identical public interface to FAISSVectorStore and VectorStore
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from app.core.config import get_settings

settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
# BM25 Sparse Index Helper
# ══════════════════════════════════════════════════════════════════════════════
def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) > 1]


class _BM25Index:
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
# PineconeVectorStore
# ══════════════════════════════════════════════════════════════════════════════
class PineconeVectorStore:
    """
    Production cloud vector store backed by Pinecone Serverless.
    Drop-in replacement for FAISSVectorStore and VectorStore.
    """

    def __init__(self):
        self._client = None
        self._index = None
        self._bm25_caches: Dict[str, _BM25Index] = {}
        self._doc_caches: Dict[str, List[Dict]] = {}

    def _get_index(self):
        """Lazy initialization of Pinecone client and index."""
        if self._index is not None:
            return self._index

        from pinecone import Pinecone
        api_key = settings.PINECONE_API_KEY
        if not api_key:
            raise ValueError("PINECONE_API_KEY is not set in backend/.env")

        self._client = Pinecone(api_key=api_key)
        index_name = getattr(settings, "PINECONE_INDEX_NAME", "deeptutor")
        self._index = self._client.Index(index_name)
        print(f"[PINECONE] Connected to cloud index '{index_name}' successfully.")
        return self._index

    def _sanitize_namespace(self, topic_id: str) -> str:
        """Pinecone namespace names must be valid ASCII strings."""
        if not topic_id:
            return "general"
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', str(topic_id))

    def add_chunks(
        self,
        topic_id: str,
        chunks: List[Dict],
        embeddings: List[List[float]],
    ) -> None:
        """Upload vectors and metadata to Pinecone under the topic namespace."""
        if not chunks or not embeddings:
            return

        index = self._get_index()
        namespace = self._sanitize_namespace(topic_id)

        records = []
        doc_cache_items = []
        target_dim = 3072

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_text = chunk.get("text", "")
            raw_meta = chunk.get("metadata", {})
            
            safe_meta = {"text": chunk_text[:2000]}
            for k, v in raw_meta.items():
                if isinstance(v, (str, int, float, bool)):
                    safe_meta[k] = v
                elif v is not None:
                    safe_meta[k] = str(v)

            # Auto-standardize dimension to 3072
            if not isinstance(emb, (list, tuple)):
                fixed_emb = [0.0] * target_dim
            elif len(emb) == target_dim:
                fixed_emb = list(emb)
            elif len(emb) < target_dim:
                fixed_emb = list(emb) + [0.0] * (target_dim - len(emb))
            else:
                fixed_emb = list(emb[:target_dim])

            doc_id = f"{namespace}_{i}_{hash(chunk_text) % 10**8}"
            records.append({
                "id": doc_id,
                "values": fixed_emb,
                "metadata": safe_meta,
            })
            doc_cache_items.append({
                "id": doc_id,
                "text": chunk_text,
                "metadata": raw_meta,
            })

        batch_size = 50
        batches = [records[b:b + batch_size] for b in range(0, len(records), batch_size)]

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(batches)))) as executor:
            list(executor.map(lambda b: index.upsert(vectors=b, namespace=namespace), batches))

        if namespace not in self._doc_caches:
            self._doc_caches[namespace] = []
        self._doc_caches[namespace].extend(doc_cache_items)
        self._bm25_caches.pop(namespace, None)

        print(f"[PINECONE] Upserted {len(records)} vectors to namespace '{namespace}'")

    def search(
        self,
        topic_id: str,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        where: Optional[Dict] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict]:
        """Dense cosine similarity search via Pinecone cloud endpoint."""
        index = self._get_index()
        namespace = self._sanitize_namespace(topic_id)
        top_k = top_k or settings.TOP_K_RETRIEVAL
        min_score = min_score if min_score is not None else settings.MIN_CHUNK_SCORE

        # Auto-standardize query vector to 3072
        target_dim = 3072
        if not isinstance(query_embedding, (list, tuple)):
            fixed_q = [0.0] * target_dim
        elif len(query_embedding) == target_dim:
            fixed_q = list(query_embedding)
        elif len(query_embedding) < target_dim:
            fixed_q = list(query_embedding) + [0.0] * (target_dim - len(query_embedding))
        else:
            fixed_q = list(query_embedding[:target_dim])

        try:
            query_kwargs = {
                "vector": fixed_q,
                "top_k": min(top_k, 50),
                "include_metadata": True,
                "namespace": namespace,
            }
            if where:
                query_kwargs["filter"] = where

            response = index.query(**query_kwargs)
            matches = response.get("matches", [])

            results = []
            for m in matches:
                score = float(m.get("score", 0.0))
                if score < min_score:
                    continue
                meta = m.get("metadata", {})
                text = meta.get("text", "")
                results.append({
                    "id": m.get("id"),
                    "text": text,
                    "metadata": meta,
                    "score": round(score, 4),
                })
            return results
        except Exception as e:
            print(f"[PINECONE ERROR] Dense search failed: {e}")
            return []

    def _get_bm25(self, namespace: str) -> Optional[_BM25Index]:
        if namespace not in self._bm25_caches:
            docs = self._doc_caches.get(namespace, [])
            if docs:
                ids = [d["id"] for d in docs]
                texts = [d["text"] for d in docs]
                metas = [d["metadata"] for d in docs]
                self._bm25_caches[namespace] = _BM25Index(ids, texts, metas)
        return self._bm25_caches.get(namespace)

    def search_bm25(self, topic_id: str, query: str, top_k: Optional[int] = None) -> List[Dict]:
        """BM25 keyword search."""
        namespace = self._sanitize_namespace(topic_id)
        bm25 = self._get_bm25(namespace)
        if bm25 is None:
            return []
        top_k = top_k or settings.TOP_K_RETRIEVAL
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

    def search_hybrid(
        self,
        topic_id: str,
        query_embedding: List[float],
        query_text: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict]:
        """Hybrid search combining Pinecone dense results + BM25 sparse results."""
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
            return dense_chunks

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
            meta = chunk.get("metadata", {})
            chunk["citation"] = {
                "source": meta.get("source", ""),
                "page": meta.get("page", 0),
                "section": meta.get("section_title", ""),
                "section_path": meta.get("section_path", ""),
            }
            results.append(chunk)

        return results

    def get_chunks_by_pages(self, topic_id: str, pages: List[int]) -> List[Dict]:
        """Return all chunks matching given page numbers."""
        namespace = self._sanitize_namespace(topic_id)
        cached = self._doc_caches.get(namespace, [])
        if cached:
            target = set(str(p) for p in pages) | set(pages)
            return [
                {"id": d["id"], "text": d["text"], "metadata": d["metadata"], "score": 1.0}
                for d in cached
                if d["metadata"].get("page") in target or str(d["metadata"].get("page")) in {str(p) for p in pages}
            ]

        index = self._get_index()
        try:
            res = index.query(
                vector=[0.0] * 3072,
                top_k=20,
                include_metadata=True,
                namespace=namespace,
                filter={"page": {"$in": pages}},
            )
            return [
                {"id": m.get("id"), "text": m.get("metadata", {}).get("text", ""), "metadata": m.get("metadata", {}), "score": 1.0}
                for m in res.get("matches", [])
            ]
        except Exception:
            return []

    def count(self, topic_id: str) -> int:
        """Get vector count in topic namespace."""
        try:
            index = self._get_index()
            namespace = self._sanitize_namespace(topic_id)
            stats = index.describe_index_stats()
            ns_dict = getattr(stats, "namespaces", {}) or {}
            if isinstance(ns_dict, dict) and namespace in ns_dict:
                ns_stat = ns_dict[namespace]
                return getattr(ns_stat, "vector_count", 0) or (ns_stat.get("vector_count", 0) if isinstance(ns_stat, dict) else 0)
            return len(self._doc_caches.get(namespace, []))
        except Exception:
            return len(self._doc_caches.get(self._sanitize_namespace(topic_id), []))

    def get_all_chunks(self, topic_id: str) -> List[Dict]:
        """Fetch cached or retrieved chunks for a topic namespace."""
        namespace = self._sanitize_namespace(topic_id)
        if namespace in self._doc_caches and self._doc_caches[namespace]:
            return self._doc_caches[namespace]
        return self.search(topic_id, [0.0] * 3072, top_k=50, min_score=0.0)

    def delete_topic(self, topic_id: str) -> None:
        """Delete all vectors under the namespace from Pinecone."""
        namespace = self._sanitize_namespace(topic_id)
        try:
            index = self._get_index()
            index.delete(delete_all=True, namespace=namespace)
        except Exception as e:
            print(f"[PINECONE] Delete namespace error: {e}")
        self._doc_caches.pop(namespace, None)
        self._bm25_caches.pop(namespace, None)

    def delete_collection(self, collection_name: str) -> None:
        self.delete_topic(collection_name)

    def reset(self) -> None:
        """Clear all vectors in index."""
        try:
            index = self._get_index()
            index.delete(delete_all=True)
        except Exception as e:
            print(f"[PINECONE] Reset error: {e}")
        self._doc_caches.clear()
        self._bm25_caches.clear()


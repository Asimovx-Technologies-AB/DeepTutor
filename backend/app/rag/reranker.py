"""
Advanced Reranker Module — Industry-Level RAG.

Implements:
  BM25Reranker      : Fast keyword-based reranking (zero LLM calls, sub-ms)
  CrossEncoderReranker: LLM-scored (query, chunk) relevance (slower, accurate)
  HybridReranker    : Reciprocal Rank Fusion of dense + BM25 signals
  
Usage:
  reranker = get_reranker()   # returns type from config
  reranked = await reranker.rerank(query, chunks, top_k=5)
"""
import math
import re
from typing import List, Dict, Optional

from app.core.config import get_settings

settings = get_settings()


# ── Text normalization ─────────────────────────────────────────────────────────
def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) > 1]


# ══════════════════════════════════════════════════════════════════════════════
# BM25 Implementation (rank-bm25 compatible interface, pure Python fallback)
# ══════════════════════════════════════════════════════════════════════════════
class _BM25Index:
    """
    BM25 index built at rerank-time from the candidate corpus.
    Uses BM25+ variant (Lv & Zhai 2011) for better short-document handling.
    k1=1.5, b=0.75 (standard defaults).
    """
    K1 = 1.5
    B  = 0.75
    DELTA = 1.0  # BM25+

    def __init__(self, corpus: List[List[str]]):
        self.corpus = corpus
        self.n = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.n, 1)
        # Document frequency
        self.df: Dict[str, int] = {}
        for doc in corpus:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1
        # Term frequencies per doc
        self.tf: List[Dict[str, int]] = []
        for doc in corpus:
            freq: Dict[str, int] = {}
            for term in doc:
                freq[term] = freq.get(term, 0) + 1
            self.tf.append(freq)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        score = 0.0
        doc_tf = self.tf[doc_idx]
        dl = len(self.corpus[doc_idx])
        for term in query_tokens:
            if term not in doc_tf:
                continue
            tf = doc_tf[term]
            idf = self._idf(term)
            num = tf * (self.K1 + 1)
            denom = tf + self.K1 * (1 - self.B + self.B * dl / self.avgdl)
            score += idf * (self.DELTA + num / denom)
        return score

    def rank(self, query_tokens: List[str]) -> List[float]:
        return [self.score(query_tokens, i) for i in range(self.n)]


# ══════════════════════════════════════════════════════════════════════════════
# Reciprocal Rank Fusion
# ══════════════════════════════════════════════════════════════════════════════
def _reciprocal_rank_fusion(
    rankings: List[List[int]],
    weights: Optional[List[float]] = None,
    k: int = 60,
) -> List[float]:
    """
    Fuse multiple ranked lists via Reciprocal Rank Fusion.
    rankings: list of lists of original indices, each sorted best→worst
    weights : per-ranking weight (default uniform)
    Returns: fused score per original index (higher = better)
    """
    if not rankings:
        return []
    n = max(max(r) for r in rankings) + 1
    fused = [0.0] * n
    weights = weights or [1.0] * len(rankings)

    for rank_list, weight in zip(rankings, weights):
        for rank, idx in enumerate(rank_list):
            fused[idx] += weight / (k + rank + 1)

    return fused


# ══════════════════════════════════════════════════════════════════════════════
# BM25Reranker
# ══════════════════════════════════════════════════════════════════════════════
class BM25Reranker:
    """
    Reranks retrieved chunks using BM25+ scoring.
    Zero LLM calls — sub-millisecond for typical chunk sets.
    Fuses BM25 rank with original dense-retrieval rank via RRF.
    """

    def __init__(self, dense_weight: float = None, sparse_weight: float = None):
        self.dense_weight = dense_weight or settings.DENSE_WEIGHT
        self.sparse_weight = sparse_weight or settings.SPARSE_WEIGHT

    async def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = None,
    ) -> List[Dict]:
        top_k = top_k or settings.TOP_K_CHUNKS
        if not chunks:
            return []
        if len(chunks) <= 1:
            return chunks[:top_k]

        query_tokens = _tokenize(query)
        corpus = [_tokenize(c["text"]) for c in chunks]

        # Build BM25 index on candidate corpus
        bm25 = _BM25Index(corpus)
        bm25_scores = bm25.rank(query_tokens)

        # Original dense scores (from vector store cosine similarity)
        dense_scores = [c.get("score", 0.5) for c in chunks]

        # Rank by each signal
        n = len(chunks)
        dense_ranked  = sorted(range(n), key=lambda i: dense_scores[i],  reverse=True)
        bm25_ranked   = sorted(range(n), key=lambda i: bm25_scores[i],   reverse=True)

        # RRF fusion
        fused = _reciprocal_rank_fusion(
            [dense_ranked, bm25_ranked],
            weights=[self.dense_weight, self.sparse_weight],
        )

        # Sort by fused score and normalize to 0-1 range
        max_rrf = (self.dense_weight + self.sparse_weight) / 61.0
        order = sorted(range(n), key=lambda i: fused[i], reverse=True)
        reranked = []
        for rank, idx in enumerate(order[:top_k]):
            chunk = dict(chunks[idx])
            orig_score = chunk.get("score", 0.5)
            norm_rrf = min(1.0, fused[idx] / max(max_rrf, 1e-6))
            final_score = round(max(orig_score, norm_rrf * 0.95), 4)
            chunk["rerank_score"] = final_score
            chunk["score"]        = final_score
            chunk["bm25_score"]   = round(bm25_scores[idx], 4)
            chunk["rerank_pos"]   = rank + 1
            reranked.append(chunk)

        return reranked


# ══════════════════════════════════════════════════════════════════════════════
# CrossEncoderReranker (LLM-as-judge)
# ══════════════════════════════════════════════════════════════════════════════
class CrossEncoderReranker:
    """
    Reranks using local Ollama LLM to score each (query, chunk) pair.
    More accurate than BM25 but adds latency (~200-500ms per chunk).
    Falls back to BM25Reranker if Ollama is unavailable.
    """

    SCORE_PROMPT = """Rate how relevant this document passage is to the question.
Return ONLY a single integer score from 0 to 10 (10 = perfectly relevant, 0 = completely irrelevant).

Question: {query}

Passage:
{passage}

Score (0-10):"""

    def __init__(self):
        self._bm25_fallback = BM25Reranker()

    async def _score_chunk(self, query: str, chunk: Dict) -> float:
        from app.rag.ollama_client import ollama
        prompt = self.SCORE_PROMPT.format(
            query=query,
            passage=chunk["text"][:800],  # cap passage length
        )
        try:
            response = await ollama.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            # Extract first integer from response
            numbers = re.findall(r'\b(\d+)\b', response.strip())
            if numbers:
                score = min(10, max(0, int(numbers[0])))
                return score / 10.0
        except Exception:
            pass
        return chunk.get("score", 0.5)  # fallback to dense score

    async def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = None,
    ) -> List[Dict]:
        import asyncio
        top_k = top_k or settings.TOP_K_CHUNKS
        if not chunks:
            return []

        # Only score top 8 candidates to save latency
        candidates = chunks[:8]
        semaphore = asyncio.Semaphore(3)

        async def _sem_score(chunk: Dict) -> float:
            async with semaphore:
                return await self._score_chunk(query, chunk)

        try:
            scores = await asyncio.gather(*[_sem_score(c) for c in candidates])
        except Exception:
            # Full fallback to BM25
            return await self._bm25_fallback.rerank(query, chunks, top_k)

        # Sort by cross-encoder score, then combine with original dense rank via RRF
        n = len(candidates)
        ce_ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
        dense_ranked = sorted(range(n), key=lambda i: candidates[i].get("score", 0.5), reverse=True)

        fused = _reciprocal_rank_fusion(
            [ce_ranked, dense_ranked],
            weights=[0.6, 0.4],
        )
        max_rrf = (0.6 + 0.4) / 61.0
        order = sorted(range(n), key=lambda i: fused[i], reverse=True)

        reranked = []
        for rank, idx in enumerate(order[:top_k]):
            chunk = dict(candidates[idx])
            orig_score = chunk.get("score", 0.5)
            norm_rrf = min(1.0, fused[idx] / max(max_rrf, 1e-6))
            final_score = round(max(orig_score, norm_rrf * 0.95), 4)
            chunk["ce_score"]     = round(scores[idx], 4)
            chunk["rerank_score"] = final_score
            chunk["score"]        = final_score
            chunk["rerank_pos"]   = rank + 1
            reranked.append(chunk)

        return reranked


# ══════════════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════════════
def get_reranker():
    """Return the configured reranker based on RERANKER_TYPE setting."""
    rtype = settings.RERANKER_TYPE.lower()
    if rtype == "cross_encoder":
        return CrossEncoderReranker()
    else:
        return BM25Reranker()  # Default: fast BM25


# Singleton reranker (lazy-init per request is also fine)
reranker = get_reranker()

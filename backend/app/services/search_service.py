import math
import logging
from typing import List, Dict, Any, Tuple
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.schemas.pipeline import (
    HybridSearchQuery,
    HybridSearchResult,
    HybridVerificationCheck
)
from app.schemas.chunk import KnowledgeChunkRead
from app.services.embedding_service import default_embedding_service
from app.core.database import is_sqlite

logger = logging.getLogger(__name__)


class HybridSearchService:
    """
    Search Indexing Service providing:
    - Full-Text Search (tsvector / keyword lexical match)
    - Vector Semantic Search (cosine similarity)
    - Semantic Knowledge Graph Traversal
    - Reciprocal Rank Fusion (RRF)
    - Advanced Hybrid Consistency Checks & Modality Verification
    """

    @classmethod
    def execute_search(cls, session: Session, query: HybridSearchQuery) -> List[HybridSearchResult]:
        search_term = query.query.strip()
        doc_filter = query.document_id
        top_k = query.top_k

        # 1. Full-Text Search (Lexical)
        fts_hits = cls._execute_fts(session, search_term, doc_filter, query.chunk_type, limit=top_k * 3)

        # 2. Vector Semantic Search
        vector_hits = cls._execute_vector_search(session, search_term, doc_filter, query.chunk_type, limit=top_k * 3)

        # 3. Knowledge Graph Expansion
        graph_hits = cls._execute_graph_expansion(session, [h[0].id for h in (fts_hits[:3] + vector_hits[:3])])

        # 4. Reciprocal Rank Fusion (RRF)
        fused_results = cls._fuse_rankings(
            fts_hits=fts_hits,
            vector_hits=vector_hits,
            graph_hits=graph_hits,
            w_fts=query.fts_weight,
            w_vector=query.vector_weight,
            w_graph=query.graph_weight,
            k=60
        )

        # Sort by final score descending
        ranked_chunks = sorted(fused_results.values(), key=lambda x: x["rrf_score"], reverse=True)[:top_k]

        # 5. Hybrid Checks & Multi-Modal Verification
        results: List[HybridSearchResult] = []
        for rank_idx, item in enumerate(ranked_chunks, start=1):
            chunk_obj: KnowledgeChunk = item["chunk"]
            fts_score = item["fts_score"]
            vector_score = item["vector_score"]
            graph_score = item["graph_score"]

            verification = None
            if query.enable_hybrid_checks:
                verification = cls._perform_hybrid_check(
                    query_text=search_term,
                    chunk=chunk_obj,
                    fts_score=fts_score,
                    vector_score=vector_score,
                    graph_score=graph_score
                )

            chunk_read = KnowledgeChunkRead.model_validate(chunk_obj)
            results.append(
                HybridSearchResult(
                    chunk=chunk_read,
                    final_score=round(item["rrf_score"], 4),
                    rrf_rank=rank_idx,
                    verification=verification
                )
            )

        return results

    @classmethod
    def _execute_fts(
        cls, session: Session, query_text: str, doc_id: str | None, chunk_type: str | None, limit: int
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """Full-Text lexical search ranking."""
        base_q = session.query(KnowledgeChunk)
        if doc_id:
            base_q = base_q.filter(KnowledgeChunk.document_id == doc_id)
        if chunk_type:
            base_q = base_q.filter(KnowledgeChunk.chunk_type == chunk_type)

        keywords = [w.lower() for w in query_text.split() if len(w) > 2]
        if not keywords:
            return []

        # Construct multi-keyword pattern
        filters = [KnowledgeChunk.content.ilike(f"%{kw}%") for kw in keywords]
        matched = base_q.filter(or_(*filters)).limit(limit).all()

        scored = []
        for chunk in matched:
            content_lower = chunk.content.lower()
            hit_count = sum(content_lower.count(kw) for kw in keywords)
            score = min(hit_count * 0.25, 1.0)
            scored.append((chunk, score))

        return sorted(scored, key=lambda x: x[1], reverse=True)

    @classmethod
    def _execute_vector_search(
        cls, session: Session, query_text: str, doc_id: str | None, chunk_type: str | None, limit: int
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """Vector semantic search using embedding cosine similarity."""
        query_vec = default_embedding_service.embed_text(query_text)
        q_norm = np.linalg.norm(query_vec)

        base_q = session.query(KnowledgeChunk)
        if doc_id:
            base_q = base_q.filter(KnowledgeChunk.document_id == doc_id)
        if chunk_type:
            base_q = base_q.filter(KnowledgeChunk.chunk_type == chunk_type)

        chunks = base_q.limit(limit * 2).all()
        scored = []

        missing_chunks = [c for c in chunks if c.embedding is None]
        if missing_chunks:
            missing_contents = [c.content for c in missing_chunks]
            computed_embs = default_embedding_service.embed_batch(missing_contents)
            for c, emb in zip(missing_chunks, computed_embs):
                c.embedding = emb
            try:
                session.commit()
            except Exception:
                session.rollback()

        for chunk in chunks:
            chunk_vec = chunk.embedding
            if chunk_vec is not None:
                c_vec_np = np.array(chunk_vec, dtype=np.float32)
                c_norm = np.linalg.norm(c_vec_np)
                cosine = float(np.dot(query_vec, c_vec_np) / (q_norm * c_norm)) if q_norm > 0 and c_norm > 0 else 0.0
            else:
                cosine = 0.0
            scored.append((chunk, max(0.0, cosine)))

        return sorted(scored, key=lambda x: x[1], reverse=True)[:limit]

    @classmethod
    def _execute_graph_expansion(
        cls, session: Session, seed_chunk_ids: List[str]
    ) -> Dict[str, Tuple[KnowledgeChunk, float]]:
        """Traverses knowledge relationships to discover adjacent semantic nodes."""
        if not seed_chunk_ids:
            return {}

        rels = session.query(KnowledgeRelationship).filter(
            or_(
                KnowledgeRelationship.source_chunk_id.in_(seed_chunk_ids),
                KnowledgeRelationship.target_chunk_id.in_(seed_chunk_ids),
            )
        ).all()

        connected_ids = set()
        for r in rels:
            if r.source_chunk_id not in seed_chunk_ids:
                connected_ids.add(r.source_chunk_id)
            if r.target_chunk_id not in seed_chunk_ids:
                connected_ids.add(r.target_chunk_id)

        if not connected_ids:
            return {}

        connected_chunks = session.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(list(connected_ids))).all()
        return {c.id: (c, 0.8) for c in connected_chunks}

    @classmethod
    def _fuse_rankings(
        cls,
        fts_hits: List[Tuple[KnowledgeChunk, float]],
        vector_hits: List[Tuple[KnowledgeChunk, float]],
        graph_hits: Dict[str, Tuple[KnowledgeChunk, float]],
        w_fts: float,
        w_vector: float,
        w_graph: float,
        k: int = 60
    ) -> Dict[str, Dict[str, Any]]:
        """Reciprocal Rank Fusion (RRF) algorithm."""
        fused: Dict[str, Dict[str, Any]] = {}

        # 1. Process FTS ranks
        for rank, (chunk, score) in enumerate(fts_hits, start=1):
            fused[chunk.id] = {
                "chunk": chunk,
                "rrf_score": w_fts / (k + rank),
                "fts_score": score,
                "vector_score": 0.0,
                "graph_score": 0.0,
            }

        # 2. Process Vector ranks
        for rank, (chunk, score) in enumerate(vector_hits, start=1):
            if chunk.id in fused:
                fused[chunk.id]["rrf_score"] += w_vector / (k + rank)
                fused[chunk.id]["vector_score"] = score
            else:
                fused[chunk.id] = {
                    "chunk": chunk,
                    "rrf_score": w_vector / (k + rank),
                    "fts_score": 0.0,
                    "vector_score": score,
                    "graph_score": 0.0,
                }

        # 3. Process Graph boosts
        for rank, (chunk_id, (chunk, score)) in enumerate(graph_hits.items(), start=1):
            if chunk_id in fused:
                fused[chunk_id]["rrf_score"] += w_graph / (k + rank)
                fused[chunk_id]["graph_score"] = score
            else:
                fused[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": w_graph / (k + rank),
                    "fts_score": 0.0,
                    "vector_score": 0.0,
                    "graph_score": score,
                }

        return fused

    @classmethod
    def _perform_hybrid_check(
        cls,
        query_text: str,
        chunk: KnowledgeChunk,
        fts_score: float,
        vector_score: float,
        graph_score: float
    ) -> HybridVerificationCheck:
        """
        Hybrid Verification Check:
        Verifies concordance across lexical, semantic vector, and relational graph signals.
        """
        fts_matched = fts_score > 0.1
        vector_matched = vector_score > 0.4
        graph_connected = graph_score > 0.0

        modalities_matched = sum([1 for m in [fts_matched, vector_matched, graph_connected] if m])
        concordance_score = round(modalities_matched / 3.0, 2)

        if modalities_matched == 3:
            status = "VERIFIED"
            notes = "Tri-modal consensus: confirmed by exact keyword match, vector semantic closeness, and graph edge connection."
        elif modalities_matched == 2:
            status = "PARTIAL"
            notes = "Dual-modal consensus: confirmed across two search modalities."
        else:
            status = "WEAK"
            notes = "Single-modal match: low cross-modality verification."

        return HybridVerificationCheck(
            fts_matched=fts_matched,
            vector_matched=vector_matched,
            graph_connected=graph_connected,
            fts_score=round(fts_score, 3),
            vector_cosine_score=round(vector_score, 3),
            graph_hop_distance=1 if graph_connected else -1,
            concordance_score=concordance_score,
            verification_status=status,
            verification_notes=notes,
        )

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.models.assets import DocumentAsset
from app.schemas.tutoring import ContextBundle, CitationItem, QueryMetadata
from app.schemas.chunk import KnowledgeChunkRead
from app.services.embedding_service import default_embedding_service
from app.tutoring.router.query_router import RetrievalStrategy

logger = logging.getLogger(__name__)


class MultiStrategyRetrievalOrchestrator:
    """
    Multi-Strategy Retrieval Orchestrator:
    Executes Cross-Lesson, Thematic, Multi-Concept, or Contextual Retrieval,
    followed by Query Expansion, Hybrid Search, Parent-Child Expansion,
    RRF Fusion, and Context Bundle Assembly.
    """

    @classmethod
    def retrieve_context_bundle(
        cls,
        session: Session,
        query_meta: QueryMetadata,
        strategy: RetrievalStrategy,
        document_id: Optional[str] = None,
        topic_title: Optional[str] = None,
        active_page: Optional[int] = None,
        top_k: int = 5
    ) -> ContextBundle:
        resolved_query = query_meta.resolved_query
        entities = query_meta.extracted_entities

        # 1. Query Expansion: Generate sub-query terms and concept expansions
        expanded_terms = set(resolved_query.lower().split())
        for e in entities:
            expanded_terms.add(e.lower())

        # 2. Metadata Filtering & Base Query Construction
        if not document_id:
            return ContextBundle(
                document_id=None,
                topic_title=topic_title or "Subject Lesson",
                resolved_query=resolved_query,
                conversation_history=[],
                student_mastery_context={},
                retrieved_chunks=[],
                related_formulas=[],
                related_tables=[],
                citations=[]
            )

        base_chunk_q = session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id)

        # Apply strategy-specific filtering
        if strategy == "contextual" and active_page:
            # Anchor to active page +/- 1
            base_chunk_q = base_chunk_q.filter(
                KnowledgeChunk.page_number.between(max(1, active_page - 1), active_page + 1)
            )
        elif strategy == "thematic" and topic_title:
            base_chunk_q = base_chunk_q.filter(
                or_(
                    KnowledgeChunk.topic.ilike(f"%{topic_title}%"),
                    KnowledgeChunk.chapter_section.ilike(f"%{topic_title}%"),
                )
            )

        candidate_chunks = base_chunk_q.all()

        # 3. Hybrid Scoring: Lexical Match + Vector Cosine + Graph Linkage
        scored_chunks: List[Dict[str, Any]] = []
        query_vec = default_embedding_service.embed_text(resolved_query)
        import numpy as np
        q_norm = float(np.linalg.norm(query_vec))

        # Check for any chunks lacking stored embeddings and batch embed once
        missing_chunks = [c for c in candidate_chunks if c.embedding is None]
        if missing_chunks:
            missing_contents = [c.content for c in missing_chunks]
            computed_embs = default_embedding_service.embed_batch(missing_contents)
            for c, emb in zip(missing_chunks, computed_embs):
                c.embedding = emb
            try:
                session.commit()
            except Exception as e:
                logger.warning(f"Failed to persist chunk embeddings: {e}")
                session.rollback()

        for chunk in candidate_chunks:
            # Lexical BM25 approximation
            text_lower = (chunk.content + " " + (chunk.search_text or "")).lower()
            lexical_hits = sum(1 for term in expanded_terms if term in text_lower)
            lexical_score = min(lexical_hits * 0.2, 1.0)

            # Vector cosine similarity using stored embedding
            chunk_vec = chunk.embedding
            if chunk_vec is not None:
                c_vec_np = np.array(chunk_vec, dtype=np.float32)
                c_norm = float(np.linalg.norm(c_vec_np))
                cosine_score = float(np.dot(query_vec, c_vec_np) / (q_norm * c_norm)) if q_norm > 0 and c_norm > 0 else 0.0
            else:
                cosine_score = 0.0

            # Strategy weighted score
            if strategy == "multi_concept":
                entity_overlap = sum(1 for e in entities if e.lower() in text_lower)
                final_score = (0.3 * lexical_score) + (0.4 * cosine_score) + (0.3 * (entity_overlap / max(1, len(entities))))
            elif strategy == "thematic":
                final_score = (0.25 * lexical_score) + (0.65 * cosine_score) + (0.1 * chunk.confidence)
            else:
                final_score = (0.4 * lexical_score) + (0.6 * cosine_score)

            scored_chunks.append({
                "chunk": chunk,
                "score": final_score,
                "lexical_score": lexical_score,
                "cosine_score": cosine_score,
            })

        # Sort by final score descending
        ranked = sorted(scored_chunks, key=lambda x: x["score"], reverse=True)[:top_k]

        # 4. Parent + Child Expansion
        selected_chunk_ids = {item["chunk"].id for item in ranked}
        expanded_chunks: List[KnowledgeChunk] = [item["chunk"] for item in ranked]

        for item in ranked[:2]:
            parent_id = item["chunk"].parent_id
            if parent_id and parent_id not in selected_chunk_ids:
                parent_chunk = session.query(KnowledgeChunk).filter(KnowledgeChunk.id == parent_id).first()
                if parent_chunk:
                    expanded_chunks.append(parent_chunk)
                    selected_chunk_ids.add(parent_id)

        # 5. Extract Related Formulas & Tables from Assets
        related_formulas = []
        related_tables = []
        pages_hit = list({c.page_number for c in expanded_chunks})
        if document_id and pages_hit:
            assets = session.query(DocumentAsset).filter(
                DocumentAsset.document_id == document_id,
                DocumentAsset.page_number.in_(pages_hit)
            ).all()

            for a in assets:
                if a.asset_type == "formula" and a.latex:
                    related_formulas.append(a.latex)
                elif a.asset_type == "table" and a.markdown:
                    related_tables.append(a.markdown)

        # 6. Build Citations & Context Bundle
        citations: List[CitationItem] = []
        chunk_reads: List[KnowledgeChunkRead] = []

        for c in expanded_chunks:
            chunk_read = KnowledgeChunkRead.model_validate(c)
            chunk_reads.append(chunk_read)

            snippet = c.content[:160].replace("\n", " ") + "..."
            citations.append(
                CitationItem(
                    chunk_id=c.id,
                    page_number=c.page_number,
                    chapter_section=c.chapter_section,
                    snippet=snippet,
                    source_uri=c.source_uri,
                    confidence=c.confidence,
                )
            )

        return ContextBundle(
            document_id=document_id,
            topic_title=topic_title or "Subject Lesson",
            resolved_query=resolved_query,
            conversation_history=[],
            student_mastery_context={},
            retrieved_chunks=chunk_reads,
            related_formulas=related_formulas[:5],
            related_tables=related_tables[:3],
            citations=citations,
        )

import re
import logging
from typing import List, Dict, Any, Optional
import numpy as np
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
        top_k: int = 5,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> ContextBundle:
        resolved_query = query_meta.resolved_query
        entities = query_meta.extracted_entities

        # 1. Query Expansion: Generate informative sub-query terms without grammatical stopwords
        _STOPWORDS = {
            "what", "are", "the", "of", "in", "is", "a", "an", "and", "or", "to", "for",
            "with", "on", "at", "by", "from", "this", "that", "these", "those", "can",
            "you", "me", "how", "why", "which", "do", "does", "did", "tell", "explain",
            "give", "please", "about"
        }
        clean_tokens = [w.strip("?,.:;\"'()!") for w in resolved_query.lower().split()]
        informative_terms = [w for w in clean_tokens if len(w) > 2 and w not in _STOPWORDS]
        expanded_terms = set(informative_terms)
        for term in informative_terms:
            if term.endswith("s") and len(term) > 3:
                expanded_terms.add(term[:-1])
            elif not term.endswith("s"):
                expanded_terms.add(term + "s")
        for e in entities:
            e_clean = e.lower().strip()
            if e_clean and e_clean not in _STOPWORDS:
                expanded_terms.add(e_clean)

        # Check if query is an overview / main topics / summary / whole material inquiry
        is_global_scope = getattr(query_meta, "query_scope", None) == "global_material"
        is_overview_query = (
            query_meta.intent == "SUMMARY"
            or is_global_scope
            or any(w in resolved_query.lower() for w in ["main topic", "topics", "summary", "overview", "syllabus", "chapters", "what is this document", "what does this cover", "roadmap", "curriculum", "whole material", "from this material", "cover all"])
        )

        # 2. Metadata Filtering & Base Query Construction
        if not document_id:
            return ContextBundle(
                document_id=None,
                topic_title=topic_title or "Subject Lesson",
                resolved_query=resolved_query,
                conversation_history=conversation_history or [],
                student_mastery_context={},
                retrieved_chunks=[],
                curriculum_topics=[],
                related_formulas=[],
                related_tables=[],
                citations=[]
            )

        # Extract curriculum topics for document/session
        curriculum_topic_titles: List[str] = []
        from app.models.session import CurriculumTopic
        db_topics = (
            session.query(CurriculumTopic)
            .filter(CurriculumTopic.document_id == document_id)
            .order_by(CurriculumTopic.order_index)
            .all()
        )
        seen_t = set()
        for t in db_topics:
            if t.title and t.title not in seen_t:
                seen_t.add(t.title)
                summary_text = f" ({t.summary})" if t.summary and "Page" in t.summary else ""
                curriculum_topic_titles.append(f"{t.title}{summary_text}")

        base_chunk_q = session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id)

        # Apply strategy-specific filtering (with resilient fallback so queries never drop to 0 candidates)
        if strategy == "contextual" and active_page and not is_overview_query:
            # Anchor to active page +/- 1
            ctx_q = base_chunk_q.filter(
                KnowledgeChunk.page_number.between(max(1, active_page - 1), active_page + 1)
            )
            candidate_chunks = ctx_q.all()
            if not candidate_chunks:
                candidate_chunks = base_chunk_q.all()
        elif strategy == "thematic" and topic_title and not is_overview_query:
            theme_q = base_chunk_q.filter(
                or_(
                    KnowledgeChunk.topic.ilike(f"%{topic_title}%"),
                    KnowledgeChunk.chapter_section.ilike(f"%{topic_title}%"),
                )
            )
            candidate_chunks = theme_q.all()
            # Resilient fallback: If the explicit topic filter matches 0 chunks (e.g. question is from another chapter),
            # fall back to all document chunks so hybrid semantic vector + lexical search can find the exact content
            if not candidate_chunks:
                candidate_chunks = base_chunk_q.all()
        else:
            candidate_chunks = base_chunk_q.all()

        # 3. Hybrid Scoring: Lexical Match + Vector Cosine + Graph Linkage
        scored_chunks: List[Dict[str, Any]] = []
        query_vec = default_embedding_service.embed_text(resolved_query)
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

        # Prepare topic terms for soft affinity scoring
        topic_terms = set(re.findall(r"\w+", (topic_title or "").lower())) if topic_title else set()
        topic_terms = {t for t in topic_terms if len(t) > 3}

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

            # Topic affinity bonus (soft boost rather than destructive filtering)
            chunk_topic = (chunk.topic or "").lower()
            chunk_section = (chunk.chapter_section or "").lower()
            has_topic_match = bool(topic_title and (
                topic_title.lower() in chunk_topic
                or topic_title.lower() in chunk_section
                or any(t in chunk_topic or t in chunk_section for t in topic_terms)
            ))
            topic_affinity_bonus = 0.2 if (has_topic_match and not is_global_scope) else 0.0

            # Figure boost: if query asks for a specific figure, prioritize chunks containing that figure reference
            ref_fig_bonus = 0.0
            if getattr(query_meta, "referenced_figure", None):
                fig_name = query_meta.referenced_figure.lower()
                fig_num = re.sub(r"[^\d.-]", "", fig_name)
                if fig_num:
                    f_hyphen = fig_num.replace(".", "-")
                    f_dot = fig_num.replace("-", ".")
                    fig_variants = [
                        f"figure {f_hyphen}",
                        f"figure {f_dot}",
                        f"fig. {f_hyphen}",
                        f"fig. {f_dot}",
                        f"fig {f_hyphen}",
                        f"fig {f_dot}",
                        f"figure-{f_hyphen}",
                        f"figure-{f_dot}",
                    ]
                    if any(v in text_lower for v in fig_variants):
                        ref_fig_bonus = 2.0

            # Strategy weighted score
            if strategy == "multi_concept":
                entity_overlap = sum(1 for e in entities if e.lower() in text_lower)
                final_score = (0.3 * lexical_score) + (0.4 * cosine_score) + (0.3 * (entity_overlap / max(1, len(entities)))) + topic_affinity_bonus + ref_fig_bonus
            elif strategy == "thematic":
                final_score = (0.25 * lexical_score) + (0.55 * cosine_score) + (0.1 * chunk.confidence) + topic_affinity_bonus + ref_fig_bonus
            else:
                final_score = (0.4 * lexical_score) + (0.6 * cosine_score) + topic_affinity_bonus + ref_fig_bonus

            scored_chunks.append({
                "chunk": chunk,
                "score": final_score,
                "lexical_score": lexical_score,
                "cosine_score": cosine_score,
            })

        # Sort by final score descending with diverse topic coverage if global material scope
        effective_top_k = max(top_k, 10) if is_global_scope else top_k
        if is_global_scope:
            selected = []
            seen_topics = set()
            sorted_all = sorted(scored_chunks, key=lambda x: x["score"], reverse=True)
            for sc in sorted_all:
                t_key = (sc["chunk"].topic or sc["chunk"].chapter_section or f"page_{sc['chunk'].page_number}").strip().lower()
                if t_key and t_key not in seen_topics:
                    seen_topics.add(t_key)
                    selected.append(sc)
                    if len(selected) >= effective_top_k:
                        break
            if len(selected) < effective_top_k:
                for sc in sorted_all:
                    if sc not in selected:
                        selected.append(sc)
                        if len(selected) >= effective_top_k:
                            break
            ranked = selected
        else:
            ranked = sorted(scored_chunks, key=lambda x: x["score"], reverse=True)[:top_k]

        # 4. Parent + Child Expansion & Exact Page Guarantee
        # If an active page was specified (e.g. from user query "page 5"), guarantee all chunks from that page are strictly prioritized at index 0
        exact_page_chunks = []
        if active_page:
            exact_page_chunks = session.query(KnowledgeChunk).filter(
                KnowledgeChunk.document_id == document_id,
                KnowledgeChunk.page_number == active_page
            ).order_by(KnowledgeChunk.chunk_index).all()
            
            page_chunk_ids = {epc.id for epc in exact_page_chunks}
            other_chunks = [item["chunk"] for item in ranked if item["chunk"].id not in page_chunk_ids]
            expanded_chunks: List[KnowledgeChunk] = list(exact_page_chunks) + other_chunks
            selected_chunk_ids = {c.id for c in expanded_chunks}
        else:
            selected_chunk_ids = {item["chunk"].id for item in ranked}
            expanded_chunks: List[KnowledgeChunk] = [item["chunk"] for item in ranked]

        for item in ranked[:2]:
            parent_id = item["chunk"].parent_id
            if parent_id and parent_id not in selected_chunk_ids:
                parent_chunk = session.query(KnowledgeChunk).filter(KnowledgeChunk.id == parent_id).first()
                if parent_chunk:
                    expanded_chunks.append(parent_chunk)
                    selected_chunk_ids.add(parent_id)

        # 5. Extract Related Formulas, Tables, & Figures from Assets
        related_formulas = []
        related_tables = []
        related_figures = []
        pages_hit = list({c.page_number for c in expanded_chunks})
        if active_page and active_page not in pages_hit:
            pages_hit.append(active_page)

        # 5b. Extract verified figure captions from target page chunks
        fig_cap_pattern = re.compile(r"(?:Figure|Fig\.?)\s*(\d+(?:[-.]\d+)*)\s*[:.-]?\s*([^\n\r]+)", re.IGNORECASE)
        target_figure_chunks = exact_page_chunks if active_page else expanded_chunks
        for c in target_figure_chunks:
            for match in fig_cap_pattern.finditer(c.content):
                fig_num = match.group(1).replace(".", "-")
                fig_title = match.group(2).strip()
                # Exclude cross-references like "Figure 1.4 for a graphical representation"
                if not any(fig_title.lower().startswith(prefix) for prefix in ["for a", "shows", "illustrates", "see", "refer"]):
                    fig_label = f"Figure {fig_num}: {fig_title}"
                    if fig_label not in related_figures:
                        related_figures.append(fig_label)

        # If a specific table was referenced (e.g. "Table 1.2" or "table"), look for it in DocumentAsset
        if query_meta.referenced_table and document_id:
            ref_tbl = query_meta.referenced_table.strip()
            table_assets_q = session.query(DocumentAsset).filter(
                DocumentAsset.document_id == document_id,
                DocumentAsset.asset_type == "table",
            )
            if ref_tbl.lower() != "table":
                table_assets_q = table_assets_q.filter(
                    or_(
                        DocumentAsset.caption.ilike(f"%{ref_tbl}%"),
                        DocumentAsset.markdown.ilike(f"%{ref_tbl}%"),
                    )
                )
            for ta in table_assets_q.limit(5).all():
                if ta.markdown and ta.markdown not in related_tables:
                    related_tables.append(ta.markdown)
                if ta.page_number not in pages_hit:
                    pages_hit.append(ta.page_number)
                    tbl_chunks = session.query(KnowledgeChunk).filter(
                        KnowledgeChunk.document_id == document_id,
                        KnowledgeChunk.page_number == ta.page_number
                    ).all()
                    for tc in tbl_chunks:
                        if tc.id not in selected_chunk_ids:
                            expanded_chunks.append(tc)
                            selected_chunk_ids.add(tc.id)

        if document_id and pages_hit:
            assets = session.query(DocumentAsset).filter(
                DocumentAsset.document_id == document_id,
                DocumentAsset.page_number.in_(pages_hit)
            ).all()

            for a in assets:
                if a.asset_type == "formula" and a.latex and a.latex not in related_formulas:
                    related_formulas.append(a.latex)
                elif a.asset_type == "table" and a.markdown and a.markdown not in related_tables:
                    related_tables.append(a.markdown)
                elif a.asset_type == "figure" and a.caption and a.caption not in related_figures:
                    if not active_page or a.page_number == active_page:
                        related_figures.append(a.caption)

        # For overview / main topics queries, guarantee key introductory/topic chunks across the document
        if is_overview_query and document_id and candidate_chunks:
            early_chunks = session.query(KnowledgeChunk).filter(
                KnowledgeChunk.document_id == document_id
            ).order_by(KnowledgeChunk.page_number, KnowledgeChunk.chunk_index).limit(6).all()
            for ec in early_chunks:
                if ec.id not in selected_chunk_ids and len(expanded_chunks) < 8:
                    expanded_chunks.append(ec)
                    selected_chunk_ids.add(ec.id)

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

        # 7. Check for requested but missing tables or figures
        missing_table_requested = False
        requested_table_name = None
        ref_table = getattr(query_meta, "referenced_table", None)
        raw_q_lower = (query_meta.raw_query or "").lower()
        if ref_table or ("table" in raw_q_lower and any(w in raw_q_lower for w in ["solve", "explain", "show", "what is", "where is", "fill", "calculate", "find"])):
            requested_table_name = ref_table or "table"
            has_table_in_chunks = any("table" in c.content.lower() or "|" in c.content for c in expanded_chunks)
            if not related_tables and not has_table_in_chunks:
                missing_table_requested = True

        missing_figure_requested = False
        requested_figure_name = None
        ref_fig = getattr(query_meta, "referenced_figure", None)
        if ref_fig or any(w in raw_q_lower for w in ["figure", "diagram", "image", "drawing", "picture", "illustration"]):
            requested_figure_name = ref_fig or "figure/image"
            has_fig_in_chunks = any(
                any(k in c.content.lower() for k in ["figure", "fig.", "diagram", "image"])
                for c in expanded_chunks
            )
            if not related_figures and not has_fig_in_chunks:
                missing_figure_requested = True

        return ContextBundle(
            document_id=document_id,
            topic_title=topic_title or "Subject Lesson",
            resolved_query=resolved_query,
            conversation_history=conversation_history or [],
            student_mastery_context={},
            retrieved_chunks=chunk_reads,
            curriculum_topics=curriculum_topic_titles,
            related_formulas=related_formulas[:5],
            related_tables=related_tables[:3],
            related_figures=related_figures[:3],
            citations=citations,
            missing_table_requested=missing_table_requested,
            missing_figure_requested=missing_figure_requested,
            requested_table_name=requested_table_name,
            requested_figure_name=requested_figure_name,
        )

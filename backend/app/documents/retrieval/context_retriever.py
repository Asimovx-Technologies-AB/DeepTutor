"""
Context Retriever — Hybrid search retrieval for document Q&A.

Separated from the old monolithic doc_processor.py.  Provides
source-type-aware boosting, page-targeted retrieval, and knowledge-box
weighted scoring.
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.documents.models import KNOWLEDGE_BOX_WEIGHTS, KnowledgeBoxType

logger = logging.getLogger(__name__)


class ContextRetriever:
    """Hybrid search retrieval over indexed document chunks."""

    # ── Main retrieval ────────────────────────────────────────────────────

    def retrieve(
        self,
        doc_id: str,
        query: str,
        top_k: int = 6,
        session_id: Optional[str] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Retrieves top-k relevant chunks using hybrid search.

        Combines:
        - Dense vector search (pgvector cosine)
        - Sparse BM25 search (tsvector)
        - Metadata filtering (page, source_type, knowledge_box)
        - Knowledge-box-aware weight boosting

        Returns:
            (formatted_context, status_note, metadata)
        """
        query_lower = query.lower().strip()

        # Detect query intent for source-type boosting
        table_boost = self._detect_table_intent(query_lower)
        image_boost = self._detect_image_intent(query_lower)
        target_page = self._detect_target_page(query_lower)

        # Search via PostgreSQL hybrid store
        raw_results = self._search_pg_fts(
            doc_id=doc_id,
            query=query,
            session_id=session_id,
            top_k=top_k * 2,  # Fetch more to allow reranking
        )

        # Rerank with knowledge-box awareness
        scored = self._rerank(
            raw_results, query_lower,
            table_boost=table_boost,
            image_boost=image_boost,
            target_page=target_page,
        )

        # Take top-k
        selected = scored[:top_k]

        # Format output
        context_blocks = []
        for item in selected:
            box_type = item.get("metadata", {}).get("knowledge_box", "text")
            page = item.get("page", "?")
            content = item.get("content", item.get("chunk_text", "")).strip()
            context_blocks.append(
                f"[Page {page} | Type: {box_type}]\n{content}"
            )

        formatted_context = "\n\n".join(context_blocks)
        status_note = ""

        metadata = {
            "doc_id": doc_id,
            "retrieved_count": len(selected),
            "source_types_retrieved": list(set(
                r.get("source_type", "text") for r in selected
            )),
            "knowledge_boxes": list(set(
                r.get("metadata", {}).get("knowledge_box", "paragraph")
                for r in selected
            )),
        }

        return formatted_context, status_note, metadata

    # ── Document text retrieval ───────────────────────────────────────────

    def get_document_text(
        self,
        doc_id: str,
        max_chars: int = 12000,
        session_id: Optional[str] = None,
    ) -> str:
        """Retrieves assembled text of the document for topic extraction."""
        results = self._search_pg_fts(
            doc_id=doc_id,
            query="*",
            session_id=session_id,
            top_k=30,
        )

        texts = []
        for r in results:
            content = r.get("content", r.get("chunk_text", ""))
            # Skip figure/diagram captions for text assembly
            box_type = r.get("metadata", {}).get("knowledge_box", "")
            if box_type not in ("figure", "diagram"):
                texts.append(content)

        return "\n\n".join(texts)[:max_chars]

    # ── PostgreSQL search ─────────────────────────────────────────────────

    @staticmethod
    def _search_pg_fts(
        doc_id: str,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 12,
    ) -> List[Dict[str, Any]]:
        """Searches via the existing PgFTSStore or SQLite FTS."""
        target = session_id or doc_id

        # Try PostgreSQL hybrid search first
        try:
            from app.rag.pg_fts_store import pg_fts_store

            results = pg_fts_store.hybrid_search(
                session_id=target,
                query=query,
                limit=top_k,
            )
            if results:
                return results
        except Exception:
            pass

        # Fallback to SQLite FTS
        try:
            from app.rag.sqlite_fts_store import get_session_store

            store = get_session_store(target)
            matches = store.search(doc_id=doc_id, query=query, limit=top_k)
            return matches or []
        except Exception as exc:
            logger.debug("[ContextRetriever] FTS search error: %s", exc)

        return []

    # ── Reranking with knowledge-box awareness ────────────────────────────

    @staticmethod
    def _rerank(
        results: List[Dict[str, Any]],
        query_lower: str,
        table_boost: bool = False,
        image_boost: bool = False,
        target_page: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reranks search results with knowledge-box weight boosting."""
        query_words = set(re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?", query_lower))

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in results:
            score = item.get("score", 0.0)
            content_lower = (
                item.get("content", item.get("chunk_text", ""))
            ).lower()
            metadata = item.get("metadata", {})
            source_type = item.get("source_type", "text")
            box_type = metadata.get("knowledge_box", "paragraph")

            # Knowledge box weight
            try:
                kb = KnowledgeBoxType(box_type)
                score *= KNOWLEDGE_BOX_WEIGHTS.get(kb, 1.0)
            except ValueError:
                pass

            # Page targeting
            page = item.get("page", 0)
            if target_page is not None and page == target_page:
                score += 60.0

            # Keyword matching
            for word in query_words:
                count = content_lower.count(word)
                if count > 0:
                    score += 1.0 + min(count * 0.5, 3.0)

            # Source-type boosting
            if table_boost and source_type == "table":
                score = (score + 15.0) * 3.0
            elif image_boost and source_type in ("image_caption",):
                score = (score + 15.0) * 3.0

            # Chunk weight from metadata
            chunk_weight = metadata.get("weight", 1.0)
            if isinstance(chunk_weight, (int, float)):
                score *= chunk_weight

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    # ── Intent detection helpers ──────────────────────────────────────────

    @staticmethod
    def _detect_table_intent(query_lower: str) -> bool:
        table_keywords = {
            "table", "value", "compare", "how many", "number", "data",
            "columns", "rows", "statistic", "percent", "metric", "versus", "vs",
        }
        return any(
            re.search(rf"\b{re.escape(kw)}\b", query_lower)
            for kw in table_keywords
        )

    @staticmethod
    def _detect_image_intent(query_lower: str) -> bool:
        image_keywords = {
            "image", "figure", "diagram", "photo", "picture",
            "illustration", "graphic", "chart", "visual", "draw",
        }
        return any(
            re.search(rf"\b{re.escape(kw)}\b", query_lower)
            for kw in image_keywords
        )

    @staticmethod
    def _detect_target_page(query_lower: str) -> Optional[int]:
        match = re.search(
            r"\b(?:page\s*number|pagenumber|page|pg|p\.?)\s*(?:no\.?)?\s*(\d+)\b",
            query_lower,
        )
        return int(match.group(1)) if match else None

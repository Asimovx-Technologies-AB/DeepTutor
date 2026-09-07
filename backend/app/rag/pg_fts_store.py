"""
PostgreSQL + pgvector Full-Text & Hybrid Search Store for DeepTutor.
Drop-in replacement for SQLiteFTSStore utilizing Azure Database for PostgreSQL (Flexible Server).
Provides native tsvector BM25-style ranking, pgvector cosine distance, and RRF hybrid fusion.
"""
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger(__name__)


def _sanitize_query(query: str) -> str:
    """Sanitize query text for PostgreSQL plainto_tsquery."""
    if not query:
        return ""
    # Strip null bytes and non-printable characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", query).strip()
    return cleaned


def _rrf(dense: List[Dict[str, Any]], sparse: List[Dict[str, Any]], k: int = 60) -> List[Dict[str, Any]]:
    """Weighted Reciprocal Rank Fusion of dense and sparse result lists."""
    scores: Dict[str, float] = {}
    chunk_map: Dict[str, Dict[str, Any]] = {}

    for rank, item in enumerate(dense):
        cid = str(item["id"])
        scores[cid] = scores.get(cid, 0.0) + (0.7 / (k + rank + 1))
        chunk_map[cid] = item

    for rank, item in enumerate(sparse):
        cid = str(item["id"])
        scores[cid] = scores.get(cid, 0.0) + (0.3 / (k + rank + 1))
        if cid not in chunk_map:
            chunk_map[cid] = item

    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    results = []
    for cid in sorted_ids:
        chunk = dict(chunk_map[cid])
        chunk["score"] = round(scores[cid], 4)
        results.append(chunk)
    return results


class PgFTSStore:
    """PostgreSQL-backed search store replacing SQLiteFTSStore."""

    def __init__(self):
        self.settings = get_settings()
        self.engine = engine
        self.dimensions = self.settings.PGVECTOR_DIMENSIONS

    def _vector_literal(self, vec: List[float]) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    def index_chunks(
        self,
        session_id: str,
        doc_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Batch index semantic chunks into document_chunks table with session scoping."""
        if not chunks:
            return 0

        records = []
        zero_vec = self._vector_literal([0.0] * self.dimensions)

        for i, chunk in enumerate(chunks):
            content = str(chunk.get("content", "")).strip()
            if not content:
                continue

            chunk_id = str(chunk.get("chunk_id", i))
            page = int(chunk.get("page", 1))
            source_type = str(chunk.get("source_type", "text"))

            # Deterministic UUID based on session, doc, and chunk_id
            pk_seed = f"{session_id}_{chunk_id}_{doc_id}"
            pk = str(uuid.uuid5(uuid.NAMESPACE_DNS, pk_seed))

            vec_literal = (
                self._vector_literal(embeddings[i])
                if embeddings and i < len(embeddings) and len(embeddings[i]) == self.dimensions
                else zero_vec
            )

            metadata = {
                "session_id": session_id,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "page": page,
                "source_type": source_type,
                "user_id": user_id or "",
            }

            records.append({
                "id": pk,
                "session_id": str(session_id),
                "topic_id": str(doc_id),
                "doc_id": str(doc_id),
                "chunk_id": chunk_id,
                "page": page,
                "source_type": source_type,
                "chunk_text": content,
                "metadata": json.dumps(metadata),
                "embedding": vec_literal,
            })

        if not records:
            return 0

        statement = text("""
            INSERT INTO document_chunks (
                id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                chunk_text, metadata, embedding, created_at, updated_at
            )
            VALUES (
                CAST(:id AS UUID), :session_id, :topic_id, :doc_id, :chunk_id, :page, :source_type,
                :chunk_text, CAST(:metadata AS jsonb), CAST(:embedding AS vector), now(), now()
            )
            ON CONFLICT (id) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                updated_at = now();
        """)

        with self.engine.begin() as conn:
            conn.execute(statement, records)

        return len(records)

    def search_bm25(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Executes full-text BM25 search using PostgreSQL tsvector and ts_rank_cd."""
        clean_q = _sanitize_query(query)
        if not clean_q:
            return []

        type_filter = "AND source_type = :source_type" if source_type else ""

        statement = text(f"""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                   ts_rank_cd(search_vector, plainto_tsquery('english', :query)) AS score
            FROM document_chunks
            WHERE session_id = :session_id
              {type_filter}
              AND search_vector @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :limit
        """)

        params = {
            "session_id": str(session_id),
            "query": clean_q,
            "limit": limit,
        }
        if source_type:
            params["source_type"] = source_type

        with self.engine.connect() as conn:
            rows = conn.execute(statement, params).mappings().fetchall()

        return [dict(r) for r in rows]

    def search_dense(
        self,
        session_id: str,
        query_embedding: List[float],
        limit: int = 5,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Executes pgvector cosine similarity search."""
        if len(query_embedding) != self.dimensions:
            return []

        vec_str = self._vector_literal(query_embedding)
        statement = text("""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM document_chunks
            WHERE session_id = :session_id
              AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_score
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        with self.engine.connect() as conn:
            # Set HNSW search ef parameter if applicable
            try:
                conn.execute(text(f"SET LOCAL hnsw.ef_search = {int(self.settings.PGVECTOR_HNSW_EF_SEARCH)}"))
            except Exception:
                pass
            rows = conn.execute(statement, {
                "session_id": str(session_id),
                "embedding": vec_str,
                "min_score": min_score,
                "limit": limit,
            }).mappings().fetchall()

        return [dict(r) for r in rows]

    def search_hybrid(
        self,
        session_id: str,
        query: str,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Combines BM25 tsvector and dense pgvector retrieval via RRF."""
        sparse = self.search_bm25(session_id, query, limit=limit * 2, source_type=source_type)
        if not query_embedding or len(query_embedding) != self.dimensions:
            return sparse[:limit]

        dense = self.search_dense(session_id, query_embedding, limit=limit * 2)
        if not dense and not sparse:
            return []
        if not dense:
            return sparse[:limit]
        if not sparse:
            return dense[:limit]

        fused = _rrf(dense, sparse)
        return fused[:limit]

    def get_chunks_by_page(self, session_id: str, page: int) -> List[Dict[str, Any]]:
        """Retrieves all chunks on a given page within a session."""
        statement = text("""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE session_id = :session_id AND page = :page
            ORDER BY chunk_id
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(statement, {"session_id": str(session_id), "page": int(page)}).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_chunks_by_pages(self, session_id: str, pages: List[int]) -> List[Dict[str, Any]]:
        """Retrieves all chunks matching any of the given page numbers."""
        if not pages:
            return []
        statement = text("""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE session_id = :session_id AND page = ANY(:pages)
            ORDER BY page, chunk_id
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(statement, {"session_id": str(session_id), "pages": [int(p) for p in pages]}).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_all_chunks(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves all indexed chunks for a session up to limit."""
        statement = text("""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE session_id = :session_id
            ORDER BY page, chunk_id
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(statement, {"session_id": str(session_id), "limit": int(limit)}).mappings().fetchall()
        return [dict(r) for r in rows]

    def delete_session_document(self, session_id: str, doc_id: str) -> int:
        """Deletes all chunks for a document within a session."""
        statement = text("""
            DELETE FROM document_chunks
            WHERE session_id = :session_id AND (doc_id = :doc_id OR topic_id = :doc_id)
        """)
        with self.engine.begin() as conn:
            res = conn.execute(statement, {"session_id": str(session_id), "doc_id": str(doc_id)})
            return res.rowcount

    def delete_session_chunks(self, session_id: str) -> int:
        """Deletes all chunks belonging to a session."""
        statement = text("DELETE FROM document_chunks WHERE session_id = :session_id")
        with self.engine.begin() as conn:
            res = conn.execute(statement, {"session_id": str(session_id)})
            return res.rowcount

    def count(self, session_id: str) -> int:
        statement = text("SELECT count(*) FROM document_chunks WHERE session_id = :session_id")
        with self.engine.connect() as conn:
            return int(conn.execute(statement, {"session_id": str(session_id)}).scalar() or 0)


# Global singleton instance
pg_fts_store = PgFTSStore()

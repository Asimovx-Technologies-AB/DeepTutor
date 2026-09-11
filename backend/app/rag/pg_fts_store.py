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

        if self.engine.dialect.name == "sqlite":
            statement = text("""
                INSERT INTO document_chunks (
                    id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                    chunk_text, metadata, embedding, created_at, updated_at
                )
                VALUES (
                    :id, :session_id, :topic_id, :doc_id, :chunk_id, :page, :source_type,
                    :chunk_text, :metadata, :embedding, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (id) DO UPDATE SET
                    chunk_text = excluded.chunk_text,
                    metadata = excluded.metadata,
                    embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP;
            """)
        else:
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

        try:
            with self.engine.begin() as conn:
                conn.execute(statement, records)
        except Exception as e:
            logger.warning(f"[PgFTSStore] index_chunks notice: {e}")

        return len(records)

    def clone_document_chunks_to_session(
        self,
        target_session_id: str,
        source_doc_id: Optional[str] = None,
        source_session_id: Optional[str] = None,
        doc_hash: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Clones all document chunks from a source doc/session into the target session.
        Uses a bulk INSERT ... SELECT statement in PostgreSQL with deterministic UUIDv5
        keys to guarantee idempotency via ON CONFLICT (id) DO NOTHING.
        """
        if not target_session_id:
            return 0

        target_sid = str(target_session_id)
        conditions = []
        params: Dict[str, Any] = {
            "target_session_id": target_sid,
            "dns_ns": str(uuid.NAMESPACE_DNS),
        }

        if source_doc_id:
            conditions.append("doc_id = :source_doc_id OR topic_id = :source_doc_id OR session_id = :source_doc_id")
            params["source_doc_id"] = str(source_doc_id)
        if source_session_id and source_session_id != target_sid:
            conditions.append("session_id = :source_session_id")
            params["source_session_id"] = str(source_session_id)
        if doc_hash:
            if self.engine.dialect.name == "sqlite":
                conditions.append("doc_id IN (SELECT id FROM documents WHERE doc_hash = :doc_hash)")
                conditions.append("session_id IN (SELECT session_id FROM session_documents WHERE doc_hash = :doc_hash)")
            else:
                conditions.append("doc_id IN (SELECT id::text FROM documents WHERE doc_hash = :doc_hash)")
                conditions.append("session_id IN (SELECT session_id FROM session_documents WHERE doc_hash = :doc_hash)")
            params["doc_hash"] = str(doc_hash)

        if not conditions:
            return 0

        where_clause = " OR ".join(f"({c})" for c in conditions)

        if self.engine.dialect.name != "sqlite":
            # PostgreSQL: Execute single bulk SQL statement
            bulk_stmt = text(f"""
                INSERT INTO document_chunks (
                    id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                    chunk_text, metadata, embedding, created_at, updated_at
                )
                SELECT
                    uuid_generate_v5(CAST(:dns_ns AS uuid), :target_session_id || '_' || chunk_id || '_' || doc_id),
                    :target_session_id,
                    topic_id,
                    doc_id,
                    chunk_id,
                    page,
                    source_type,
                    chunk_text,
                    metadata || jsonb_build_object('session_id', :target_session_id),
                    embedding,
                    now(),
                    now()
                FROM document_chunks
                WHERE ({where_clause})
                  AND session_id != :target_session_id
                ON CONFLICT (id) DO NOTHING;
            """)
            try:
                with self.engine.begin() as conn:
                    conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                    res = conn.execute(bulk_stmt, params)
                    return res.rowcount if res.rowcount is not None and res.rowcount >= 0 else 0
            except Exception as pg_err:
                logger.warning(f"[PgFTSStore] Bulk SQL clone error, falling back to python batch: {pg_err}")

        # Fallback / SQLite path
        fetch_stmt = text(f"""
            SELECT DISTINCT doc_id, chunk_id, page, source_type, chunk_text, metadata, embedding
            FROM document_chunks
            WHERE ({where_clause})
              AND session_id != :target_session_id
        """)

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(fetch_stmt, params).mappings().fetchall()

            if not rows:
                return 0

            records = []
            zero_vec = self._vector_literal([0.0] * self.dimensions)

            for r in rows:
                doc_id_val = str(r.get("doc_id") or source_doc_id or "")
                chunk_id_val = str(r.get("chunk_id") or "")
                page_val = int(r.get("page") or 1)
                source_type_val = str(r.get("source_type") or "text")
                chunk_text_val = str(r.get("chunk_text") or "")

                pk_seed = f"{target_sid}_{chunk_id_val}_{doc_id_val}"
                pk = str(uuid.uuid5(uuid.NAMESPACE_DNS, pk_seed))

                meta = {}
                try:
                    meta_raw = r.get("metadata")
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else dict(meta_raw or {})
                except Exception:
                    meta = {}
                meta["session_id"] = target_sid
                if user_id:
                    meta["user_id"] = user_id

                emb_val = r.get("embedding")
                if not emb_val:
                    emb_val = zero_vec
                elif not isinstance(emb_val, str):
                    emb_val = str(emb_val)

                records.append({
                    "id": pk,
                    "session_id": target_sid,
                    "topic_id": doc_id_val,
                    "doc_id": doc_id_val,
                    "chunk_id": chunk_id_val,
                    "page": page_val,
                    "source_type": source_type_val,
                    "chunk_text": chunk_text_val,
                    "metadata": json.dumps(meta),
                    "embedding": emb_val,
                })

            if not records:
                return 0

            if self.engine.dialect.name == "sqlite":
                insert_stmt = text("""
                    INSERT OR IGNORE INTO document_chunks (
                        id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                        chunk_text, metadata, embedding, created_at, updated_at
                    )
                    VALUES (
                        :id, :session_id, :topic_id, :doc_id, :chunk_id, :page, :source_type,
                        :chunk_text, :metadata, :embedding, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    );
                """)
            else:
                insert_stmt = text("""
                    INSERT INTO document_chunks (
                        id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                        chunk_text, metadata, embedding, created_at, updated_at
                    )
                    VALUES (
                        CAST(:id AS UUID), :session_id, :topic_id, :doc_id, :chunk_id, :page, :source_type,
                        :chunk_text, CAST(:metadata AS jsonb), CAST(:embedding AS vector), now(), now()
                    )
                    ON CONFLICT (id) DO NOTHING;
                """)

            with self.engine.begin() as conn:
                res = conn.execute(insert_stmt, records)
                return res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(records)
        except Exception as e:
            logger.warning(f"[PgFTSStore] clone_document_chunks_to_session notice: {e}")
            return 0

    def search_chunks(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Alias for search_bm25 for backward-compatibility with study plan & generator services."""
        return self.search_bm25(session_id=session_id, query=query, limit=limit, source_type=source_type)

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

        if self.engine.dialect.name == "sqlite":
            terms = [clean_q]
            words = [w for w in re.findall(r"[a-zA-Z0-9\.]+", clean_q) if len(w) > 1]
            for w in words:
                if w.lower() not in terms:
                    terms.append(w)

            tbl_label_match = re.search(r"\b(?:table|tbl|figure|fig)\s*(\d+(?:\.\d+)?)\b", clean_q, re.I)
            target_lbl = f"table {tbl_label_match.group(1)}" if tbl_label_match else None
            target_num = tbl_label_match.group(1) if tbl_label_match else (re.search(r"\b(\d+\.\d+)\b", clean_q).group(1) if re.search(r"\b(\d+\.\d+)\b", clean_q) else None)

            if target_lbl and target_lbl not in terms:
                terms.insert(0, target_lbl)
            if target_num and target_num not in terms:
                terms.insert(0, target_num)

            term_clauses = []
            params: Dict[str, Any] = {
                "session_id": str(session_id),
                "limit": limit,
                "lbl_exact": f"%{target_lbl}%" if target_lbl else "%__none__%",
                "num_exact": f"%{target_num}%" if target_num else "%__none__%",
            }
            if source_type:
                params["source_type"] = source_type

            for i, t in enumerate(terms):
                p_key = f"term_{i}"
                term_clauses.append(f"chunk_text LIKE :{p_key}")
                params[p_key] = f"%{t}%"

            like_filter = f"AND ({' OR '.join(term_clauses)})" if term_clauses else ""

            statement = text(f"""
                SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                       1.0 AS score
                FROM document_chunks
                WHERE (
                    session_id = :session_id
                    OR topic_id = :session_id
                    OR doc_id = :session_id
                    OR session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                    OR doc_id IN (SELECT id FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                )
                  {type_filter}
                  {like_filter}
                ORDER BY (CASE WHEN chunk_text LIKE :lbl_exact THEN 1 WHEN chunk_text LIKE :num_exact THEN 2 ELSE 3 END), id ASC
                LIMIT :limit
            """)

            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(statement, params).mappings().fetchall()
            except Exception as ex:
                logger.warning(f"[PgFTSStore] SQLite search_bm25 error: {ex}")
                return []

            seen_c = set()
            dedup_results = []
            for r in rows:
                k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
                if k not in seen_c:
                    seen_c.add(k)
                    dedup_results.append(dict(r))
            return dedup_results

        tbl_label_match = re.search(r"\b(?:table|tbl|figure|fig)\s*(\d+(?:\.\d+)?)\b", clean_q, re.I)
        target_lbl = f"table {tbl_label_match.group(1)}" if tbl_label_match else None
        target_num = tbl_label_match.group(1) if tbl_label_match else (re.search(r"\b(\d+\.\d+)\b", clean_q).group(1) if re.search(r"\b(\d+\.\d+)\b", clean_q) else None)

        statement = text(f"""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                   ts_rank_cd(search_vector, plainto_tsquery('english', :query)) AS score
            FROM document_chunks
            WHERE (
                session_id = :session_id
                OR topic_id = :session_id
            )
              {type_filter}
              AND (
                  search_vector @@ plainto_tsquery('english', :query)
                  OR chunk_text ILIKE :query_like
                  OR chunk_text ILIKE :lbl_exact
                  OR chunk_text ILIKE :num_exact
              )
            ORDER BY (CASE WHEN chunk_text ILIKE :lbl_exact THEN 1 WHEN chunk_text ILIKE :num_exact THEN 2 ELSE 3 END), score DESC
            LIMIT :limit
        """)

        params = {
            "session_id": str(session_id),
            "query": clean_q,
            "query_like": f"%{clean_q}%",
            "lbl_exact": f"%{target_lbl}%" if target_lbl else "%__none__%",
            "num_exact": f"%{target_num}%" if target_num else "%__none__%",
            "limit": limit,
        }
        if source_type:
            params["source_type"] = source_type

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(statement, params).mappings().fetchall()
                if not rows:
                    # Narrow safety net fallback for un-cloned legacy sessions
                    fallback_stmt = text(f"""
                        SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                               ts_rank_cd(search_vector, plainto_tsquery('english', :query)) AS score
                        FROM document_chunks
                        WHERE (
                            session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                            OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                        )
                          {type_filter}
                          AND (
                              search_vector @@ plainto_tsquery('english', :query)
                              OR chunk_text ILIKE :query_like
                          )
                        ORDER BY score DESC
                        LIMIT :limit
                    """)
                    rows = conn.execute(fallback_stmt, params).mappings().fetchall()
        except Exception as ex:
            logger.warning(f"[PgFTSStore] search_bm25 error: {ex}")
            return []

        seen_c = set()
        dedup_results = []
        for r in rows:
            k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
            if k not in seen_c:
                seen_c.add(k)
                dedup_results.append(dict(r))
        return dedup_results

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
            WHERE (
                session_id = :session_id
                OR topic_id = :session_id
            )
              AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_score
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        try:
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

                if not rows:
                    fallback_stmt = text("""
                        SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content,
                               1 - (embedding <=> CAST(:embedding AS vector)) AS score
                        FROM document_chunks
                        WHERE (
                            session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                            OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                        )
                          AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_score
                        ORDER BY embedding <=> CAST(:embedding AS vector)
                        LIMIT :limit
                    """)
                    rows = conn.execute(fallback_stmt, {
                        "session_id": str(session_id),
                        "embedding": vec_str,
                        "min_score": min_score,
                        "limit": limit,
                    }).mappings().fetchall()
        except Exception as ex:
            logger.warning(f"[PgFTSStore] search_dense error: {ex}")
            return []

        seen_c = set()
        dedup_results = []
        for r in rows:
            k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
            if k not in seen_c:
                seen_c.add(k)
                dedup_results.append(dict(r))
        return dedup_results

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
        scope_doc_query = (
            "OR doc_id IN (SELECT id FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
            if self.engine.dialect.name == "sqlite"
            else "OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
        )
        statement = text(f"""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE (
                session_id = :session_id
                OR topic_id = :session_id
                OR doc_id = :session_id
                OR session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                {scope_doc_query}
            ) AND page = :page
            ORDER BY chunk_id
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(statement, {"session_id": str(session_id), "page": int(page)}).mappings().fetchall()
        except Exception:
            return []
        
        seen_c = set()
        dedup_results = []
        for r in rows:
            k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
            if k not in seen_c:
                seen_c.add(k)
                dedup_results.append(dict(r))
        return dedup_results

    def get_chunks_by_pages(self, session_id: str, pages: List[int]) -> List[Dict[str, Any]]:
        """Retrieves all chunks matching any of the given page numbers."""
        if not pages:
            return []
        scope_doc_query = (
            "OR doc_id IN (SELECT id FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
            if self.engine.dialect.name == "sqlite"
            else "OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
        )
        statement = text(f"""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE (
                session_id = :session_id
                OR topic_id = :session_id
                OR doc_id = :session_id
                OR session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                {scope_doc_query}
            ) AND page = ANY(:pages)
            ORDER BY page, chunk_id
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(statement, {"session_id": str(session_id), "pages": [int(p) for p in pages]}).mappings().fetchall()
            seen_c = set()
            dedup_results = []
            for r in rows:
                k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
                if k not in seen_c:
                    seen_c.add(k)
                    dedup_results.append(dict(r))
            return dedup_results
        except Exception:
            return []

    def get_all_chunks(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves all indexed chunks for a session up to limit."""
        statement = text("""
            SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
            FROM document_chunks
            WHERE (
                session_id = :session_id
                OR topic_id = :session_id
            )
            ORDER BY page, chunk_id
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(statement, {"session_id": str(session_id), "limit": int(limit)}).mappings().fetchall()
                if not rows:
                    scope_doc_query = (
                        "OR doc_id IN (SELECT id FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
                        if self.engine.dialect.name == "sqlite"
                        else "OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
                    )
                    fallback_stmt = text(f"""
                        SELECT id, chunk_id, doc_id, page, source_type, chunk_text AS content
                        FROM document_chunks
                        WHERE (
                            session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                            {scope_doc_query}
                        )
                        ORDER BY page, chunk_id
                        LIMIT :limit
                    """)
                    rows = conn.execute(fallback_stmt, {"session_id": str(session_id), "limit": int(limit)}).mappings().fetchall()
            seen_c = set()
            dedup_results = []
            for r in rows:
                k = (r.get("doc_id"), r.get("chunk_id"), r.get("content"))
                if k not in seen_c:
                    seen_c.add(k)
                    dedup_results.append(dict(r))
            return dedup_results
        except Exception:
            return []

    def delete_session_document(self, session_id: str, doc_id: str) -> int:
        """Deletes all chunks for a document within a session."""
        statement = text("""
            DELETE FROM document_chunks
            WHERE session_id = :session_id AND (doc_id = :doc_id OR topic_id = :doc_id)
        """)
        try:
            with self.engine.begin() as conn:
                res = conn.execute(statement, {"session_id": str(session_id), "doc_id": str(doc_id)})
                return res.rowcount or 0
        except Exception:
            return 0

    def delete_session_chunks(self, session_id: str) -> int:
        """Deletes all chunks belonging to a session."""
        statement = text("DELETE FROM document_chunks WHERE session_id = :session_id")
        try:
            with self.engine.begin() as conn:
                res = conn.execute(statement, {"session_id": str(session_id)})
                return res.rowcount or 0
        except Exception:
            return 0

    def count(self, session_id: str) -> int:
        scope_doc_query = (
            "OR doc_id IN (SELECT id FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
            if self.engine.dialect.name == "sqlite"
            else "OR doc_id IN (SELECT id::text FROM documents WHERE doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))"
        )
        statement = text(f"""
            SELECT count(DISTINCT chunk_text) FROM document_chunks 
            WHERE (
                session_id = :session_id 
                OR topic_id = :session_id 
                OR doc_id = :session_id
                OR session_id IN (SELECT session_id FROM session_documents WHERE session_id != :session_id AND doc_hash IN (SELECT doc_hash FROM session_documents WHERE session_id = :session_id AND doc_hash IS NOT NULL AND doc_hash != ''))
                {scope_doc_query}
            )
        """)
        try:
            with self.engine.connect() as conn:
                return int(conn.execute(statement, {"session_id": str(session_id)}).scalar() or 0)
        except Exception:
            return 0


# Global singleton instance
pg_fts_store = PgFTSStore()

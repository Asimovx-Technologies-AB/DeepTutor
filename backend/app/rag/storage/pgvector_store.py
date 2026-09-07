"""PostgreSQL/pgvector vector store for the Azure-native RAG path.

The public API intentionally matches the existing Pinecone and FAISS stores.
PostgreSQL provides dense cosine retrieval, full-text sparse retrieval, and
metadata filtering; weighted reciprocal-rank fusion stays application-side.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings

settings = get_settings()


def _rrf(
    dense: List[Tuple[str, float]],
    sparse: List[Tuple[str, float]],
    dw: float,
    sw: float,
    k: int = 60,
) -> List[Tuple[str, float]]:
    fused: Dict[str, float] = {}
    for rank, (doc_id, _) in enumerate(dense):
        fused[doc_id] = fused.get(doc_id, 0.0) + dw / (k + rank + 1)
    for rank, (doc_id, _) in enumerate(sparse):
        fused[doc_id] = fused.get(doc_id, 0.0) + sw / (k + rank + 1)
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)


class PgVectorStore:
    """Azure PostgreSQL-backed dense, sparse, and hybrid chunk retrieval."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        dimensions: Optional[int] = None,
        engine: Optional[Engine] = None,
    ) -> None:
        self.dimensions = dimensions or settings.PGVECTOR_DIMENSIONS
        if self.dimensions <= 0 or self.dimensions > 2000:
            raise ValueError("PGVECTOR_DIMENSIONS must be between 1 and 2000 for vector HNSW indexes")

        url = (database_url or settings.DATABASE_URL).replace("postgres://", "postgresql://", 1)
        if engine is None and not url.startswith("postgresql"):
            raise ValueError("VECTOR_STORE_BACKEND=pgvector requires a PostgreSQL DATABASE_URL")

        self._engine = engine or create_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=10,
            pool_recycle=300,
        )
        self._schema_ready = False

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id text PRIMARY KEY,
                    topic_id text NOT NULL,
                    chunk_text text NOT NULL,
                    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({self.dimensions}) NOT NULL,
                    search_vector tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce(chunk_text, ''))
                    ) STORED,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_document_chunks_topic ON document_chunks (topic_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_document_chunks_metadata ON document_chunks USING gin (metadata)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_document_chunks_search ON document_chunks USING gin (search_vector)"))
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
                ON document_chunks USING hnsw (embedding vector_cosine_ops)
                WITH (m = {settings.PGVECTOR_HNSW_M},
                      ef_construction = {settings.PGVECTOR_HNSW_EF_CONSTRUCTION})
            """))
        self._schema_ready = True

    def _validate_embedding(self, embedding: Iterable[float]) -> List[float]:
        vector = list(embedding)
        if len(vector) != self.dimensions:
            raise ValueError(
                f"Embedding has {len(vector)} dimensions; pgvector expects {self.dimensions}. "
                "Use the same embedding model for indexing and querying."
            )
        return vector

    @staticmethod
    def _vector_literal(embedding: Iterable[float]) -> str:
        return "[" + ",".join(format(float(value), ".9g") for value in embedding) + "]"

    @staticmethod
    def _chunk_id(topic_id: str, position: int, chunk_text: str) -> str:
        digest = hashlib.sha256(f"{topic_id}\0{chunk_text}".encode("utf-8")).hexdigest()[:24]
        return f"{topic_id}_{position}_{digest}"

    @staticmethod
    def _row_to_chunk(row, score: float) -> Dict:
        values = row._mapping if hasattr(row, "_mapping") else None
        raw_metadata = values["metadata"] if values is not None else row.metadata
        metadata = raw_metadata if isinstance(raw_metadata, dict) else json.loads(raw_metadata or "{}")
        effective_text = metadata.get("parent_text") or row.chunk_text
        return {
            "id": row.id,
            "text": effective_text,
            "child_text": row.chunk_text if metadata.get("parent_text") else None,
            "metadata": metadata,
            "score": round(float(score), 4),
        }

    def add_chunks(self, topic_id: str, chunks: List[Dict], embeddings: List[List[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must contain the same number of items")
        if not chunks:
            return
        self._ensure_schema()
        statement = text("""
            INSERT INTO document_chunks (id, topic_id, chunk_text, metadata, embedding)
            VALUES (:id, :topic_id, :chunk_text, CAST(:metadata AS jsonb), CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                updated_at = now()
        """)
        records = []
        for position, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_text = chunk.get("text", "")
            vector = self._validate_embedding(embedding)
            records.append({
                "id": self._chunk_id(topic_id, position, chunk_text),
                "topic_id": topic_id,
                "chunk_text": chunk_text,
                "metadata": json.dumps(chunk.get("metadata", {}), default=str),
                "embedding": self._vector_literal(vector),
            })
        with self._engine.begin() as conn:
            conn.execute(statement, records)

    def search(
        self,
        topic_id: str,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        where: Optional[Dict] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict]:
        self._ensure_schema()
        vector = self._validate_embedding(query_embedding)
        top_k = top_k or settings.TOP_K_RETRIEVAL
        min_score = settings.MIN_CHUNK_SCORE if min_score is None else min_score
        filter_sql = " AND metadata @> CAST(:metadata_filter AS jsonb)" if where else ""
        statement = text(f"""
            SELECT id, chunk_text, metadata,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM document_chunks
            WHERE topic_id = :topic_id
              AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_score
              {filter_sql}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)
        params = {
            "topic_id": topic_id,
            "embedding": self._vector_literal(vector),
            "min_score": min_score,
            "top_k": top_k,
        }
        if where:
            params["metadata_filter"] = json.dumps(where, default=str)
        with self._engine.connect() as conn:
            conn.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.PGVECTOR_HNSW_EF_SEARCH)}"))
            rows = conn.execute(statement, params).fetchall()
        return [self._row_to_chunk(row, row.score) for row in rows]

    def search_bm25(self, topic_id: str, query: str, top_k: Optional[int] = None) -> List[Dict]:
        self._ensure_schema()
        top_k = top_k or settings.TOP_K_RETRIEVAL
        statement = text("""
            SELECT id, chunk_text, metadata,
                   ts_rank_cd(search_vector, plainto_tsquery('simple', :query)) AS score
            FROM document_chunks
            WHERE topic_id = :topic_id
              AND search_vector @@ plainto_tsquery('simple', :query)
            ORDER BY score DESC
            LIMIT :top_k
        """)
        with self._engine.connect() as conn:
            rows = conn.execute(statement, {"topic_id": topic_id, "query": query, "top_k": top_k}).fetchall()
        if not rows:
            return []
        max_score = max(float(row.score) for row in rows) or 1.0
        return [self._row_to_chunk(row, float(row.score) / max_score) for row in rows]

    def search_hybrid(
        self,
        topic_id: str,
        query_embedding: List[float],
        query_text: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict]:
        if not settings.ENABLE_HYBRID_SEARCH:
            return self.search(topic_id, query_embedding, top_k, min_score=min_score)
        top_k = top_k or settings.TOP_K_RETRIEVAL
        retrieval_k = min(top_k * 2, 20)
        dense = self.search(topic_id, query_embedding, retrieval_k, min_score=0.0)
        sparse = self.search_bm25(topic_id, query_text, retrieval_k)
        chunks = {chunk["id"]: chunk for chunk in [*dense, *sparse]}
        fused = _rrf(
            [(chunk["id"], chunk["score"]) for chunk in dense],
            [(chunk["id"], chunk["score"]) for chunk in sparse],
            settings.DENSE_WEIGHT,
            settings.SPARSE_WEIGHT,
        )
        max_rrf = (settings.DENSE_WEIGHT + settings.SPARSE_WEIGHT) / 61.0
        results = []
        for doc_id, fused_score in fused[:top_k]:
            chunk = dict(chunks[doc_id])
            chunk["score"] = round(max(chunk["score"], min(1.0, fused_score / max_rrf) * 0.95), 4)
            chunk["fused"] = True
            chunk["fused_raw"] = round(fused_score, 6)
            meta = chunk["metadata"]
            chunk["citation"] = {
                "source": meta.get("source", ""),
                "page": meta.get("page", 0),
                "section": meta.get("section_title", ""),
                "section_path": meta.get("section_path", ""),
            }
            results.append(chunk)
        return results

    def get_chunks_by_pages(self, topic_id: str, pages: List[int]) -> List[Dict]:
        if not pages:
            return []
        self._ensure_schema()
        statement = text("""
            SELECT id, chunk_text, metadata, 1.0 AS score
            FROM document_chunks
            WHERE topic_id = :topic_id AND metadata ->> 'page' IN :pages
            ORDER BY id
        """).bindparams(bindparam("pages", expanding=True))
        with self._engine.connect() as conn:
            rows = conn.execute(statement, {"topic_id": topic_id, "pages": [str(page) for page in pages]}).fetchall()
        return [self._row_to_chunk(row, 1.0) for row in rows]

    def get_all_chunks(self, topic_id: str, limit: int = 15) -> List[Dict]:
        self._ensure_schema()
        statement = text("""
            SELECT id, chunk_text, metadata, 0.9 AS score
            FROM document_chunks WHERE topic_id = :topic_id
            ORDER BY created_at, id LIMIT :limit
        """)
        with self._engine.connect() as conn:
            rows = conn.execute(statement, {"topic_id": topic_id, "limit": limit}).fetchall()
        return [self._row_to_chunk(row, 0.9) for row in rows]

    def count(self, topic_id: str) -> int:
        self._ensure_schema()
        with self._engine.connect() as conn:
            return int(conn.execute(
                text("SELECT count(*) FROM document_chunks WHERE topic_id = :topic_id"),
                {"topic_id": topic_id},
            ).scalar_one())

    def delete_topic(self, topic_id: str) -> None:
        self._ensure_schema()
        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM document_chunks WHERE topic_id = :topic_id"), {"topic_id": topic_id})

    def delete_collection(self, collection_name: str) -> None:
        self.delete_topic(collection_name)

    def reset(self) -> None:
        self._ensure_schema()
        with self._engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE document_chunks"))

    def cache_stats(self) -> Dict:
        return {"backend": "pgvector", "dimensions": self.dimensions}

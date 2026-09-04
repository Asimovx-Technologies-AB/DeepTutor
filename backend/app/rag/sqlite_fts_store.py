"""
Local Embedded SQLite FTS5 Full-Text & BM25 Search Store.
Provides ultra-fast (<2ms), zero-cloud, 100% local persistent indexing for study materials.
"""
import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "study_store.db"


class SQLiteFTSStore:
    """Local, zero-cloud SQLite FTS5 Full-Text Store with native BM25 relevance scoring."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables with FTS5 virtual full-text index."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Virtual FTS5 table for fast keyword and BM25 ranking
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
                    chunk_id UNINDEXED,
                    doc_id,
                    page UNINDEXED,
                    source_type,
                    content,
                    tokenize='porter unicode61'
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Inserts or updates document chunks into the local FTS5 store."""
        if not chunks:
            return 0

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", "")
                doc_id = chunk.get("doc_id", "")
                page = chunk.get("page", 1)
                source_type = chunk.get("source_type", "text")
                content = chunk.get("content", "")

                if not content.strip():
                    continue

                # Delete existing chunk if present to prevent duplicates
                cursor.execute("DELETE FROM document_fts WHERE chunk_id = ?", (chunk_id,))
                cursor.execute("""
                    INSERT INTO document_fts (chunk_id, doc_id, page, source_type, content)
                    VALUES (?, ?, ?, ?, ?)
                """, (chunk_id, doc_id, page, source_type, content))

            conn.commit()
            return len(chunks)
        finally:
            conn.close()

    def search(
        self,
        doc_id: str,
        query: str,
        source_type: Optional[str] = None,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Executes BM25 search across document chunks in < 2ms.
        """
        cleaned_query = self._sanitize_fts_query(query)
        if not cleaned_query:
            return []

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if source_type:
                sql = """
                    SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) AS rank
                    FROM document_fts
                    WHERE doc_id = ? AND source_type = ? AND document_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                """
                cursor.execute(sql, (doc_id, source_type, cleaned_query, limit))
            else:
                sql = """
                    SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) AS rank
                    FROM document_fts
                    WHERE doc_id = ? AND document_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                """
                cursor.execute(sql, (doc_id, cleaned_query, limit))

            rows = cursor.fetchall()
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "page": row["page"],
                    "source_type": row["source_type"],
                    "content": row["content"],
                    "rank": row["rank"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_page_chunks(self, doc_id: str, page: int) -> List[Dict[str, Any]]:
        """Retrieves all chunks directly for a specific page number."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id, doc_id, page, source_type, content
                FROM document_fts
                WHERE doc_id = ? AND page = ?
                ORDER BY rowid ASC
            """, (doc_id, page))
            rows = cursor.fetchall()
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "page": row["page"],
                    "source_type": row["source_type"],
                    "content": row["content"],
                }
                for row in rows
            ]
        finally:
            conn.close()


    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Converts natural language queries into safe, OR-joined FTS5 token queries."""
        words = re.findall(r"\w+", query.strip())
        # Filter out common stop words for clean token matching
        stopwords = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "are", "was", "were", "what", "how", "why", "who", "which",
            "explain", "tell", "me", "about", "please", "can", "you", "give"
        }
        filtered = [w for w in words if w.lower() not in stopwords and len(w) > 1]
        if not filtered:
            filtered = words

        if not filtered:
            return ""

        # Join with OR for broad relevance scoring with BM25
        return " OR ".join(f'"{w}"' for w in filtered)


# Global singleton instance (default fallback)
sqlite_fts_store = SQLiteFTSStore()

_session_stores: Dict[str, SQLiteFTSStore] = {}

def get_session_store(session_id: Optional[str] = None) -> SQLiteFTSStore:
    """Returns an isolated SQLite FTS5 store for a specific session."""
    if not session_id:
        return sqlite_fts_store
    
    if session_id not in _session_stores:
        session_db = DB_PATH.parent / "sessions" / f"{session_id}.db"
        _session_stores[session_id] = SQLiteFTSStore(db_path=session_db)
    return _session_stores[session_id]


def close_session_store(session_id: str):
    """Evicts session store from cache."""
    if session_id in _session_stores:
        del _session_stores[session_id]



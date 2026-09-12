"""
Helper script to inspect chunks stored in local PostgreSQL.

Usage:
    python scripts/check_postgres_chunks.py
    python scripts/check_postgres_chunks.py --limit 10
    python scripts/check_postgres_chunks.py --doc-id <id>
"""
import sys
import json
import argparse
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import engine
from sqlalchemy import text


def inspect_chunks(limit: int = 5, doc_id: str = None, session_id: str = None):
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM document_chunks;")).scalar()
        print(f"\n=======================================================")
        print(f"  [PostgreSQL] Total document_chunks in DB: {total}")
        print(f"=======================================================\n")

        where_clauses = []
        params = {"limit": limit}
        if doc_id:
            where_clauses.append("doc_id = :doc_id")
            params["doc_id"] = doc_id
        if session_id:
            where_clauses.append("session_id = :session_id")
            params["session_id"] = session_id

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = text(f"""
            SELECT id, chunk_id, doc_id, session_id, page, source_type,
                   SUBSTRING(chunk_text, 1, 100) AS snippet,
                   metadata, created_at
            FROM document_chunks
            {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit;
        """)

        rows = conn.execute(query, params).mappings().fetchall()

        if not rows:
            print("No chunks found matching query criteria.")
            return

        print(f"Showing latest {len(rows)} chunk(s):\n")
        for idx, row in enumerate(rows, start=1):
            meta = row["metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    pass

            kbox = meta.get("knowledge_box") if isinstance(meta, dict) else "N/A"
            concepts = meta.get("named_concepts") if isinstance(meta, dict) else []

            print(f"{idx}. Chunk ID: {row['chunk_id']}")
            print(f"   Session ID:     {row['session_id']}")
            print(f"   Doc ID:         {row['doc_id']}")
            print(f"   Page:           {row['page']}")
            print(f"   Source Type:    {row['source_type']}")
            print(f"   Knowledge Box:  {kbox}")
            print(f"   Concepts:       {concepts}")
            print(f"   Snippet:        {row['snippet']}...")
            print(f"   Created At:     {row['created_at']}")
            print("-" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect chunks in PostgreSQL")
    parser.add_argument("--limit", type=int, default=5, help="Number of records to show")
    parser.add_argument("--doc-id", type=str, default=None, help="Filter by doc_id")
    parser.add_argument("--session-id", type=str, default=None, help="Filter by session_id")
    args = parser.parse_args()

    inspect_chunks(limit=args.limit, doc_id=args.doc_id, session_id=args.session_id)

"""
DeepTutor Data Migration: SQLite -> Azure PostgreSQL + pgvector.

Migrates:
  1. Per-user and per-session SQLite databases under backend/data/ ->
     - study_session_messages
     - study_session_topics
     - document_chunks (with automatic re-embedding at 1536d)
     - session_documents
  2. sessions_registry.json -> workspace_sessions table
  3. user_memory.json -> user_memory table

Features:
  - Idempotent: safe to run multiple times (ON CONFLICT DO NOTHING / UPSERT).
  - Deterministic UUID mapping for non-UUID SQLite keys.
  - Foreign-key safe: verifies user existence before inserting into workspace_sessions.
  - --dry-run flag: inspect and print migration stats without writing to PostgreSQL.
  - --skip-embed flag: migrate FTS metadata and chunks without calling external embedding API.
"""
import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psycopg2
from psycopg2.extras import execute_batch, Json

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings


def to_uuid(val: str, namespace_suffix: str = "") -> str:
    """Returns val if it's already a valid UUID string, otherwise generates a deterministic UUID5."""
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError):
        seed = f"{val}:{namespace_suffix}" if namespace_suffix else str(val)
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def extract_user_id_from_filename(filename: str) -> Optional[str]:
    match = re.match(r"^user_(.+)\.db$", filename)
    return match.group(1) if match else None


def extract_session_id_from_filename(filename: str) -> Optional[str]:
    match = re.match(r"^session_(.+)\.db$", filename)
    return match.group(1) if match else None


class DataMigrator:
    def __init__(self, dry_run: bool = False, skip_embed: bool = False):
        self.dry_run = dry_run
        self.skip_embed = skip_embed
        self.settings = get_settings()
        self.data_dir = BACKEND_DIR / "data"

        self.db_url = self.settings.DATABASE_URL
        if self.db_url.startswith("postgresql+asyncpg://"):
            self.db_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif self.db_url.startswith("postgres://"):
            self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)

        self.conn = None
        self.existing_users: Set[str] = set()

    def connect(self):
        if not self.dry_run:
            self.conn = psycopg2.connect(self.db_url)
            with self.conn.cursor() as cur:
                cur.execute("SELECT id FROM users;")
                self.existing_users = {row[0] for row in cur.fetchall()}

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Compute 1536-dimensional embeddings for a batch of texts."""
        if self.skip_embed or self.dry_run:
            # Return dummy 1536d vector for dry-run
            return [[0.0] * self.settings.PGVECTOR_DIMENSIONS for _ in texts]

        provider = self.settings.EMBEDDING_PROVIDER.lower()
        if provider == "azure_openai":
            from app.rag.azure_openai_client import azure_openai
            return await azure_openai.embed_batch(texts)
        else:
            from app.rag.azure_openai_client import openai_client
            return await openai_client.embed_batch(texts)

    def migrate_sessions_registry(self) -> int:
        registry_path = self.data_dir / "sessions_registry.json"
        if not registry_path.exists():
            print("[REGISTRY] sessions_registry.json not found.")
            return 0

        with open(registry_path, "r", encoding="utf-8") as f:
            try:
                registry = json.load(f)
            except Exception as e:
                print(f"[REGISTRY] Error reading {registry_path}: {e}")
                return 0

        # Can be dict {session_id: {...}} or list [{...}]
        items = registry if isinstance(registry, list) else list(registry.values())
        print(f"[REGISTRY] Found {len(items)} sessions in registry.")

        if self.dry_run:
            for item in items[:3]:
                print(f"  [DRY-RUN] Session: id={item.get('id')}, title={item.get('title')}, user_id={item.get('user_id')}")
            return len(items)

        records = []
        for item in items:
            s_id = str(item.get("id") or "")
            if not s_id:
                continue
            raw_user_id = item.get("user_id")
            # Enforce FK safety: set user_id to None if not in users table
            user_id = raw_user_id if raw_user_id in self.existing_users else None
            title = str(item.get("title") or "Study Session")
            subject = str(item.get("subject") or "General Study")
            created_at = str(item.get("created_at") or "")
            last_active = str(item.get("last_active") or created_at)
            topic_count = int(item.get("topic_count") or 0)
            message_count = int(item.get("message_count") or 0)

            records.append((
                s_id, user_id, title, subject, created_at, last_active, topic_count, message_count
            ))

        with self.conn.cursor() as cur:
            execute_batch(cur, """
                INSERT INTO workspace_sessions (id, user_id, title, subject, created_at, last_active, topics_count, messages_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, workspace_sessions.user_id),
                    title = EXCLUDED.title,
                    subject = EXCLUDED.subject,
                    last_active = EXCLUDED.last_active,
                    topics_count = EXCLUDED.topics_count,
                    messages_count = EXCLUDED.messages_count;
            """, records)
        self.conn.commit()
        print(f"[REGISTRY] Migrated/upserted {len(records)} sessions into workspace_sessions.")
        return len(records)

    def migrate_user_memory(self) -> int:
        memory_path = self.data_dir / "user_memory.json"
        if not memory_path.exists():
            print("[MEMORY] user_memory.json not found.")
            return 0

        with open(memory_path, "r", encoding="utf-8") as f:
            try:
                mem_data = json.load(f)
            except Exception as e:
                print(f"[MEMORY] Error reading {memory_path}: {e}")
                return 0

        if not mem_data:
            print("[MEMORY] user_memory.json is empty.")
            return 0

        entries = mem_data if isinstance(mem_data, list) else [
            {"user_id": uid, "memory": m} for uid, m in mem_data.items()
        ]
        print(f"[MEMORY] Found {len(entries)} memory entries.")

        if self.dry_run:
            return len(entries)

        records = [
            (str(entry.get("user_id")), Json(entry.get("memory") or {}))
            for entry in entries if entry.get("user_id")
        ]

        if records:
            with self.conn.cursor() as cur:
                execute_batch(cur, """
                    INSERT INTO user_memory (user_id, memory_json, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                        memory_json = EXCLUDED.memory_json,
                        updated_at = now();
                """, records)
            self.conn.commit()
            print(f"[MEMORY] Migrated {len(records)} user_memory entries.")
        return len(records)

    async def migrate_sqlite_databases(self):
        db_files = list(self.data_dir.rglob("*.db"))
        print(f"[SQLITE] Found {len(db_files)} SQLite database files under {self.data_dir}")

        total_msgs = 0
        total_topics = 0
        total_docs = 0
        total_chunks = 0

        for db_file in db_files:
            rel_name = str(db_file.relative_to(self.data_dir))
            filename = db_file.name
            user_id = extract_user_id_from_filename(filename)
            session_id = extract_session_id_from_filename(filename)

            try:
                conn_sqlite = sqlite3.connect(str(db_file))
                conn_sqlite.row_factory = sqlite3.Row
                cur_sqlite = conn_sqlite.cursor()
            except Exception as e:
                print(f"[SQLITE] Error connecting to {rel_name}: {e}")
                continue

            # Check available tables
            cur_sqlite.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in cur_sqlite.fetchall()}

            # 1. session_messages -> study_session_messages
            if "session_messages" in tables:
                cur_sqlite.execute("SELECT * FROM session_messages;")
                rows = cur_sqlite.fetchall()
                if rows:
                    total_msgs += len(rows)
                    if self.dry_run:
                        print(f"  [DRY-RUN] {rel_name}: session_messages ({len(rows)} rows)")
                    else:
                        msg_records = []
                        for r in rows:
                            msg_id = to_uuid(r["id"])
                            sid = r["session_id"]
                            uid = user_id or (r["user_id"] if "user_id" in r.keys() else None)
                            role = r["role"] or "user"
                            text = r["text"] or ""
                            thought = r["thought_process"] if "thought_process" in r.keys() else ""
                            quiz = Json(json.loads(r["quiz_data_json"])) if "quiz_data_json" in r.keys() and r["quiz_data_json"] else None
                            topics = Json(json.loads(r["topics_json"])) if "topics_json" in r.keys() and r["topics_json"] else None
                            attach = Json(json.loads(r["attachment_json"])) if "attachment_json" in r.keys() and r["attachment_json"] else None
                            is_expl = bool(r["is_explanation"]) if "is_explanation" in r.keys() else False
                            created_at = r["created_at"] if "created_at" in r.keys() else None

                            msg_records.append((
                                msg_id, sid, uid, role, text, thought, quiz, topics, attach, is_expl, created_at
                            ))

                        with self.conn.cursor() as cur:
                            execute_batch(cur, """
                                INSERT INTO study_session_messages (
                                    id, session_id, user_id, role, text, thought_process,
                                    quiz_data_json, topics_json, attachment_json, is_explanation, created_at
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()))
                                ON CONFLICT (id) DO NOTHING;
                            """, msg_records)
                        self.conn.commit()

            # 2. session_topics -> study_session_topics
            if "session_topics" in tables:
                cur_sqlite.execute("SELECT * FROM session_topics;")
                rows = cur_sqlite.fetchall()
                if rows:
                    total_topics += len(rows)
                    if self.dry_run:
                        print(f"  [DRY-RUN] {rel_name}: session_topics ({len(rows)} rows)")
                    else:
                        topic_records = []
                        for r in rows:
                            t_id = to_uuid(r["id"], namespace_suffix=r["session_id"])
                            sid = r["session_id"]
                            uid = user_id or (r["user_id"] if "user_id" in r.keys() else None)
                            title = r["title"] or ""
                            summary = r["summary"] or ""
                            diff = r["difficulty"] if "difficulty" in r.keys() else "Intermediate"
                            kconcepts = Json(json.loads(r["key_concepts_json"])) if "key_concepts_json" in r.keys() and r["key_concepts_json"] else Json([])
                            est_time = r["estimated_study_time"] if "estimated_study_time" in r.keys() else "10 mins"
                            doc_name = r["document_name"] if "document_name" in r.keys() else ""

                            topic_records.append((
                                t_id, sid, uid, title, summary, diff, kconcepts, est_time, doc_name
                            ))

                        with self.conn.cursor() as cur:
                            execute_batch(cur, """
                                INSERT INTO study_session_topics (
                                    id, session_id, user_id, title, summary, difficulty,
                                    key_concepts_json, estimated_study_time, document_name, created_at
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                                ON CONFLICT (id) DO NOTHING;
                            """, topic_records)
                        self.conn.commit()

            # 3. session_documents -> session_documents
            if "session_documents" in tables:
                cur_sqlite.execute("SELECT * FROM session_documents;")
                rows = cur_sqlite.fetchall()
                if rows:
                    total_docs += len(rows)
                    if self.dry_run:
                        print(f"  [DRY-RUN] {rel_name}: session_documents ({len(rows)} rows)")
                    else:
                        doc_records = []
                        import hashlib
                        for r in rows:
                            doc_id = to_uuid(r["id"], namespace_suffix=r["session_id"])
                            sid = r["session_id"]
                            uid = user_id or (r["user_id"] if "user_id" in r.keys() else None)
                            fname = r["filename"] if "filename" in r.keys() else ""
                            fpath = r["file_path"] if "file_path" in r.keys() else ""
                            status = r["status"] if "status" in r.keys() else "completed"
                            page_count = int(r["page_count"]) if "page_count" in r.keys() and r["page_count"] else 0
                            created_at = r["created_at"] if "created_at" in r.keys() else None
                            doc_hash = hashlib.sha256(f"{sid}_{fname}_{doc_id}".encode()).hexdigest()[:32]

                            doc_records.append((
                                doc_id, sid, doc_hash, uid, fname, fpath, status, page_count, created_at
                            ))

                        with self.conn.cursor() as cur:
                            execute_batch(cur, """
                                INSERT INTO session_documents (
                                    id, session_id, doc_hash, user_id, filename, file_path, status, page_count, created_at
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()))
                                ON CONFLICT (id) DO NOTHING;
                            """, doc_records)
                        self.conn.commit()

            # 4. document_fts -> document_chunks (with re-embedding)
            if "document_fts" in tables:
                try:
                    cur_sqlite.execute("SELECT * FROM document_fts;")
                    rows = cur_sqlite.fetchall()
                except Exception:
                    rows = []

                if rows:
                    total_chunks += len(rows)
                    if self.dry_run:
                        print(f"  [DRY-RUN] {rel_name}: document_fts ({len(rows)} chunks)")
                    else:
                        print(f"[CHUNKS] Migrating and embedding {len(rows)} chunks from {rel_name}...")
                        batch_size = 50
                        for i in range(0, len(rows), batch_size):
                            batch = rows[i:i + batch_size]
                            texts = [str(r["content"] or "").strip() for r in batch]
                            embeddings = await self.get_embeddings(texts)

                            chunk_records = []
                            for r, text_content, emb in zip(batch, texts, embeddings):
                                sid = str(r["session_id"]) if "session_id" in r.keys() and r["session_id"] else str(session_id or "")
                                doc_id = str(r["doc_id"]) if "doc_id" in r.keys() and r["doc_id"] else ""
                                chunk_id = str(r["chunk_id"]) if "chunk_id" in r.keys() and r["chunk_id"] else ""
                                chunk_pk = to_uuid(f"{sid}_{chunk_id}_{doc_id}")
                                topic_id = doc_id if doc_id else "general"
                                page = int(r["page"]) if "page" in r.keys() and r["page"] else 1
                                source_type = str(r["source_type"]) if "source_type" in r.keys() and r["source_type"] else "text"
                                metadata = {
                                    "session_id": sid,
                                    "doc_id": doc_id,
                                    "chunk_id": chunk_id,
                                    "page": page,
                                    "source_type": source_type,
                                    "migrated_from": rel_name,
                                }

                                # Format embedding literal for pgvector
                                emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"

                                chunk_records.append((
                                    chunk_pk, sid, topic_id, doc_id, chunk_id, page, source_type,
                                    text_content, Json(metadata), emb_str
                                ))

                            with self.conn.cursor() as cur:
                                execute_batch(cur, """
                                    INSERT INTO document_chunks (
                                        id, session_id, topic_id, doc_id, chunk_id, page, source_type,
                                        chunk_text, metadata, embedding, created_at, updated_at
                                    )
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, now(), now())
                                    ON CONFLICT (id) DO UPDATE SET
                                        chunk_text = EXCLUDED.chunk_text,
                                        metadata = EXCLUDED.metadata,
                                        embedding = EXCLUDED.embedding,
                                        updated_at = now();
                                """, chunk_records)
                            self.conn.commit()

            conn_sqlite.close()

        print(f"\n[SUMMARY] Total migrated across all SQLite DBs:")
        print(f"  Messages:  {total_msgs}")
        print(f"  Topics:    {total_topics}")
        print(f"  Documents: {total_docs}")
        print(f"  Chunks:    {total_chunks}")


async def main():
    parser = argparse.ArgumentParser(description="Migrate DeepTutor SQLite data to PostgreSQL + pgvector")
    parser.add_argument("--dry-run", action="store_true", help="Log what would be migrated without modifying PostgreSQL")
    parser.add_argument("--skip-embed", action="store_true", help="Skip calling external embedding API (uses zero vectors)")
    args = parser.parse_args()

    migrator = DataMigrator(dry_run=args.dry_run, skip_embed=args.skip_embed)
    try:
        migrator.connect()
        print(f"=== DeepTutor Data Migration (dry_run={args.dry_run}, skip_embed={args.skip_embed}) ===")
        migrator.migrate_sessions_registry()
        migrator.migrate_user_memory()
        await migrator.migrate_sqlite_databases()
        print("=== Data Migration Completed Successfully ===")
    finally:
        migrator.close()


if __name__ == "__main__":
    asyncio.run(main())

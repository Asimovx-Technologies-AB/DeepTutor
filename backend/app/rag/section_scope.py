"""
Single source of truth for "which ChromaDB collection belongs to this
user's section" and for pulling context out of it.

Every feature (chat, quiz, flashcards) and the ingestion pipeline must
import get_section_collection_id() from HERE rather than re-deriving a
key string themselves. That's what caused the earlier bug: quiz_generator
guessed one key format while ingestion (presumably) used another, so
lookups silently missed and fell through to an unrelated "general"
collection.
"""
import re
from typing import Optional

from app.rag.vector_store import vector_store
from app.rag.ollama_client import ollama
from app.core import database as db


def get_section_collection_id(user_id: str, section_id: str) -> str:
    """
    Deterministic collection name for a given user's section or curriculum topic.
    Curriculum topics (e.g. math-10-1, sslc-physics) map directly to their textbook namespace.
    """
    if section_id and section_id.startswith(("sslc-", "math-10-", "phys-10-", "chem-10-", "math-", "phys-", "chem-", "textbook")):
        return section_id
    safe_uid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(user_id))
    safe_sid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(section_id))
    return f"sec_{safe_uid}_{safe_sid}"


def user_owns_section(user_id: str, section_id: str) -> bool:
    """
    Authorization check: confirm this section belongs to this user or is a curriculum topic.
    """
    if not section_id or not user_id:
        return False

    # Curriculum topics are available to all students
    if section_id.startswith(("sslc-", "math-10-", "phys-10-", "chem-10-", "general")):
        return True

    docs = db.get_documents_for_user_and_topic(user_id, section_id)
    if docs:
        return True

    all_user_docs = db.get_documents_for_user(user_id)
    if all_user_docs:
        return True

    sessions = db.get_sessions_for_user(user_id)
    return any(s.get("topic_id") == section_id or s.get("id") == section_id for s in sessions)


async def get_section_context(
    user_id: str,
    section_id: str,
    query: Optional[str] = None,
    top_k: int = 8,
) -> list[str]:
    """
    Fetch text chunks scoped to this user's section or pre-ingested curriculum textbook topic in ChromaDB.
    """
    if not user_owns_section(user_id, section_id):
        print(f"[section_scope] Denied: user {user_id} does not own section {section_id}")
        return []

    from app.rag.storage import active_vector_store
    from app.rag.pipeline.embedder import embedding_pipeline

    collection_id = get_section_collection_id(user_id, section_id)

    try:
        count = active_vector_store.count(collection_id)
    except Exception:
        count = 0

    # Fallback to pre-ingested textbook topic collection if user has no custom upload
    if count == 0:
        try:
            raw_count = active_vector_store.count(section_id)
            if raw_count > 0:
                collection_id = section_id
                count = raw_count
        except Exception:
            pass

    if count == 0:
        print(f"[section_scope] Collection {collection_id} is empty. Searching user's other collections...")
        candidate_topics = []
        user_docs = db.get_documents_for_user(user_id)
        for d in user_docs:
            tid = d.get("topic_id")
            if tid and tid not in candidate_topics:
                candidate_topics.append(tid)
        if "general" not in candidate_topics:
            candidate_topics.append("general")

        found_collection = None
        for candidate_tid in candidate_topics:
            cand_coll = get_section_collection_id(user_id, candidate_tid)
            try:
                if active_vector_store.count(cand_coll) > 0:
                    found_collection = cand_coll
                    break
            except Exception:
                continue

        if found_collection:
            print(f"[section_scope] Using populated collection {found_collection} for user {user_id}")
            target_collection_id = found_collection
        else:
            print(f"[section_scope] No populated collections found for user {user_id}.")
            return []

    if query and query.strip():
        try:
            emb = await embedding_pipeline.embed(query)
            if emb:
                results = active_vector_store.search_hybrid(target_collection_id, emb, query, top_k=top_k)
                chunks = [r["text"] for r in results if r.get("text")]
                if chunks:
                    return chunks
        except Exception as e:
            print(f"[section_scope] Embedding/search failed for {target_collection_id}: {e}")

    # No query, or query search came back empty — fall back to sample from target_collection_id
    try:
        if hasattr(active_vector_store, "get_all_chunks"):
            chunks = active_vector_store.get_all_chunks(target_collection_id)
            if chunks:
                return [c["text"] if isinstance(c, dict) else str(c) for c in chunks[:top_k]]
        if hasattr(active_vector_store, "_topic"):
            topic = active_vector_store._topic(target_collection_id)
            return topic._docs[:top_k]
        res = active_vector_store.search(target_collection_id, [0.0] * 3072, top_k=top_k, min_score=0.0)
        return [r["text"] for r in res if r.get("text")]
    except Exception as e:
        print(f"[section_scope] Failed to read collection {target_collection_id}: {e}")
        return []
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
    Deterministic, ChromaDB-safe collection name for a given user's
    section. Call this at ingestion time (when a PDF is uploaded and
    embedded) and at retrieval time (chat / quiz / flashcards) — never
    reconstruct this string differently in two places.
    """
    safe_uid = re.sub(r"[^a-zA-Z0-9_]", "_", user_id)
    safe_sid = re.sub(r"[^a-zA-Z0-9_]", "_", section_id)
    return f"sec_{safe_uid}_{safe_sid}"


def user_owns_section(user_id: str, section_id: str) -> bool:
    """
    Authorization check: confirm this section belongs to this user.
    We infer ownership from documents or sessions in the user's namespace.
    """
    if not section_id or not user_id:
        return False

    docs = db.get_documents_for_user_and_topic(user_id, section_id)
    if docs:
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
    Fetch text chunks scoped STRICTLY to this user's section. No fallback
    to any other collection, "general" or otherwise. Returns [] if the
    section has no processed content yet — callers must treat that as
    "nothing to work with" and say so, not substitute unrelated content.

    Use this same function from chat, quiz generation, and flashcard
    generation so all three features are scoped identically.
    """
    if not user_owns_section(user_id, section_id):
        print(f"[section_scope] Denied: user {user_id} does not own section {section_id}")
        return []

    collection_id = get_section_collection_id(user_id, section_id)

    try:
        col = vector_store._collection(collection_id)
    except Exception as e:
        print(f"[section_scope] No collection for {collection_id}: {e}")
        return []

    if col.count() == 0:
        print(f"[section_scope] Collection {collection_id} exists but is empty.")
        return []

    if query and query.strip():
        try:
            emb = await ollama.embed(query)
            if emb:
                results = vector_store.search(collection_id, emb, top_k=top_k)
                chunks = [r["text"] for r in results if r.get("text")]
                if chunks:
                    return chunks
        except Exception as e:
            print(f"[section_scope] Embedding/search failed for {collection_id}: {e}")

    # No query, or query search came back empty — fall back to a sample
    # of this SAME section's own documents (never another section's).
    try:
        data = col.get(include=["documents"])
        docs = data.get("documents", []) or []
        return docs[:top_k]
    except Exception as e:
        print(f"[section_scope] Failed to read collection {collection_id}: {e}")
        return []
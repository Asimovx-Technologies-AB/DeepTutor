"""
ChromaDB vector store wrapper.
Stores document chunk embeddings for similarity search.
"""
import os
from typing import List, Dict, Optional
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import get_settings

settings = get_settings()


class VectorStore:
    def __init__(self):
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection(self, topic_id: str):
        """Get or create collection for a topic."""
        return self._client.get_or_create_collection(
            name=f"topic_{topic_id.replace('-', '_')}",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        topic_id: str,
        chunks: List[Dict],         # [{text, metadata}]
        embeddings: List[List[float]],
    ) -> None:
        """Add text chunks with pre-computed embeddings."""
        collection = self._collection(topic_id)
        ids = [f"{topic_id}_{i}_{hash(c['text']) % 10**8}" for i, c in enumerate(chunks)]
        documents = [c["text"] for c in chunks]
        metadatas = [c.get("metadata", {}) for c in chunks]

        if not ids:
            return

        # Avoid duplicate IDs
        existing = set(collection.get(ids=ids)["ids"])
        new_idx = [i for i, id_ in enumerate(ids) if id_ not in existing]
        if not new_idx:
            return

        collection.add(
            ids=[ids[i] for i in new_idx],
            documents=[documents[i] for i in new_idx],
            embeddings=[embeddings[i] for i in new_idx],
            metadatas=[metadatas[i] for i in new_idx],
        )

    def search(
        self,
        topic_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Return top_k most similar chunks.
        Each result: { text, metadata, score }
        """
        collection = self._collection(topic_id)

        if collection.count() == 0:
            return []

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        try:
            results = collection.query(**query_kwargs)
        except Exception:
            # Fallback to unrestricted search if filter fails
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

        chunks = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(docs, metas, distances):
            # Convert cosine distance to similarity score (0-1)
            score = round(1 - dist, 4)
            chunks.append({"text": doc, "metadata": meta, "score": score})

        return chunks

    def get_chunks_by_pages(
        self,
        topic_id: str,
        pages: List[int],
    ) -> List[Dict]:
        """
        Retrieve chunks that belong to specific page numbers using metadata filter.
        Returns list of chunks with text, metadata, score.
        """
        collection = self._collection(topic_id)
        if collection.count() == 0 or not pages:
            return []

        where_clause = {"page": pages[0]} if len(pages) == 1 else {"page": {"$in": pages}}
        try:
            results = collection.get(
                where=where_clause,
                include=["documents", "metadatas"],
            )
            chunks = []
            if results and results.get("documents"):
                for doc, meta in zip(results["documents"], results["metadatas"]):
                    chunks.append({"text": doc, "metadata": meta, "score": 1.0})
            return chunks
        except Exception:
            return []

    def count(self, topic_id: str) -> int:
        return self._collection(topic_id).count()

    def delete_topic(self, topic_id: str) -> None:
        try:
            self._client.delete_collection(f"topic_{topic_id.replace('-', '_')}")
        except Exception:
            pass

    def reset(self) -> None:
        try:
            for col in self._client.list_collections():
                name = col.name if hasattr(col, 'name') else str(col)
                self._client.delete_collection(name)
        except Exception:
            pass


# Singleton
vector_store = VectorStore()

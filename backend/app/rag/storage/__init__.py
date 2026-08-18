"""
Stage 3 — Storage Package
===========================
Exports the active vector store and graph store backends based on config.

VECTOR_STORE_BACKEND = "faiss"  → FAISSVectorStore
VECTOR_STORE_BACKEND = "chroma" → VectorStore (legacy ChromaDB)

GRAPH_STORE_BACKEND = "json_kv"   → GraphKVStore
GRAPH_STORE_BACKEND = "networkx"  → graph_store (legacy NetworkX)
"""
from app.core.config import get_settings

settings = get_settings()

# ── Active Vector Store ───────────────────────────────────────────────────────
if settings.VECTOR_STORE_BACKEND == "pinecone" or bool(settings.PINECONE_API_KEY):
    from .pinecone_store import PineconeVectorStore as _VS
    active_vector_store = _VS()
elif settings.VECTOR_STORE_BACKEND == "faiss":
    from .faiss_store import FAISSVectorStore as _VS
    active_vector_store = _VS()
else:
    from app.rag.vector_store import VectorStore as _VS  # type: ignore
    active_vector_store = _VS()

# ── Active Graph Store ────────────────────────────────────────────────────────
if settings.GRAPH_STORE_BACKEND == "json_kv":
    from .graph_kv import GraphKVStore as _GS
    active_graph_store = _GS()
else:
    from app.rag.graph_store import graph_store as active_graph_store  # type: ignore

__all__ = ["active_vector_store", "active_graph_store"]

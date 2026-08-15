from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Deep Tutor API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "deep-tutor-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./deep_tutor.db"

    # ── LLM / Chat (Ollama local) ────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.1"      # or qwen2.5, phi3.5, gemma2
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_NUM_CTX: int = 4096
    OLLAMA_NUM_PREDICT: int = 2048

    # ── Stage 2: Embedding Provider ─────────────────────────────────────────
    # Switch via .env: EMBEDDING_PROVIDER=ollama | openai | gemini
    EMBEDDING_PROVIDER: str = "ollama"
    OPENAI_API_KEY: str = ""
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"   # or text-embedding-3-large
    GEMINI_API_KEY: str = ""
    GEMINI_EMBED_MODEL: str = "models/text-embedding-004"

    # ── Stage 3: Vector Store Backend ───────────────────────────────────────
    # Switch via .env: VECTOR_STORE_BACKEND=faiss | chroma
    VECTOR_STORE_BACKEND: str = "faiss"
    FAISS_DATA_DIR: str = "./faiss_data"
    FAISS_INDEX_TYPE: str = "hnsw"           # "hnsw" | "flat"
    FAISS_HNSW_M: int = 32                   # HNSW graph connectivity degree
    FAISS_HNSW_EF_CONSTRUCTION: int = 200    # HNSW build-time accuracy
    FAISS_HNSW_EF_SEARCH: int = 64          # HNSW search-time accuracy
    # Fallback ChromaDB config (used when VECTOR_STORE_BACKEND=chroma)
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # ── Stage 3: Graph Store Backend ────────────────────────────────────────
    # Switch via .env: GRAPH_STORE_BACKEND=json_kv | networkx
    GRAPH_STORE_BACKEND: str = "json_kv"
    LIGHTRAG_DATA_DIR: str = "./lightrag_data"
    # Legacy NetworkX store
    GRAPH_DATA_DIR: str = "./graph_data"

    # ── Stage 1: Document Parser ────────────────────────────────────────────
    # Switch via .env: PRIMARY_PARSER=pymupdf | docling | pdfplumber
    PRIMARY_PARSER: str = "pymupdf"
    ENABLE_DOCLING: bool = False             # Enable IBM Docling (slow, ML-based)
    DOCLING_TIMEOUT_SECONDS: int = 12
    DOCLING_ENABLE_OCR: bool = True
    DOCLING_OCR_ENGINE: str = "easyocr"     # "easyocr" | "tesseract" | "rapidocr"

    # ── Stage 1: Semantic Chunking (Fast 350–650 words per chunk) ───────────
    CHUNKING_STRATEGY: str = "semantic"      # "semantic" | "sliding_window" | "hierarchical"
    CHUNK_MIN_WORDS: int = 350               # min words per chunk
    CHUNK_MAX_WORDS: int = 650              # max words per chunk
    CHUNK_SIZE: int = 400                    # legacy token target (used by fallback)
    CHUNK_OVERLAP: int = 48                  # overlap tokens
    CHUNK_OVERLAP_WORDS: int = 50           # overlap in words for new chunker
    MIN_CHUNK_CHARS: int = 80               # discard chunks smaller than this

    # ── Stage 4: Retrieval & Hybrid Search (Optimized for <10s response) ────
    TOP_K_RETRIEVAL: int = 6                # candidates fetched before reranking
    TOP_K_CHUNKS: int = 3                   # final chunks sent to LLM (fast prefill <200ms)
    MIN_CHUNK_SCORE: float = 0.20           # similarity threshold
    DENSE_WEIGHT: float = 0.70             # dense vector weight in RRF fusion
    SPARSE_WEIGHT: float = 0.30            # BM25 weight in RRF fusion

    # Reranker
    RERANKER_TYPE: str = "bm25"             # "bm25" (instant sub-ms) | "cross_encoder"

    # Advanced retrieval toggles
    ENABLE_HYDE: bool = False               # False eliminates pre-generation delay
    ENABLE_QUERY_EXPANSION: bool = False    # False enables direct instant retrieval
    ENABLE_CONTEXTUAL_COMPRESSION: bool = True
    ENABLE_HYBRID_SEARCH: bool = True       # Dense + BM25 fusion (<10ms)

    # ── Embedding Cache ──────────────────────────────────────────────────────
    EMBEDDING_CACHE_SIZE: int = 1024
    QUERY_CACHE_TTL_SECONDS: int = 300
    QUERY_CACHE_SIZE: int = 256

    # ── Stage 2 / 4: Knowledge Graph ────────────────────────────────────────
    GRAPH_HOP_DEPTH: int = 2               # BFS hops for graph traversal
    GRAPH_TOP_ENTITIES: int = 8
    GRAPH_TOP_EDGES: int = 10
    GRAPH_TRIPLET_CONFIDENCE_THRESHOLD: float = 0.5  # min confidence for triplet storage

    # ── File Uploads & Tier Limits ───────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    FREE_MAX_UPLOAD_SIZE_MB: int = 10
    PREMIUM_MAX_UPLOAD_SIZE_MB: int = 100

    # ── Confidence / Grounding ───────────────────────────────────────────────
    MIN_CONFIDENCE_TO_STREAM: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

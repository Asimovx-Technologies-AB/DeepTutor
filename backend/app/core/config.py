from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Deep Tutor API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "deep-tutor-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./deep_tutor.db"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.2"      # or mistral, gemma2
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 120

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Graph Store
    GRAPH_DATA_DIR: str = "./graph_data"

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── RAG Core ────────────────────────────────────────────────────────────────
    # Document parsing
    ENABLE_DOCLING: bool = True           # Set True to enable IBM Docling structure parsing for complex PDFs
    DOCLING_TIMEOUT_SECONDS: int = 5      # Fast 5s timeout guard before falling back to pypdfium2/pdfplumber
    DOCLING_ENABLE_OCR: bool = True       # Enable OCR for scanned PDFs and image files (.png, .jpg, .jpeg, .webp)
    DOCLING_OCR_ENGINE: str = "easyocr"  # "easyocr" | "tesseract" | "rapidocr"

    # Chunking
    CHUNKING_STRATEGY: str = "semantic"   # "semantic" | "sliding_window" | "hierarchical"
    CHUNK_SIZE: int = 512                  # target tokens per chunk
    CHUNK_OVERLAP: int = 64               # overlap in tokens
    MIN_CHUNK_CHARS: int = 100            # discard chunks smaller than this

    # Retrieval
    TOP_K_RETRIEVAL: int = 10             # candidates fetched before reranking
    TOP_K_CHUNKS: int = 5                 # final chunks sent to LLM after reranking
    MIN_CHUNK_SCORE: float = 0.20         # cosine-score threshold — drop below this

    # Hybrid Search weights (dense + sparse BM25)
    DENSE_WEIGHT: float = 0.70            # weight for dense vector score in RRF fusion
    SPARSE_WEIGHT: float = 0.30           # weight for BM25 score in RRF fusion

    # Reranker
    RERANKER_TYPE: str = "bm25"           # "bm25" (fast) | "cross_encoder" (accurate)

    # Advanced retrieval techniques
    ENABLE_HYDE: bool = True              # Hypothetical Document Embedding
    ENABLE_QUERY_EXPANSION: bool = True   # Multi-query expansion (3 variants)
    ENABLE_CONTEXTUAL_COMPRESSION: bool = True  # Trim irrelevant sentences
    ENABLE_HYBRID_SEARCH: bool = True     # Dense + BM25 fusion

    # Embedding cache
    EMBEDDING_CACHE_SIZE: int = 1024      # max entries in embedding LRU cache
    QUERY_CACHE_TTL_SECONDS: int = 300    # query-result cache TTL (5 min)
    QUERY_CACHE_SIZE: int = 256           # max query result cache entries

    # Knowledge Graph
    GRAPH_HOP_DEPTH: int = 2
    GRAPH_TOP_ENTITIES: int = 8
    GRAPH_TOP_EDGES: int = 10

    # Confidence / grounding
    MIN_CONFIDENCE_TO_STREAM: float = 0.0  # Set >0 to block low-confidence answers


@lru_cache
def get_settings() -> Settings:
    return Settings()

import hashlib
import time
import logging
from typing import List
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Embedding Service supporting configurable providers:
    - local: deterministic, normalized pseudo-semantic vectors based on token hashes
    - openai: text-embedding-3-small / text-embedding-ada-002
    - gemini: text-embedding-004 / gemini-embedding-001
    """

    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER
        self.dimension = settings.EMBEDDING_DIMENSION
        self._cache = {}
        self._max_cache_size = 1024
        self._gemini_client = None
        self._working_model = settings.EMBEDDING_MODEL or "gemini-embedding-001"
        self._last_working_model = self._working_model
        self._gemini_quota_exceeded_until = 0.0

    def _get_gemini_client(self):
        if self._gemini_client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._genai = genai
                self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client for embeddings: {e}")
        return self._gemini_client

    def embed_text(self, text: str) -> List[float]:
        """Generates a normalized embedding vector for a single string with LRU caching."""
        cache_key = text.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        res = self.embed_batch([text])[0]
        if len(self._cache) >= self._max_cache_size:
            # Drop oldest key
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[cache_key] = res
        return res

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates normalized embedding vectors for a batch of texts."""
        if not texts:
            return []

        # Process in chunks of 50 to avoid API payload limits
        chunk_size = 50
        if len(texts) > chunk_size:
            all_embeddings = []
            for i in range(0, len(texts), chunk_size):
                sub_batch = texts[i : i + chunk_size]
                all_embeddings.extend(self.embed_batch(sub_batch))
            return all_embeddings

        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            # If recently throttled (429), use fast working fallback immediately without blocking network calls
            if time.time() < self._gemini_quota_exceeded_until:
                return [self._generate_local_embedding(t) for t in texts]

            try:
                client = self._get_gemini_client()
                if client:
                    candidate_models = [self._working_model]
                    for fb in ["gemini-embedding-001", "gemini-embedding-2-preview"]:
                        if fb not in candidate_models:
                            candidate_models.append(fb)

                    for model_name in candidate_models:
                        try:
                            config = None
                            genai_module = getattr(self, "_genai", None)
                            if genai_module and hasattr(genai_module, "types") and hasattr(genai_module.types, "EmbedContentConfig"):
                                config = genai_module.types.EmbedContentConfig(output_dimensionality=self.dimension)
                            resp = client.models.embed_content(
                                model=model_name,
                                contents=texts,
                                config=config,
                            )
                            if hasattr(resp, "embeddings") and resp.embeddings:
                                self._working_model = model_name
                                self._last_working_model = model_name
                                self._gemini_quota_exceeded_until = 0.0
                                return [list(e.values) for e in resp.embeddings]
                        except Exception as me:
                            err_str = str(me).lower()
                            if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                                self._gemini_quota_exceeded_until = time.time() + 300.0
                                logger.warning(f"Gemini embedding quota exceeded (429). Activating sticky fallback to local embeddings for 5 minutes.")
                                return [self._generate_local_embedding(t) for t in texts]
                            if "404" in err_str or "not found" in err_str:
                                continue
                            raise me
            except Exception as e:
                logger.warning(f"Gemini embedding call failed: {e}. Falling back to local deterministic embeddings.")

        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                resp = client.embeddings.create(
                    model=settings.EMBEDDING_MODEL,
                    input=texts
                )
                return [d.embedding for d in resp.data]
            except Exception as e:
                logger.warning(f"OpenAI embedding call failed: {e}. Falling back to local deterministic embeddings.")

        # Local deterministic normalized embedding generator
        return [self._generate_local_embedding(t) for t in texts]

    def _generate_local_embedding(self, text: str) -> List[float]:
        """Generates a deterministic pseudo-semantic vector from token n-grams and hashing."""
        vec = np.zeros(self.dimension, dtype=np.float32)
        words = text.lower().split()
        if not words:
            return vec.tolist()

        for word in words:
            # Hash word to dimensional bucket
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h // self.dimension) % 2 == 0 else -1.0
            vec[idx] += sign

        # L2 normalization
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


default_embedding_service = EmbeddingService()

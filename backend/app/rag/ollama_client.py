"""
Async Ollama API client with integrated EmbeddingCache.
Supports: chat, streaming chat, embeddings (cached).
Ollama must be running: `ollama serve`
"""
import json
import httpx
from typing import AsyncGenerator, List, Dict, Optional
from app.core.config import get_settings

settings = get_settings()


class OllamaClient:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.chat_model = settings.OLLAMA_CHAT_MODEL
        self.embed_model = settings.OLLAMA_EMBED_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self._cache = None  # lazy import to avoid circular dep

    @property
    def _embedding_cache(self):
        """Lazy-load cache to avoid circular imports at module level."""
        if self._cache is None:
            from app.rag.cache import embedding_cache
            self._cache = embedding_cache
        return self._cache

    async def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def get_available_models(self) -> List[str]:
        """Get list of installed model names from Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    models = r.json().get("models", [])
                    names = []
                    for m in models:
                        name = m.get("name", "")
                        if name:
                            names.append(name)
                            if ":" in name:
                                names.append(name.split(":")[0])
                    return names
        except Exception:
            pass
        return []

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        """Resolve a working chat model name against installed Ollama models."""
        target = requested_model or self.chat_model
        available = await self.get_available_models()
        if not available:
            return target

        if target in available or f"{target}:latest" in available:
            return target

        # Fallback candidates order
        for fallback in ["llama3.1", "llama3", "llama3.2", "mistral", "gemma2", "qwen2.5", "deepseek-r1", "phi3", "llama2"]:
            if fallback in available or f"{fallback}:latest" in available:
                return fallback

        # If no known candidate matched, use the first model installed in Ollama
        if available:
            return available[0]

        return target


    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Single (non-streaming) chat response."""
        resolved_model = await self.get_working_chat_model(model)
        payload = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
                "num_predict": 2048,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data["message"]["content"]

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[str, None]:
        """Async generator: yields tokens one by one."""
        resolved_model = await self.get_working_chat_model(model)
        payload = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
                "num_predict": 1024,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            error_msg = f"⚠️ Ollama model error ({resolved_model}): {str(e)}"
            print(f"[OLLAMA ERROR] {error_msg}")
            raise RuntimeError(error_msg) from e

    async def get_working_embed_model(self, requested_model: Optional[str] = None) -> str:
        """Resolve a working embed model name against installed Ollama models."""
        target = requested_model or self.embed_model
        available = await self.get_available_models()
        if not available:
            return target

        if target in available or f"{target}:latest" in available:
            return target

        for fallback in ["nomic-embed-text", "all-minilm", "bge-m3", "mxbai-embed-large"]:
            if fallback in available or f"{fallback}:latest" in available:
                return fallback

        return target

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Get embedding vector for text.
        Checks EmbeddingCache first — avoids redundant Ollama calls for identical text.
        Falls back to deterministic pseudo-embedding if Ollama is offline.
        """
        resolved_model = await self.get_working_embed_model(model)

        # Check cache first
        cached = await self._embedding_cache.get(text, resolved_model)
        if cached is not None:
            return cached

        payload = {"model": resolved_model, "prompt": text}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload,
                )
                r.raise_for_status()
                embedding = r.json()["embedding"]
                # Store in cache
                await self._embedding_cache.set(text, resolved_model, embedding)
                return embedding
        except Exception:
            # Deterministic pseudo-embedding for testing when Ollama is offline
            import hashlib
            h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
            pseudo = [((h + i) % 1000) / 1000.0 for i in range(768)]
            await self._embedding_cache.set(text, resolved_model, pseudo)
            return pseudo

    async def embed_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """
        Embed multiple texts concurrently.
        - Checks cache for each text first (avoids redundant calls)
        - Uses semaphore to limit parallel Ollama requests
        """
        import asyncio
        semaphore = asyncio.Semaphore(15)  # 15 concurrent embeddings

        async def _sem_embed(text: str) -> List[float]:
            async with semaphore:
                return await self.embed(text, model)

        return await asyncio.gather(*[_sem_embed(t) for t in texts])


# Singleton
ollama = OllamaClient()

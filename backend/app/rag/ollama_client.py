"""
Async Ollama API client with integrated EmbeddingCache.
Supports: chat, streaming chat, embeddings (cached).
Ollama must be running: `ollama serve`
"""
import json
import asyncio
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
        self._resolved_chat_model: Optional[str] = None
        self._resolved_embed_model: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop = None

    def _get_client(self) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None 
            or self._client.is_closed 
            or self._client_loop != current_loop
        ):
            self._client_loop = current_loop
            limits = httpx.Limits(max_keepalive_connections=30, max_connections=60)
            self._client = httpx.AsyncClient(timeout=self.timeout, limits=limits)
        return self._client

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
            client = self._get_client()
            r = await client.get(f"{self.base_url}/api/tags")
            return r.status_code == 200
        except Exception:
            return False

    async def get_available_models(self) -> List[str]:
        """Get list of installed model names from Ollama."""
        try:
            client = self._get_client()
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
        if requested_model is None and self._resolved_chat_model is not None:
            return self._resolved_chat_model

        target = requested_model or self.chat_model
        available = await self.get_available_models()
        res = target
        if available:
            if target in available or f"{target}:latest" in available:
                res = target
            else:
                for fallback in ["llama3.1", "llama3", "llama3.2", "mistral", "gemma2", "qwen2.5", "deepseek-r1", "phi3", "llama2"]:
                    if fallback in available or f"{fallback}:latest" in available:
                        res = fallback
                        break
                else:
                    res = available[0]

        if requested_model is None:
            self._resolved_chat_model = res
        return res


    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        """Single (non-streaming) chat response with connection pool & warm keep_alive."""
        resolved_model = await self.get_working_chat_model(model)
        opts = {
            "temperature": temperature,
            "num_ctx": getattr(settings, "OLLAMA_NUM_CTX", 4096),
            "num_predict": getattr(settings, "OLLAMA_NUM_PREDICT", 2048),
            "top_k": 20,
            "top_p": 0.85,
            "repeat_penalty": 1.1,
        }
        if options:
            opts.update(options)

        payload = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": opts,
        }
        client = self._get_client()
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
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator: yields tokens one by one with warm keep_alive."""
        resolved_model = await self.get_working_chat_model(model)
        opts = {
            "temperature": temperature,
            "num_ctx": getattr(settings, "OLLAMA_NUM_CTX", 4096),
            "num_predict": getattr(settings, "OLLAMA_NUM_PREDICT", 2048),
            "top_k": 20,
            "top_p": 0.85,
            "repeat_penalty": 1.1,
        }
        if options:
            opts.update(options)

        payload = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": opts,
        }
        try:
            client = self._get_client()
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
        if requested_model is None and self._resolved_embed_model is not None:
            return self._resolved_embed_model

        target = requested_model or self.embed_model
        available = await self.get_available_models()
        res = target
        if available:
            if target in available or f"{target}:latest" in available:
                res = target
            else:
                for fallback in ["nomic-embed-text", "all-minilm", "bge-m3", "mxbai-embed-large"]:
                    if fallback in available or f"{fallback}:latest" in available:
                        res = fallback
                        break

        if requested_model is None:
            self._resolved_embed_model = res
        return res

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

        payload = {"model": resolved_model, "prompt": text, "keep_alive": "15m"}
        try:
            client = self._get_client()
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


class UnifiedLLMClient:
    """
    Unified LLM Client that seamlessly delegates to GeminiClient or OllamaClient
    based on settings.LLM_PROVIDER (defaults to 'gemini').
    Preserves 100% backward compatibility for all modules importing `ollama`.
    """
    def __init__(self):
        self.ollama_client = OllamaClient()

    @property
    def provider(self) -> str:
        return getattr(settings, "LLM_PROVIDER", "gemini").lower()

    async def is_available(self) -> bool:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            if await gemini.is_available():
                return True
            # Fallback check if Ollama is running
            return await self.ollama_client.is_available()
        return await self.ollama_client.is_available()

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            return await gemini.get_working_chat_model(requested_model)
        return await self.ollama_client.get_working_chat_model(requested_model)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            if await gemini.is_available():
                try:
                    return await gemini.chat(messages, model, temperature, options)
                except Exception as e:
                    print(f"[UnifiedLLMClient] Gemini chat call failed: {e}. Attempting Ollama fallback...")
        return await self.ollama_client.chat(messages, model, temperature, options)

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            if await gemini.is_available():
                async for token in gemini.stream(messages, model, temperature, options):
                    yield token
                return
        async for token in self.ollama_client.stream(messages, model, temperature, options):
            yield token

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            if await gemini.is_available():
                return await gemini.embed(text, model)
        return await self.ollama_client.embed(text, model)

    async def embed_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        if self.provider == "gemini":
            from app.rag.gemini_client import gemini
            if await gemini.is_available():
                return await gemini.embed_batch(texts, model)
        return await self.ollama_client.embed_batch(texts, model)


# Singleton — provides backward compatibility for all existing callers
ollama = UnifiedLLMClient()
llm = ollama


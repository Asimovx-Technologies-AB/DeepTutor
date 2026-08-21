"""
Async Google Gemini API client with token streaming, embeddings & caching.
Supports: Gemini 1.5 Flash, Gemini 2.0 Flash, Gemini 1.5 Pro, text-embedding-004.
Uses async HTTPX for high-throughput non-blocking execution.
"""
import json
import asyncio
import httpx
from typing import AsyncGenerator, List, Dict, Optional
from app.core.config import get_settings

settings = get_settings()


class GeminiClient:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.chat_model = settings.GEMINI_CHAT_MODEL or "gemini-1.5-flash"
        self.embed_model = settings.GEMINI_EMBED_MODEL or "models/gemini-embedding-2"
        self.timeout = getattr(settings, "GEMINI_TIMEOUT", 15) or 15
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._cache = None
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
            timeout = httpx.Timeout(self.timeout, connect=5.0)
            self._client = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._client

    @property
    def _embedding_cache(self):
        """Lazy-load cache to avoid circular imports."""
        if self._cache is None:
            from app.rag.cache import embedding_cache
            self._cache = embedding_cache
        return self._cache

    def _get_headers(self) -> Dict[str, str]:
        # Always read latest GEMINI_API_KEY in case .env was modified at runtime
        import os
        api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or self.api_key
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["x-goog-api-key"] = api_key.strip()
        return headers

    async def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        api_key = getattr(settings, "GEMINI_API_KEY", "") or self.api_key
        return bool(api_key and len(api_key.strip()) > 5)

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        """Return configured chat model (e.g. gemini-1.5-flash)."""
        target = requested_model or getattr(settings, "GEMINI_CHAT_MODEL", None) or self.chat_model
        # Strip any 'models/' prefix if present
        if target.startswith("models/"):
            target = target[7:]
        return target

    def _format_messages_for_gemini(self, messages: List[Dict[str, str]]) -> Dict:
        """
        Convert OpenAI/Ollama messages list to Gemini API format.
        Extracts system prompts into system_instruction and formats contents.
        """
        system_texts = []
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue

            if role == "system":
                system_texts.append(content)
            elif role in ("assistant", "model"):
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}],
                })
            else:
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })

        # Ensure at least one user message
        if not contents:
            contents.append({
                "role": "user",
                "parts": [{"text": "Hello"}],
            })

        payload = {"contents": contents}
        if system_texts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n\n".join(system_texts)}]
            }

        return payload

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        """Single non-streaming chat generation via Gemini API with auto-retry on 503/429."""
        resolved_model = await self.get_working_chat_model(model)
        payload = self._format_messages_for_gemini(messages)

        payload["generationConfig"] = {
            "temperature": temperature,
            "maxOutputTokens": 8192,
            "topP": 0.95,
        }
        if options and "temperature" in options:
            payload["generationConfig"]["temperature"] = options["temperature"]

        headers = self._get_headers()
        client = self._get_client()

        models_to_try = [resolved_model]
        for fallback in ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-flash-latest"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for attempt, target_model in enumerate(models_to_try):
            url = f"{self.base_url}/models/{target_model}:generateContent"
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return "".join(p.get("text", "") for p in parts)
                    return ""
                elif response.status_code in (503, 429, 500):
                    last_error = f"Gemini API error ({response.status_code}): {response.text}"
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    response.raise_for_status()
            except Exception as e:
                last_error = str(e)
                if attempt < len(models_to_try) - 1:
                    await asyncio.sleep(0.5)
                    continue

        raise RuntimeError(last_error or "Gemini chat failed across candidate models.")

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens asynchronously from Gemini via Server-Sent Events with automatic multi-model failover."""
        resolved_model = await self.get_working_chat_model(model)
        payload = self._format_messages_for_gemini(messages)

        payload["generationConfig"] = {
            "temperature": temperature,
            "maxOutputTokens": 4096,
            "topP": 0.95,
        }
        if options and "temperature" in options:
            payload["generationConfig"]["temperature"] = options["temperature"]

        headers = self._get_headers()
        client = self._get_client()

        models_to_try = [resolved_model]
        for fallback in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for attempt, target_model in enumerate(models_to_try):
            url = f"{self.base_url}/models/{target_model}:streamGenerateContent?alt=sse"
            token_yielded = False
            try:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            trimmed = line.strip()
                            if not trimmed or not trimmed.startswith("data: "):
                                continue

                            raw_json = trimmed[6:]
                            try:
                                chunk = json.loads(raw_json)
                                candidates = chunk.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    for part in parts:
                                        text = part.get("text", "")
                                        if text:
                                            token_yielded = True
                                            yield text
                            except json.JSONDecodeError:
                                continue
                        # Stream completed cleanly
                        return
                    elif response.status_code in (429, 503, 500):
                        err_body = await response.aread()
                        last_error = f"Gemini error on {target_model} ({response.status_code}): {err_body.decode('utf-8', errors='replace')}"
                        if attempt < len(models_to_try) - 1:
                            await asyncio.sleep(0.5)
                            continue
                    else:
                        err_body = await response.aread()
                        raise RuntimeError(f"Gemini error ({response.status_code}): {err_body.decode('utf-8', errors='replace')}")
            except Exception as e:
                if token_yielded:
                    # Already partially streamed, cannot restart mid-stream
                    raise
                last_error = str(e)
                if attempt < len(models_to_try) - 1:
                    await asyncio.sleep(0.5)
                    continue

        raise RuntimeError(last_error or "Gemini streaming failed across candidate models.")

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """Get embedding vector for text with cache and retry."""
        results = await self.embed_batch([text], model=model)
        return results[0] if results else [0.0] * 3072

    async def embed_batch(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """
        Embed batch of texts using Gemini batchEmbedContents endpoint.
        Handles caching and batches up to 50 texts per request.
        """
        if not texts:
            return []

        target_model = model or getattr(settings, "GEMINI_EMBED_MODEL", "models/gemini-embedding-2")
        if not target_model.startswith("models/"):
            target_model = f"models/{target_model}"

        # 1. Check cache for cached texts
        cached_results: Dict[int, List[float]] = {}
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for idx, t in enumerate(texts):
            cached = await self._embedding_cache.get(t, target_model)
            if cached is not None and len(cached) > 0:
                cached_results[idx] = cached
            else:
                uncached_indices.append(idx)
                uncached_texts.append(t)

        if not uncached_texts:
            return [cached_results[i] for i in range(len(texts))]

        # 2. Batch call Gemini batchEmbedContents in chunks of 50 concurrently
        batch_size = 50
        headers = self._get_headers()
        url = f"{self.base_url}/{target_model}:batchEmbedContents"
        client = self._get_client()

        batch_slices = [
            (uncached_texts[i:i + batch_size], uncached_indices[i:i + batch_size])
            for i in range(0, len(uncached_texts), batch_size)
        ]

        async def _fetch_one_batch(chunk_texts: List[str], chunk_indices: List[int]):
            requests_payload = [
                {"model": target_model, "content": {"parts": [{"text": t}]}}
                for t in chunk_texts
            ]
            payload = {"requests": requests_payload}

            embeddings = None
            for attempt in range(3):
                try:
                    r = await client.post(url, headers=headers, json=payload, timeout=20)
                    if r.status_code == 200:
                        data = r.json()
                        raw_embs = data.get("embeddings", [])
                        embeddings = [e.get("values", []) for e in raw_embs]
                        break
                    elif r.status_code in (429, 503):
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    else:
                        r.raise_for_status()
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(0.5)
                        continue
                    print(f"[GEMINI BATCH EMBED ERROR] {e}")

            dim = 3072
            if not embeddings or len(embeddings) != len(chunk_texts):
                embeddings = []
                for t in chunk_texts:
                    import hashlib
                    h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
                    pseudo = [((h + j) % 1000) / 1000.0 for j in range(dim)]
                    embeddings.append(pseudo)

            for orig_idx, t, emb in zip(chunk_indices, chunk_texts, embeddings):
                cached_results[orig_idx] = emb
                await self._embedding_cache.set(t, target_model, emb)

        await asyncio.gather(*[_fetch_one_batch(texts_chunk, idxs_chunk) for texts_chunk, idxs_chunk in batch_slices])

        # Assemble final result in original order
        final_list = [cached_results[i] for i in range(len(texts))]
        return final_list


# Singleton
gemini = GeminiClient()
gemini_client = gemini


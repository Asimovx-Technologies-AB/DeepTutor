"""Azure OpenAI client using managed identity in Azure and an optional local key."""
from __future__ import annotations

from typing import AsyncGenerator, Dict, List, Optional

from app.core.config import get_settings

settings = get_settings()


class AzureOpenAIClient:
    def __init__(self) -> None:
        self._client = None
        self._credential = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT is not configured")

        from openai import AsyncAzureOpenAI

        common = {
            "azure_endpoint": settings.AZURE_OPENAI_ENDPOINT,
            "api_version": settings.AZURE_OPENAI_API_VERSION,
        }
        if settings.AZURE_OPENAI_API_KEY:
            common["api_key"] = settings.AZURE_OPENAI_API_KEY
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            self._credential = DefaultAzureCredential(
                managed_identity_client_id=getattr(settings, "AZURE_CLIENT_ID", None) or None,
            )
            common["azure_ad_token_provider"] = get_bearer_token_provider(
                self._credential,
                "https://cognitiveservices.azure.com/.default",
            )
        self._client = AsyncAzureOpenAI(**common)
        return self._client

    async def is_available(self) -> bool:
        return bool(settings.AZURE_OPENAI_ENDPOINT)

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        return requested_model or settings.AZURE_OPENAI_CHAT_DEPLOYMENT

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        response = await self._get_client().chat.completions.create(
            model=model or settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        stream = await self._get_client().chat.completions.create(
            model=model or settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content if chunk.choices else None
            if token:
                yield token

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        vectors = await self.embed_batch([text], model)
        return vectors[0]

    async def embed_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        response = await self._get_client().embeddings.create(
            model=model or settings.AZURE_OPENAI_EMBED_DEPLOYMENT,
            input=texts,
            dimensions=settings.PGVECTOR_DIMENSIONS,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


azure_openai = AzureOpenAIClient()

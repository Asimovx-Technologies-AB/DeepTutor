"""
Azure OpenAI & OpenAI client supporting managed identity / API keys, streaming, vision, and embeddings.
"""
from __future__ import annotations

import base64
import os
from typing import AsyncGenerator, Dict, List, Optional, Any
from pathlib import Path
from dotenv import dotenv_values

from app.core.config import get_settings

settings = get_settings()


def _get_active_env_var(name: str, default: str = "") -> str:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        vals = dotenv_values(env_path)
        val = vals.get(name, "")
        if val and val.strip():
            return val.strip()
    return os.environ.get(name) or getattr(settings, name, default) or default


class AzureOpenAIClient:
    """Client for Azure OpenAI Service."""

    def __init__(self) -> None:
        self._client = None
        self._credential = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        endpoint = _get_active_env_var("AZURE_OPENAI_ENDPOINT", settings.AZURE_OPENAI_ENDPOINT)
        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT is not configured")

        from openai import AsyncAzureOpenAI

        api_key = _get_active_env_var("AZURE_OPENAI_API_KEY", settings.AZURE_OPENAI_API_KEY)
        api_version = _get_active_env_var("AZURE_OPENAI_API_VERSION", settings.AZURE_OPENAI_API_VERSION)

        common: Dict[str, Any] = {
            "azure_endpoint": endpoint,
            "api_version": api_version,
        }
        if api_key:
            common["api_key"] = api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            client_id = _get_active_env_var("AZURE_CLIENT_ID", getattr(settings, "AZURE_CLIENT_ID", "") or "")
            self._credential = DefaultAzureCredential(
                managed_identity_client_id=client_id or None,
            )
            common["azure_ad_token_provider"] = get_bearer_token_provider(
                self._credential,
                "https://cognitiveservices.azure.com/.default",
            )
        self._client = AsyncAzureOpenAI(**common)
        return self._client

    async def is_available(self) -> bool:
        endpoint = _get_active_env_var("AZURE_OPENAI_ENDPOINT", settings.AZURE_OPENAI_ENDPOINT)
        return bool(endpoint and len(endpoint.strip()) > 5)

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        return requested_model or _get_active_env_var("AZURE_OPENAI_CHAT_DEPLOYMENT", settings.AZURE_OPENAI_CHAT_DEPLOYMENT)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        dep = model or _get_active_env_var("AZURE_OPENAI_CHAT_DEPLOYMENT", settings.AZURE_OPENAI_CHAT_DEPLOYMENT)
        client = self._get_client()
        response = await client.chat.completions.create(
            model=dep,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        dep = model or _get_active_env_var("AZURE_OPENAI_CHAT_DEPLOYMENT", settings.AZURE_OPENAI_CHAT_DEPLOYMENT)
        client = self._get_client()
        stream_resp = await client.chat.completions.create(
            model=dep,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
            stream=True,
        )
        async for chunk in stream_resp:
            token = chunk.choices[0].delta.content if chunk.choices else None
            if token:
                yield token

    async def chat_vision(
        self,
        prompt: str,
        image_bytes: bytes,
        system_instruction: str = "",
        temperature: float = 0.1,
        model: Optional[str] = None,
    ) -> str:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        messages: List[Dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_img}"
                    }
                }
            ]
        })
        return await self.chat(messages, model=model, temperature=temperature)

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        vectors = await self.embed_batch([text], model)
        return vectors[0]

    async def embed_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        dep = model or _get_active_env_var("AZURE_OPENAI_EMBED_DEPLOYMENT", settings.AZURE_OPENAI_EMBED_DEPLOYMENT)
        client = self._get_client()
        response = await client.embeddings.create(
            model=dep,
            input=texts,
            dimensions=settings.PGVECTOR_DIMENSIONS,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class OpenAIClient:
    """Client for direct OpenAI API (standard public OpenAI)."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = _get_active_env_var("OPENAI_API_KEY", settings.OPENAI_API_KEY)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        from openai import AsyncOpenAI

        base_url = _get_active_env_var("OPENAI_BASE_URL", settings.OPENAI_BASE_URL)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url if base_url else None)
        return self._client

    async def is_available(self) -> bool:
        key = _get_active_env_var("OPENAI_API_KEY", settings.OPENAI_API_KEY)
        return bool(key and len(key.strip()) > 10 and key != "your_openai_api_key_here")

    async def get_working_chat_model(self, requested_model: Optional[str] = None) -> str:
        return requested_model or _get_active_env_var("OPENAI_CHAT_MODEL", settings.OPENAI_CHAT_MODEL)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> str:
        m = model or _get_active_env_var("OPENAI_CHAT_MODEL", settings.OPENAI_CHAT_MODEL)
        client = self._get_client()
        response = await client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        options: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        m = model or _get_active_env_var("OPENAI_CHAT_MODEL", settings.OPENAI_CHAT_MODEL)
        client = self._get_client()
        stream_resp = await client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=(options or {}).get("temperature", temperature),
            max_tokens=4096,
            stream=True,
        )
        async for chunk in stream_resp:
            token = chunk.choices[0].delta.content if chunk.choices else None
            if token:
                yield token

    async def chat_vision(
        self,
        prompt: str,
        image_bytes: bytes,
        system_instruction: str = "",
        temperature: float = 0.1,
        model: Optional[str] = None,
    ) -> str:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        messages: List[Dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64_img}"
                    }
                }
            ]
        })
        vlm_model = model or _get_active_env_var("OPENAI_VLM_MODEL", settings.OPENAI_VLM_MODEL)
        return await self.chat(messages, model=vlm_model, temperature=temperature)

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        vectors = await self.embed_batch([text], model)
        return vectors[0]

    async def embed_batch(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        m = model or _get_active_env_var("OPENAI_EMBED_MODEL", settings.OPENAI_EMBED_MODEL)
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": m,
            "input": texts,
        }
        # text-embedding-3 supports dimensions parameter
        if settings.PGVECTOR_DIMENSIONS in (512, 768, 1536, 3072):
            kwargs["dimensions"] = settings.PGVECTOR_DIMENSIONS
        response = await client.embeddings.create(**kwargs)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


azure_openai = AzureOpenAIClient()
openai_client = OpenAIClient()

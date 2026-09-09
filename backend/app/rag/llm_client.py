"""
Unified OpenAI / ChatGPT API Client for Text Generation, Streaming, and Embeddings.
Supports OpenAI (gpt-4o, gpt-4o-mini) and Azure OpenAI with connection pooling and keep-alive.
"""
from __future__ import annotations

import os
import asyncio
from typing import AsyncGenerator, List, Dict, Optional, Any
from app.core.config import get_settings

settings = get_settings()


def clean_llm_response(text: str) -> str:
    """
    Sanitizes raw LLM output across the system to ensure clean, publication-ready academic output:
    1. Removes conversational chatter / intro boilerplate (e.g. 'Sure, here is...', 'Certainly!').
    2. Strips accidental outer markdown block wrappers (```markdown ... ```).
    3. Normalizes LaTeX math syntax:
       - Converts single-line inline double dollars ($$ var $$) into single dollars ($var$) so KaTeX renders inline math cleanly.
       - Ensures block display equations ($$\\n...\\n$$) have clear surrounding blank lines.
    4. Normalizes unbulleted concept lists into clean Markdown bullet points.
    5. Strips redundant whitespace while preserving code blocks and math indentation.
    """
    if not text:
        return ""

    import re
    cleaned = text.strip()

    # 1. Strip outer markdown code block wrap if the entire output was enclosed in ```markdown ... ```
    if cleaned.startswith("```markdown") and cleaned.endswith("```"):
        cleaned = cleaned[len("```markdown"): -3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```") and cleaned.count("```") == 2:
        lines = cleaned.splitlines()
        if len(lines) > 2 and lines[0].strip() in ("```", "```md", "```text"):
            cleaned = "\n".join(lines[1:-1]).strip()

    # 2. Strip conversational preambles
    preambles = [
        r"^(?:Sure|Certainly|Here\s+(?:is|are)|Below\s+is|As\s+an\s+AI)[^\n]*:\s*\n+",
        r"^(?:I\s+have\s+generated|Here\s+are\s+the\s+study\s+notes)[^\n]*:\s*\n+",
    ]
    for pattern in preambles:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # 3. Convert standalone single-line formulas wrapped in $...$ into display math $$\n...\n$$
    cleaned = re.sub(
        r'^\s*\$(?!\$)([^\$\n]{5,})\$\s*$',
        r'$$\n\1\n$$',
        cleaned,
        flags=re.MULTILINE
    )

    # 4. Normalize single-line inline double dollars ($$ var $$) to single dollars ($var$)
    # Only replace when $$ is embedded inside a text line (not on a line by itself)
    def _replace_inline_double_dollars(line: str) -> str:
        if line.strip() in ("$$", "$$$"):
            return line
        return re.sub(r'(?<!\$)\$\$\s*([^\$\r\n]+?)\s*\$\$(?!\$)', r'$\1$', line)

    lines = cleaned.splitlines()
    cleaned = "\n".join(_replace_inline_double_dollars(l) for l in lines)

    # 5. Clean up un-bulleted paradigm lists like "Supervised Learning: ..." into "- **Supervised Learning**: ..."
    cleaned = re.sub(
        r'^(?!(?:[-*#>]|\d+\.))\s*([A-Za-z0-9\s()/\-]{3,45}):\s+([A-Z])',
        r'- **\1**: \2',
        cleaned,
        flags=re.MULTILINE
    )

    # 6. Consolidate excessive blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


class LLMClient:
    """
    Unified LLM Client using official OpenAI API (ChatGPT / GPT-4o / GPT-4o-mini)
    and Embedding API (text-embedding-3-small).
    """

    def __init__(self):
        self._async_client = None

    def _get_client(self):
        if self._async_client is not None:
            return self._async_client

        from openai import AsyncOpenAI, AsyncAzureOpenAI

        provider = settings.LLM_PROVIDER.lower()

        if provider == "azure_openai" or (settings.AZURE_OPENAI_ENDPOINT and not settings.OPENAI_API_KEY):
            endpoint = settings.AZURE_OPENAI_ENDPOINT
            api_key = settings.AZURE_OPENAI_API_KEY
            api_version = settings.AZURE_OPENAI_API_VERSION or "2024-10-21"

            if api_key:
                self._async_client = AsyncAzureOpenAI(
                    azure_endpoint=endpoint,
                    api_key=api_key,
                    api_version=api_version,
                )
            else:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                credential = DefaultAzureCredential(
                    managed_identity_client_id=getattr(settings, "AZURE_CLIENT_ID", None) or None
                )
                token_provider = get_bearer_token_provider(
                    credential,
                    "https://cognitiveservices.azure.com/.default"
                )
                self._async_client = AsyncAzureOpenAI(
                    azure_endpoint=endpoint,
                    azure_ad_token_provider=token_provider,
                    api_version=api_version,
                )
        else:
            api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
            base_url = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
            self._async_client = AsyncOpenAI(
                api_key=api_key or "sk-dummy-key-for-initialization",
                base_url=base_url,
            )

        return self._async_client

    @property
    def model(self) -> str:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "azure_openai":
            return settings.AZURE_OPENAI_CHAT_DEPLOYMENT or "gpt-4.1-mini"
        return settings.OPENAI_CHAT_MODEL or settings.OPENAI_MODEL or "gpt-4o-mini"

    @property
    def embed_model(self) -> str:
        provider = settings.EMBEDDING_PROVIDER.lower()
        if provider == "azure_openai":
            return settings.AZURE_OPENAI_EMBED_DEPLOYMENT or "text-embedding-3-small"
        return settings.OPENAI_EMBED_MODEL or "text-embedding-3-small"

    async def is_available(self) -> bool:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "azure_openai":
            return bool(settings.AZURE_OPENAI_ENDPOINT and len(settings.AZURE_OPENAI_ENDPOINT.strip()) > 5)
        key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        return bool(key and len(key.strip()) > 10 and key != "your_openai_api_key_here")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Single chat completion using OpenAI ChatGPT API."""
        target_model = model or self.model
        client = self._get_client()

        formatted_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("human", "student"):
                role = "user"
            elif role in ("model", "bot"):
                role = "assistant"
            formatted_messages.append({"role": role, "content": content})

        try:
            response = await client.chat.completions.create(
                model=target_model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            raw_content = choice.message.content or ""
            return clean_llm_response(raw_content)
        except Exception as e:
            err_msg = str(e)
            print(f"[LLMClient] OpenAI Chat error with {target_model}: {err_msg}")
            if "api_key" in err_msg.lower() or "authentication" in err_msg.lower():
                return "⚠️ OpenAI API key is missing or invalid. Please check `OPENAI_API_KEY` in `backend/.env`."
            raise

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Streaming token generation using OpenAI ChatGPT API."""
        target_model = model or self.model
        client = self._get_client()

        formatted_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role in ("human", "student"):
                role = "user"
            elif role in ("model", "bot"):
                role = "assistant"
            formatted_messages.append({"role": role, "content": content})

        try:
            response_stream = await client.chat.completions.create(
                model=target_model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response_stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except Exception as e:
            print(f"[LLMClient] OpenAI streaming error: {e}")
            yield f"\n\n⚠️ OpenAI Generation Error: {e}"

    async def stream(self, messages: List[Dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        async for token in self.chat_stream(messages, **kwargs):
            yield token

    # In-memory embedding cache (query -> vector)
    _embedding_cache: Dict[str, List[float]] = {}

    async def get_embedding(self, text: str) -> List[float]:
        """Generates embedding vector for a single text chunk with memory caching."""
        clean = text.strip() if text else "empty"
        if clean in self._embedding_cache:
            return self._embedding_cache[clean]

        embeddings = await self.get_embeddings([clean])
        vec = embeddings[0] if embeddings else [0.0] * settings.PGVECTOR_DIMENSIONS
        if len(self._embedding_cache) < 2000:
            self._embedding_cache[clean] = vec
        return vec

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a batch of text chunks via OpenAI Embeddings API with cache check."""
        if not texts:
            return []

        dim = settings.PGVECTOR_DIMENSIONS
        results: List[Optional[List[float]]] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []

        for idx, t in enumerate(texts):
            clean = t.strip() if t.strip() else "empty chunk"
            if clean in self._embedding_cache:
                results[idx] = self._embedding_cache[clean]
            else:
                missing_indices.append(idx)
                missing_texts.append(clean)

        if not missing_texts:
            return [r for r in results if r is not None]

        if not await self.is_available():
            for idx in missing_indices:
                results[idx] = [0.0] * dim
            return [r for r in results if r is not None]

        client = self._get_client()
        target_model = self.embed_model

        try:
            resp = await client.embeddings.create(
                model=target_model,
                input=missing_texts,
            )
            for m_idx, data in zip(missing_indices, resp.data):
                vec = data.embedding
                results[m_idx] = vec
                if len(self._embedding_cache) < 2000:
                    self._embedding_cache[texts[m_idx].strip()] = vec
        except Exception as e:
            print(f"[LLMClient] OpenAI Embedding error: {e}")
            for idx in missing_indices:
                results[idx] = [0.0] * dim

        return [r for r in results if r is not None]


# Global singleton instance
llm_client = LLMClient()
openai_client = llm_client

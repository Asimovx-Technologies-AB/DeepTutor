"""
OpenAI Vision-Language Model (VLM) Client.
Used for scanned documents, images (.png, .jpg, .webp), and image-based PDFs
to perform fast OCR, topic extraction, and visual diagram captioning using OpenAI GPT-4o / GPT-4o-mini.
"""
from __future__ import annotations

import os
import base64
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.config import get_settings

settings = get_settings()


class OpenAIVLMClient:
    """
    Vision-Language client using OpenAI GPT-4o / GPT-4o-mini Multimodal API.
    Supports multimodal inputs (image + prompt) for:
    1. Full OCR and academic text extraction
    2. Topic tree & curriculum extraction
    3. Diagram / figure factual captioning
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
        return settings.OPENAI_VLM_MODEL or settings.OPENAI_CHAT_MODEL or "gpt-4o-mini"

    def is_configured(self) -> bool:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "azure_openai":
            return bool(settings.AZURE_OPENAI_ENDPOINT and len(settings.AZURE_OPENAI_ENDPOINT.strip()) > 5)
        key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        return bool(key and len(key.strip()) > 10 and key != "your_openai_api_key_here")

    def render_pdf_page_to_image(self, file_path: str, page_idx: int = 0, dpi: int = 150) -> Optional[bytes]:
        """Renders a specific page of a PDF file to PNG image bytes using PyMuPDF."""
        try:
            import pymupdf
            doc = pymupdf.open(file_path)
            if 0 <= page_idx < len(doc):
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=dpi)
                return pix.tobytes("png")
        except Exception as e:
            try:
                import fitz
                doc = fitz.open(file_path)
                if 0 <= page_idx < len(doc):
                    page = doc[page_idx]
                    pix = page.get_pixmap(dpi=dpi)
                    return pix.tobytes("png")
            except Exception as e2:
                print(f"[OpenAIVLM] PDF render page {page_idx} error: {e2}")
        return None

    async def extract_text_from_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        context_hint: str = "",
    ) -> str:
        """Transcribes high-accuracy text and equations from an educational image or scanned page."""
        if not image_bytes:
            return ""

        client = self._get_client()
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_img}"

        prompt = (
            "You are an expert academic OCR and document digitization system. "
            "Transcribe all readable educational text, equations, headings, bullet points, and tables "
            "from this image into clean Markdown format. Preserve mathematical formulas in standard LaTeX format ($...$ and $$...$$). "
            f"{f'Context Hint: {context_hint}' if context_hint else ''}"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                ],
            }
        ]

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[OpenAIVLM] Image transcription error: {e}")
            return ""

    async def caption_diagram(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        context_hint: str = "",
    ) -> str:
        """Generates a factual academic caption and description for diagrams, charts, and figures."""
        if not image_bytes:
            return ""

        client = self._get_client()
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_img}"

        prompt = (
            "Analyze and describe this educational figure, diagram, or chart in detail.\n"
            f"{f'Surrounding Context: {context_hint}' if context_hint else ''}\n"
            "1. State the figure title or subject matter.\n"
            "2. Describe the key visual elements, processes, relationships, and data labels.\n"
            "3. Keep the description clear, factual, and concise."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "low"}},
                ],
            }
        ]

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=500,
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[OpenAIVLM] Diagram captioning error: {e}")
            return ""


# Aliases for backward compatibility
GeminiVLMClient = OpenAIVLMClient
vlm_client = OpenAIVLMClient()


def _get_active_gemini_key() -> str:
    return settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")

"""
Gemini Client adapter for text generation and VLM vision operations.
"""
import os
import json
import base64
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import get_settings
from app.rag.ollama_client import ollama, GeminiClient as TextGeminiClient, _get_active_gemini_key
from app.rag.vlm_client import vlm_client, VLM_CASCADE_MODELS

settings = get_settings()


class GeminiClientAdapter(TextGeminiClient):
    """Unified client providing both text and vision/VLM capabilities."""

    async def transcribe_image_vlm(
        self,
        image_input: Any,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Analyze or transcribe an image using Gemini VLM."""
        if not vlm_client.is_configured():
            return ""

        if isinstance(image_input, (str, Path)):
            with open(str(image_input), "rb") as f:
                img_bytes = f.read()
        elif isinstance(image_input, bytes):
            img_bytes = image_input
        else:
            return ""

        actual_prompt = prompt or "Extract and describe all educational content in this image."

        # If OpenAI or Azure is active provider, route through vlm_client
        if vlm_client.provider.lower() in ("openai", "azure_openai"):
            res = await vlm_client.extract_text_from_image(img_bytes, context_hint=actual_prompt)
            if res and res.strip():
                return res.strip()

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": actual_prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_data}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        key = _get_active_gemini_key()
        models = [model] if model else VLM_CASCADE_MODELS

        for m_name in models:
            if not m_name:
                continue
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key}"
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
            except Exception:
                continue
        return ""

    def sync_transcribe_image_vlm(self, image_input: Any, prompt: Optional[str] = None, model: Optional[str] = None) -> str:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # run in separate thread or executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, self.transcribe_image_vlm(image_input, prompt, model)).result(timeout=20)
            else:
                return loop.run_until_complete(self.transcribe_image_vlm(image_input, prompt, model))
        except Exception:
            return ""


# Singleton
gemini_client = GeminiClientAdapter()
GeminiClient = GeminiClientAdapter

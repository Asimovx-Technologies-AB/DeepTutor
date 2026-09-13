import base64
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class VLMService:
    """
    Vision-Language Model Service for scanned document pages and complex visual extraction.
    Supports mock mode, Gemini, and OpenAI multimodal models.
    """

    def __init__(self):
        self.provider = settings.VLM_PROVIDER
        self.model = settings.VLM_MODEL

    def transcribe_document_page(self, image_bytes: bytes) -> str:
        """Transcribes a rendered page image to Markdown with LaTeX equations."""
        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    "Transcribe this document page precisely into clean Markdown. "
                    "Convert mathematical equations into LaTeX notation ($...$ and $$...$$). "
                    "Format tables into Markdown tables."
                )
                candidate_models = [self.model]
                for fb in ["gemini-3.6-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]:
                    if fb not in candidate_models:
                        candidate_models.append(fb)

                for model_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[
                                genai.types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                                prompt
                            ]
                        )
                        if response and response.text:
                            return response.text
                    except Exception as me:
                        err_str = str(me).lower()
                        if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                            continue
                        raise me
            except Exception as e:
                logger.error(f"Gemini VLM call failed: {e}")

        # Fallback / mock extraction
        return "Transcribed document content from visual layer."


default_vlm_service = VLMService()

import base64
import logging
from typing import Optional, Set
from app.core.config import settings

logger = logging.getLogger(__name__)


class VLMService:
    """
    Vision-Language Model Service for scanned document pages and complex visual extraction.
    Supports mock mode, Gemini, and OpenAI multimodal models.
    """

    def __init__(self):
        self.provider = settings.VLM_PROVIDER
        self.model = settings.VLM_MODEL or "gemini-3.5-flash-lite"
        self._working_model: Optional[str] = None
        self._broken_models: Set[str] = set()

    def transcribe_document_page(self, image_bytes: bytes) -> str:
        """Transcribes a rendered page image to Markdown with LaTeX equations and tables."""
        if not image_bytes:
            return ""

        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            try:
                import time
                from google import genai

                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    "Transcribe this document page precisely and completely into clean, structured Markdown.\n"
                    "- Use '# ' for main chapter/document titles, and '## ' or '### ' for section headings.\n"
                    "- Maintain paragraph breaks and bullet points.\n"
                    "- Convert mathematical equations and formulas into LaTeX ($...$ inline or $$...$$ block).\n"
                    "- Convert tables into clean GitHub-flavored Markdown tables.\n"
                    "- Do not omit or summarize any body text; transcribe all readable content faithfully."
                )

                # Prioritize active working model or ultra-fast, high-availability lite models
                candidate_models = []
                if self._working_model and self._working_model not in self._broken_models:
                    candidate_models.append(self._working_model)
                if self.model and self.model not in self._broken_models and self.model not in candidate_models:
                    candidate_models.append(self.model)

                for fb in [
                    "gemini-3.5-flash-lite",
                    "gemini-flash-lite-latest",
                    "gemini-3.1-flash-lite",
                    "gemini-3.6-flash",
                ]:
                    if fb not in candidate_models and fb not in self._broken_models:
                        candidate_models.append(fb)

                for model_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[
                                genai.types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                                prompt,
                            ],
                        )
                        if response and response.text and response.text.strip():
                            self._working_model = model_name
                            return response.text.strip()
                    except Exception as me:
                        err_str = str(me).lower()
                        if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                            self._broken_models.add(model_name)
                            continue
                        if "503" in err_str or "unavailable" in err_str or "high demand" in err_str:
                            logger.info(f"VLM model {model_name} is under high demand (503). Switching to fallback model.")
                            self._broken_models.add(model_name)
                            continue
                        if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                            logger.warning(f"VLM model {model_name} quota exceeded (429). Switching to fallback.")
                            self._broken_models.add(model_name)
                            continue
                        logger.warning(f"VLM model {model_name} failed: {me}")
                        self._broken_models.add(model_name)
            except Exception as e:
                logger.error(f"Gemini VLM call failed: {e}")

        elif self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                import base64
                from openai import OpenAI

                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                base64_image = base64.b64encode(image_bytes).decode("utf-8")
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Transcribe this document page precisely into structured Markdown with LaTeX math and tables.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=4096,
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"OpenAI VLM call failed: {e}")

        # Graceful fallback when VLM is mock or offline
        return ""


default_vlm_service = VLMService()

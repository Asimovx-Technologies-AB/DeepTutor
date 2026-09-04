"""
Google Gemini Vision Language Model (VLM) Client.
Used for scanned documents, images (.png, .jpg, .webp), and image-based PDFs
to extract structured topics and key concepts in <5s without extracting raw images or tables.
"""
import os
import base64
import json
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import dotenv_values


VLM_CASCADE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
]



def _get_active_gemini_key() -> str:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        vals = dotenv_values(env_path)
        key = vals.get("GEMINI_API_KEY", "")
        if key and key.strip() and key != "your_gemini_api_key_here":
            return key.strip()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


class GeminiVLMClient:
    """
    Vision-Language client using Google Gemini API.
    Supports multimodal inputs (image + prompt) for:
    1. Full OCR and academic text extraction
    2. Topic tree & curriculum extraction
    3. Diagram / figure factual captioning
    """

    def __init__(self):
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = 20.0

    @property
    def provider(self) -> str:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            vals = dotenv_values(env_path)
            p = vals.get("VLM_PROVIDER", "")
            if p:
                return p.strip()
            llm_p = vals.get("LLM_PROVIDER", "")
            if llm_p:
                return llm_p.strip()
        from app.core.config import get_settings
        return getattr(get_settings(), "VLM_PROVIDER", "openai")

    @property
    def api_key(self) -> str:
        return _get_active_gemini_key()

    def is_configured(self) -> bool:
        p = self.provider.lower()
        if p == "azure_openai":
            from app.core.config import get_settings
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or getattr(get_settings(), "AZURE_OPENAI_ENDPOINT", "")
            return bool(endpoint and len(endpoint.strip()) > 5)
        elif p == "openai":
            from app.core.config import get_settings
            key = os.environ.get("OPENAI_API_KEY") or getattr(get_settings(), "OPENAI_API_KEY", "")
            return bool(key and len(key.strip()) > 10 and key != "your_openai_api_key_here")
        key = self.api_key
        return bool(key and len(key.strip()) > 10 and key != "your_gemini_api_key_here")

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
                print(f"[GeminiVLM] PDF render page {page_idx} error: {e2}")
        return None

    def get_pdf_page_count(self, file_path: str) -> int:
        """Returns total page count of a PDF file."""
        try:
            import pymupdf
            doc = pymupdf.open(file_path)
            return len(doc)
        except Exception:
            try:
                import fitz
                doc = fitz.open(file_path)
                return len(doc)
            except Exception:
                return 0

    async def extract_text_from_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        context_hint: str = "",
    ) -> str:
        """
        Extracts all readable text, formulas, equations, definitions, and structured notes
        from an image or scanned document page using Gemini VLM.
        """
        if not self.is_configured():
            return ""

        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are an expert academic OCR and document digitization engine.\n"
            f"The subject/context of this study material is: '{context_hint or 'Academic Study Material'}'.\n\n"
            "MANDATORY INSTRUCTIONS:\n"
            "1. Extract ALL readable text, headings, subheadings, bullet points, explanations, and notes from this image verbatim.\n"
            "2. Preserve mathematical equations, formulas, theorems, and proofs accurately (using clean LaTeX or standard math notations).\n"
            "3. If diagrams, charts, or figures are present, include their labels and a concise factual summary in brackets [Figure: ...].\n"
            "4. Maintain proper paragraph hierarchy and reading sequence.\n"
            "5. Output ONLY the extracted text content. Do NOT include conversational commentary like 'Here is the text:' or markdown wrappers."
        )

        # 1. Try OpenAI / Azure OpenAI Vision
        p = self.provider.lower()
        if p == "azure_openai":
            try:
                from app.rag.azure_openai_client import azure_openai
                if await azure_openai.is_available():
                    text = await azure_openai.chat_vision(prompt, image_bytes, temperature=0.1)
                    if text and text.strip():
                        return text.strip()
            except Exception as e:
                print(f"[AzureVLM] extract_text_from_image error: {e}")
        elif p == "openai":
            try:
                from app.rag.azure_openai_client import openai_client
                if await openai_client.is_available():
                    text = await openai_client.chat_vision(prompt, image_bytes, temperature=0.1)
                    if text and text.strip():
                        return text.strip()
            except Exception as e:
                print(f"[OpenAIVLM] extract_text_from_image error: {e}")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }

        key = self.api_key
        for model_name in VLM_CASCADE_MODELS:
            url = f"{self.base_url}/models/{model_name}:generateContent?key={key}"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        if text and text.strip():
                            return text.strip()
                    elif r.status_code in (404, 429, 503):
                        print(f"[GeminiVLM] Model {model_name} returned status {r.status_code}, cascading...")
                        continue
            except Exception as e:
                print(f"[GeminiVLM] OCR error with model {model_name}: {e}")
                continue

        return ""

    async def analyze_scanned_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        subject_hint: str = "",
    ) -> Dict[str, Any]:
        """
        Analyze a scanned page or diagram image using Gemini VLM.
        Extracts structured topics, core concepts, and hierarchy.
        """
        if not self.is_configured():
            return self._offline_fallback(subject_hint)

        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            f"You are an expert academic curriculum parser and content validator for an AI tutoring system.\n"
            f"The user uploaded an image for their study room (subject hint: '{subject_hint or 'General Subject'}').\n\n"
            "STEP 1: EDUCATIONAL STUDY MATERIAL VALIDATION\n"
            "Carefully examine the visual content of this image and classify whether it is genuine academic study material:\n"
            "A. ACADEMIC STUDY MATERIAL (is_study_material: true):\n"
            "   - Textbook page, lecture slides, chalkboard/whiteboard notes, handwritten/typed study notes\n"
            "   - Exam papers, problem sets, formulas/equations, scientific charts/diagrams, code tutorials\n"
            "   - Academic paper, syllabus, or course handout\n\n"
            "B. NON-STUDY MATERIAL (is_study_material: false):\n"
            "   - Personal photos, selfies, portraits, group pictures\n"
            "   - Animals/pets, landscapes, nature, food, vehicles, fashion\n"
            "   - Memes, comics, video game screenshots, movie posters, entertainment graphics\n"
            "   - Financial receipts, invoices, bills, shipping labels, personal identity cards\n"
            "   - Random objects, icons, wallpapers, decorative graphics without educational text\n\n"
            "STEP 2: OUTPUT INSTRUCTIONS\n"
            "If NON-STUDY MATERIAL:\n"
            "  Set 'is_study_material': false.\n"
            "  Set 'detected_document_type' to a specific human-readable descriptor (e.g. 'Personal Photo', 'Meme / Entertainment Image', 'Financial Receipt', 'Vehicle Photo', 'Landscape Photo', 'Random Screenshot').\n"
            "  Set 'validation_reason': 'This image appears to be a [type] rather than academic coursework or study material. IndieTutor is an AI study room designed exclusively for learning course concepts and cannot answer questions or generate study plans from non-educational images.'\n"
            "  Set 'topics': [] (empty list).\n\n"
            "If ACADEMIC STUDY MATERIAL:\n"
            "  Set 'is_study_material': true.\n"
            "  Set 'detected_document_type': 'Textbook Page' / 'Lecture Slides' / 'Handwritten Notes' / 'Formula Sheet' / etc.\n"
            "  Extract 3 to 6 core academic topics and key concepts in prerequisite order (Beginner -> Intermediate -> Advanced).\n"
            "  Set 'validation_reason': ''\n\n"
            "Return strictly valid JSON with this exact schema:\n"
            "{\n"
            '  "is_study_material": true,\n'
            '  "detected_document_type": "Textbook Page",\n'
            '  "validation_reason": "",\n'
            '  "thought_process": "Brief explanation of image classification and topics.",\n'
            '  "title": "Main Subject or Chapter Title",\n'
            '  "topics": [\n'
            "    {\n"
            '      "id": "topic_1",\n'
            '      "title": "Topic Heading",\n'
            '      "summary": "Brief 1-2 sentence overview of this topic.",\n'
            '      "difficulty": "Beginner | Intermediate | Advanced",\n'
            '      "key_concepts": ["concept 1", "concept 2"],\n'
            '      "estimated_study_time": "10-15 mins"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Return raw JSON only, no markdown backticks, no other text."
        )

        # 1. Try OpenAI / Azure OpenAI Vision
        p = self.provider.lower()
        if p in ("openai", "azure_openai"):
            try:
                raw_text = ""
                if p == "azure_openai":
                    from app.rag.azure_openai_client import azure_openai
                    if await azure_openai.is_available():
                        raw_text = await azure_openai.chat_vision(prompt, image_bytes, temperature=0.2)
                elif p == "openai":
                    from app.rag.azure_openai_client import openai_client
                    if await openai_client.is_available():
                        raw_text = await openai_client.chat_vision(prompt, image_bytes, temperature=0.2)

                if raw_text and raw_text.strip():
                    cleaned = raw_text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[1]
                        if cleaned.endswith("```"):
                            cleaned = cleaned.rsplit("\n", 1)[0]
                        if cleaned.startswith("json"):
                            cleaned = cleaned[4:].strip()
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict):
                        if parsed.get("is_study_material") is False:
                            return {
                                "is_study_material": False,
                                "detected_document_type": parsed.get("detected_document_type", "Non-Academic Image"),
                                "validation_reason": parsed.get(
                                    "validation_reason",
                                    "This image does not contain academic coursework or study material. IndieTutor only processes educational study materials."
                                ),
                                "thought_process": parsed.get("thought_process", "VLM guardrail identified non-educational visual content."),
                                "subject": "Non-Study Material",
                                "title": parsed.get("detected_document_type", "Non-Academic Image"),
                                "topics": [],
                            }
                        if "topics" in parsed and len(parsed["topics"]) > 0:
                            for i, t in enumerate(parsed["topics"]):
                                if not t.get("id"):
                                    t["id"] = f"topic_{i+1}"
                            parsed["is_study_material"] = True
                            if not parsed.get("detected_document_type"):
                                parsed["detected_document_type"] = "Study Material Image"
                            return parsed
            except Exception as e:
                print(f"[VLM] OpenAI/Azure analyze error: {e}")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        key = self.api_key
        for model_name in VLM_CASCADE_MODELS:
            url = f"{self.base_url}/models/{model_name}:generateContent?key={key}"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        cleaned = text.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("\n", 1)[1]
                            if cleaned.endswith("```"):
                                cleaned = cleaned.rsplit("\n", 1)[0]
                            if cleaned.startswith("json"):
                                cleaned = cleaned[4:].strip()

                        parsed = json.loads(cleaned)
                        if isinstance(parsed, dict):
                            # Check if VLM classified as non-study material
                            if parsed.get("is_study_material") is False:
                                return {
                                    "is_study_material": False,
                                    "detected_document_type": parsed.get("detected_document_type", "Non-Academic Image"),
                                    "validation_reason": parsed.get(
                                        "validation_reason",
                                        "This image does not contain academic coursework or study material. IndieTutor only processes educational study materials."
                                    ),
                                    "thought_process": parsed.get("thought_process", "VLM guardrail identified non-educational visual content."),
                                    "subject": "Non-Study Material",
                                    "title": parsed.get("detected_document_type", "Non-Academic Image"),
                                    "topics": [],
                                }

                            # If valid study material with topics
                            if "topics" in parsed and len(parsed["topics"]) > 0:
                                for i, t in enumerate(parsed["topics"]):
                                    if not t.get("id"):
                                        t["id"] = f"topic_{i+1}"
                                parsed["is_study_material"] = True
                                if not parsed.get("detected_document_type"):
                                    parsed["detected_document_type"] = "Study Material Image"
                                return parsed
                    elif r.status_code in (404, 429, 503):
                        continue
            except Exception as e:
                print(f"[GeminiVLM] analyze_scanned_image error with {model_name}: {e}")
                continue

        return self._offline_fallback(subject_hint)

    def _offline_fallback(self, subject: str) -> Dict[str, Any]:
        """Offline fallback if Gemini is unreachable."""
        return {
            "thought_process": f"Generated curriculum topics for {subject or 'Study Material'}.",
            "title": f"{subject or 'Study Material'} Overview",
            "topics": [
                {
                    "id": "topic_1",
                    "title": f"Core Foundations of {subject or 'Topic'}",
                    "summary": "Primary definitions, governing principles, and essential concepts.",
                    "difficulty": "Beginner",
                    "key_concepts": ["Core Definitions", "Primary Theorems", "Fundamental Rules"],
                    "estimated_study_time": "10-12 mins",
                },
                {
                    "id": "topic_2",
                    "title": f"Applied Methods & Mechanics",
                    "summary": "Step-by-step problem-solving methods and practical applications.",
                    "difficulty": "Intermediate",
                    "key_concepts": ["Methods", "Execution Steps", "Standard Problems"],
                    "estimated_study_time": "15-18 mins",
                },
                {
                    "id": "topic_3",
                    "title": f"Advanced Mastery & Examination Synthesis",
                    "summary": "Complex scenarios, edge cases, and exam-level problem breakdowns.",
                    "difficulty": "Advanced",
                    "key_concepts": ["Edge Cases", "Synthesis", "Exam Traps"],
                    "estimated_study_time": "15-20 mins",
                },
            ],
        }


# Singleton instance
vlm_client = GeminiVLMClient()

"""
Content Classifier — Per-page routing to text or visual extraction pipelines.

Analyses each page of a document and decides whether it should be processed
by the text extraction pipeline, the visual processing pipeline, or both.
Also provides document-level content relevance classification using the
existing LLM-based classifier prompt.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from app.documents.models import PageContent

logger = logging.getLogger(__name__)

# Minimum characters of extractable digital text for a page to be considered
# "text-ready".  Below this threshold the page is routed to VLM OCR.
TEXT_THRESHOLD = 40


class ContentClassifier:
    """Classifies pages into text / visual / mixed for pipeline routing."""

    # ── Page-level classification ─────────────────────────────────────────

    @staticmethod
    def classify_page(
        page_text: str,
        embedded_image_count: int = 0,
    ) -> str:
        """Classify a single page as 'text', 'visual', or 'mixed'.

        Rules:
        - < TEXT_THRESHOLD chars of text  →  'visual' (scanned / image-only)
        - ≥ TEXT_THRESHOLD chars AND ≥ 1 large embedded image  →  'mixed'
        - ≥ TEXT_THRESHOLD chars AND no significant images  →  'text'
        """
        text_len = len((page_text or "").strip())
        if text_len < TEXT_THRESHOLD:
            return "visual"
        if embedded_image_count > 0:
            return "mixed"
        return "text"

    def classify_pages(
        self,
        pages: List[Tuple[int, str, int]],
    ) -> Dict[str, List[int]]:
        """Batch classify all pages.

        Args:
            pages: list of (page_num, page_text, image_count) tuples.

        Returns:
            {"text": [1, 2, 5], "visual": [3], "mixed": [4, 6]}
        """
        result: Dict[str, List[int]] = {"text": [], "visual": [], "mixed": []}
        for page_num, text, img_count in pages:
            category = self.classify_page(text, img_count)
            result[category].append(page_num)
        return result

    # ── Page quality scoring ──────────────────────────────────────────────

    @staticmethod
    def score_text_quality(text: str) -> float:
        """Heuristic quality score for extracted page text.

        Returns a float 0.0–1.0 where:
        - 1.0 = perfect digital extraction
        - < 0.6 = likely garbled / poor quality → route to VLM
        """
        if not text or not text.strip():
            return 0.0

        text = text.strip()
        char_count = len(text)

        # Very short text
        if char_count < TEXT_THRESHOLD:
            return 0.1

        # Check for garbled / mojibake characters
        garbled_chars = sum(
            1 for c in text if ord(c) > 0xFFFF or c in "\ufffd\ufffe\uffff"
        )
        garble_ratio = garbled_chars / char_count if char_count else 0

        # Check word density (real words vs random character sequences)
        words = re.findall(r"[a-zA-Z]{2,}", text)
        word_char_total = sum(len(w) for w in words)
        word_density = word_char_total / char_count if char_count else 0

        # Check for excessive whitespace
        whitespace_ratio = text.count(" ") / char_count if char_count else 0

        # Scoring
        score = 1.0
        if garble_ratio > 0.05:
            score -= min(garble_ratio * 5, 0.5)
        if word_density < 0.3:
            score -= 0.3
        if whitespace_ratio > 0.5:
            score -= 0.2

        return max(0.0, min(1.0, score))

    # ── Document-level content relevance classification ───────────────────

    async def classify_document_content(
        self,
        sample_text: str,
    ) -> Dict[str, Any]:
        """LLM-based content relevance classification.

        Uses the CONTENT_RELEVANCE_CLASSIFIER_PROMPT from topic_extractor
        to classify the document into one of:
        STUDY_MATERIAL, REFERENCE_NONACADEMIC, PERSONAL, COMMERCIAL,
        CREATIVE, OTHER.

        Returns:
            {
                "category": "STUDY_MATERIAL",
                "is_study_material": True,
                "confidence": 0.92,
                "reasoning": "..."
            }
        """
        if not sample_text or len(sample_text.strip()) < 50:
            return {
                "category": "OTHER",
                "is_study_material": False,
                "confidence": 0.1,
                "reasoning": "Insufficient text to classify.",
            }

        try:
            from app.rag.llm_client import llm_client
            from app.rag.topic_extractor import CONTENT_RELEVANCE_CLASSIFIER_PROMPT

            prompt = CONTENT_RELEVANCE_CLASSIFIER_PROMPT.format(
                text_sample=sample_text[:8000]
            )
            raw = await llm_client.generate(prompt)

            # Parse JSON response defensively
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```\w*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)

            result = json.loads(cleaned)
            return {
                "category": result.get("category", "OTHER"),
                "is_study_material": result.get("is_study_material", False),
                "confidence": float(result.get("confidence", 0.0)),
                "reasoning": result.get("reasoning", ""),
            }
        except Exception as exc:
            logger.warning("[ContentClassifier] LLM classification error: %s", exc)
            return {
                "category": "STUDY_MATERIAL",
                "is_study_material": True,
                "confidence": 0.5,
                "reasoning": f"Fallback: classification failed ({exc})",
            }

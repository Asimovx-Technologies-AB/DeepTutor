"""
Figure Detector — Extracts and captions figures/diagrams from PDF pages.

Uses PyMuPDF for image extraction and VLM (vlm_client) for factual
captioning of technical diagrams and academic figures.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from app.documents.models import FigureData
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Minimum image byte size to consider (skip tiny icons/decorations)
MIN_IMAGE_BYTES = 5000


class FigureDetector:
    """Detects and captions figures/diagrams embedded in PDF pages."""

    def __init__(self, max_vlm_captions: Optional[int] = None):
        self._vlm_captions_count: int = 0
        self._max_vlm_captions: int = (
            max_vlm_captions
            if max_vlm_captions is not None
            else getattr(settings, "VLM_MAX_FIGURES_PER_DOC", 5)
        )

    def reset_caption_budget(self) -> None:
        """Resets the caption count for a new document run."""
        self._vlm_captions_count = 0

    async def detect_figures(
        self,
        file_path: str,
        page_num: int,
        max_figures: int = 3,
    ) -> List[FigureData]:
        """Extracts embedded images from a PDF page and captions them.

        Args:
            file_path: Path to PDF file.
            page_num: 1-based page number.
            max_figures: Maximum figures to extract per page.

        Returns:
            List of FigureData with captions from VLM.
        """
        raw_images = await asyncio.to_thread(
            self._extract_page_images, file_path, page_num, max_figures
        )
        if not raw_images:
            return []

        figures: List[FigureData] = []
        for img_index, img_bytes, img_ext in raw_images:
            caption = ""
            # Only attempt VLM if enabled and within free-tier budget
            if (
                getattr(settings, "ENABLE_VLM_PARSER", True)
                and self._vlm_captions_count < self._max_vlm_captions
            ):
                caption = await self._caption_figure(
                    img_bytes, f"image/{img_ext}"
                )
                if caption:
                    self._vlm_captions_count += 1

            if not caption or not caption.strip():
                caption = f"Figure {img_index} on page {page_num}"

            figures.append(FigureData(
                page_num=page_num,
                image_index=img_index,
                image_bytes=img_bytes,
                caption=caption.strip(),
                mime_type=f"image/{img_ext}",
            ))

        return figures

    # ── Image extraction from PDF ─────────────────────────────────────────

    @staticmethod
    def _extract_page_images(
        file_path: str,
        page_num: int,
        max_figures: int = 3,
    ) -> List[tuple]:
        """Extracts embedded images from a single PDF page.

        Returns list of (image_index, image_bytes, extension).
        """
        try:
            import pymupdf

            doc = pymupdf.open(file_path)
            if page_num - 1 >= len(doc):
                doc.close()
                return []

            page = doc[page_num - 1]
            image_list = page.get_images(full=True)
            results = []

            for img_idx, img in enumerate(image_list):
                if len(results) >= max_figures:
                    break
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image.get("image")
                    image_ext = base_image.get("ext", "jpeg")

                    if image_bytes and len(image_bytes) >= MIN_IMAGE_BYTES:
                        results.append((img_idx + 1, image_bytes, image_ext))
                except Exception:
                    continue

            doc.close()
            return results
        except Exception as exc:
            logger.warning("[FigureDetector] Image extraction error p%d: %s", page_num, exc)
            return []

    # ── VLM captioning ────────────────────────────────────────────────────

    @staticmethod
    async def _caption_figure(
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> str:
        """Generates a factual caption for a figure using VLM.

        Uses the existing vlm_client.caption_diagram() method.
        """
        try:
            from app.rag.vlm_client import vlm_client

            if not vlm_client.is_configured() or vlm_client.is_rate_limited():
                return ""

            caption = await vlm_client.caption_diagram(
                image_bytes, mime_type=mime_type
            )
            if caption and len(caption.strip()) > 10:
                return caption.strip()
        except Exception as exc:
            logger.warning("[FigureDetector] VLM captioning error: %s", exc)

        return ""

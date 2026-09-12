"""
Text Extractor — Digital text extraction with quality checking.

Handles the text extraction pipeline for PDFs (PyMuPDF fast path), DOCX,
PPTX, and plain text files.  Includes a quality checker that routes
low-quality pages to the VLM OCR fallback.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Tuple

from app.documents.extraction.content_classifier import ContentClassifier
from app.documents.ingestion.file_handler import FileHandler
from app.documents.models import PageContent

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extracts digital text from documents with quality checking."""

    def __init__(self) -> None:
        self.file_handler = FileHandler()
        self.classifier = ContentClassifier()

    # ── PDF text extraction ───────────────────────────────────────────────

    async def extract_pdf_pages(
        self,
        file_path: str,
    ) -> Tuple[List[PageContent], List[int]]:
        """PyMuPDF fast-path text extraction.

        Returns:
            (good_pages, scanned_page_nums) where good_pages are PageContent
            objects with quality_score ≥ 0.6, and scanned_page_nums are page
            numbers that need VLM OCR fallback.
        """
        import pymupdf

        def _extract():
            doc = pymupdf.open(file_path)
            page_count = len(doc)
            pages: List[PageContent] = []
            scanned: List[int] = []

            for p_idx in range(page_count):
                page = doc[p_idx]
                text = page.get_text().strip()
                page_num = p_idx + 1

                # Count embedded images for mixed-content detection
                try:
                    img_count = len(page.get_images())
                except Exception:
                    img_count = 0

                classification = self.classifier.classify_page(text, img_count)
                quality = self.classifier.score_text_quality(text)

                if classification == "visual" or quality < 0.6:
                    scanned.append(page_num)
                    # Still create a PageContent with whatever text we got
                    pages.append(PageContent(
                        page_num=page_num,
                        raw_text=text,
                        classification="visual",
                        quality_score=quality,
                        extraction_method="digital_text_low_quality",
                    ))
                else:
                    pages.append(PageContent(
                        page_num=page_num,
                        raw_text=text,
                        classification=classification,
                        quality_score=quality,
                        extraction_method="digital_text",
                    ))

            doc.close()
            return pages, scanned

        return await asyncio.to_thread(_extract)

    # ── VLM OCR fallback for scanned pages ────────────────────────────────

    async def ocr_scanned_pages(
        self,
        file_path: str,
        scanned_page_nums: List[int],
        concurrency: int = 4,
    ) -> List[PageContent]:
        """Renders scanned pages as PNG and transcribes with VLM.

        Args:
            file_path: Path to PDF file.
            scanned_page_nums: 1-based page numbers to OCR.
            concurrency: Max parallel VLM requests.

        Returns:
            List of PageContent with OCR-extracted text.
        """
        if not scanned_page_nums:
            return []

        from app.rag.vlm_client import vlm_client

        sem = asyncio.Semaphore(concurrency)

        async def _ocr_one(page_num: int) -> PageContent:
            async with sem:
                try:
                    import pymupdf

                    def _render():
                        doc = pymupdf.open(file_path)
                        page = doc[page_num - 1]
                        pix = page.get_pixmap(dpi=130)
                        png_bytes = pix.tobytes("png")
                        doc.close()
                        return png_bytes

                    png_bytes = await asyncio.to_thread(_render)
                    resp = await vlm_client.extract_text_from_image(
                        png_bytes, mime_type="image/png"
                    )
                    text = (resp or "").strip()

                    if text:
                        return PageContent(
                            page_num=page_num,
                            raw_text=text,
                            classification="visual",
                            quality_score=0.7,
                            extraction_method="vlm_ocr",
                        )
                    else:
                        logger.warning(
                            "[TextExtractor] VLM returned empty for page %d of %s",
                            page_num, Path(file_path).name,
                        )
                except Exception:
                    logger.exception(
                        "[TextExtractor] OCR failed for page %d of %s",
                        page_num, Path(file_path).name,
                    )

                return PageContent(
                    page_num=page_num,
                    raw_text="",
                    classification="visual",
                    quality_score=0.0,
                    extraction_method="vlm_ocr_failed",
                )

        tasks = [_ocr_one(pn) for pn in scanned_page_nums]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pages: List[PageContent] = []
        for r in results:
            if isinstance(r, PageContent):
                pages.append(r)
            elif isinstance(r, Exception):
                logger.warning("[TextExtractor] OCR task exception: %s", r)
        return pages

    # ── DOCX extraction ───────────────────────────────────────────────────

    async def extract_docx(self, file_path: str) -> List[PageContent]:
        """Extracts text from Word documents."""
        _, parts = await self.file_handler.open_docx(file_path)
        full_text = "\n\n".join(text for _, text in parts)
        return [PageContent(
            page_num=1,
            raw_text=full_text,
            classification="text",
            quality_score=0.95,
            extraction_method="digital_text",
        )]

    # ── PPTX extraction ──────────────────────────────────────────────────

    async def extract_pptx(self, file_path: str) -> List[PageContent]:
        """Extracts per-slide text from PowerPoint presentations."""
        _, slides = await self.file_handler.open_pptx(file_path)
        pages: List[PageContent] = []
        for slide_num, slide_text in slides:
            pages.append(PageContent(
                page_num=slide_num,
                raw_text=slide_text,
                classification="text",
                quality_score=0.90,
                extraction_method="digital_text",
            ))
        return pages

    # ── Plain text / code extraction ──────────────────────────────────────

    async def extract_text_file(self, file_path: str) -> List[PageContent]:
        """Reads plain text, markdown, or code files."""
        text = await self.file_handler.read_text(file_path)
        return [PageContent(
            page_num=1,
            raw_text=text,
            classification="text",
            quality_score=0.98,
            extraction_method="digital_text",
        )]

    # ── Image file extraction (VLM transcription) ─────────────────────────

    async def extract_image_file(self, file_path: str) -> List[PageContent]:
        """Transcribes a standalone image file using VLM."""
        try:
            img_bytes = await self.file_handler.read_image(file_path)

            from app.rag.vlm_client import vlm_client

            ext = Path(file_path).suffix.lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            resp = await vlm_client.extract_text_from_image(
                img_bytes, mime_type=mime
            )
            text = (resp or "").strip()

            if text:
                return [PageContent(
                    page_num=1,
                    raw_text=text,
                    classification="visual",
                    quality_score=0.7,
                    extraction_method="vlm_ocr",
                )]
            else:
                logger.warning(
                    "[TextExtractor] VLM returned empty for image %s",
                    Path(file_path).name,
                )
        except Exception:
            logger.exception(
                "[TextExtractor] Image transcription failed for %s",
                Path(file_path).name,
            )

        return [PageContent(
            page_num=1,
            raw_text=f"Uploaded study image: {Path(file_path).name} (no text extracted)",
            classification="visual",
            quality_score=0.0,
            extraction_method="vlm_ocr_failed",
        )]

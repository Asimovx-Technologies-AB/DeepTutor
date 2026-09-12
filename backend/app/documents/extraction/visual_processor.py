"""
Visual Processor — Coordinates image analysis for figure, table,
and equation detection across document pages.

The 'Visual Processing Pipeline' and 'Image Analysis' stage in the
architecture diagram.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from app.documents.extraction.figure_detector import FigureDetector
from app.documents.extraction.table_detector import TableDetector
from app.documents.extraction.equation_detector import EquationDetector
from app.documents.models import PageContent

logger = logging.getLogger(__name__)


class VisualProcessor:
    """Coordinates the three visual detection sub-pipelines."""

    def __init__(self) -> None:
        self.figure_detector = FigureDetector()
        self.table_detector = TableDetector()
        self.equation_detector = EquationDetector()

    # ── Process a single page ─────────────────────────────────────────────

    async def process_page(
        self,
        file_path: str,
        page_num: int,
        page_text: str = "",
    ) -> PageContent:
        """Runs figure, table, and equation detection in parallel for a page.

        Args:
            file_path: Path to the PDF file.
            page_num: 1-based page number.
            page_text: Already-extracted text for equation regex detection.

        Returns:
            PageContent with figures, tables, and equations populated.
        """
        # Run all three detectors concurrently
        fig_task = self.figure_detector.detect_figures(file_path, page_num)
        tbl_task = asyncio.to_thread(
            self.table_detector.detect_tables, file_path, page_num
        )
        eq_task = asyncio.to_thread(
            self.equation_detector.detect_equations, page_text, page_num
        )

        results = await asyncio.gather(
            fig_task, tbl_task, eq_task, return_exceptions=True
        )

        figures = results[0] if isinstance(results[0], list) else []
        tables = results[1] if isinstance(results[1], list) else []
        equations = results[2] if isinstance(results[2], list) else []

        if isinstance(results[0], Exception):
            logger.warning("[VisualProcessor] Figure detection error p%d: %s", page_num, results[0])
        if isinstance(results[1], Exception):
            logger.warning("[VisualProcessor] Table detection error p%d: %s", page_num, results[1])
        if isinstance(results[2], Exception):
            logger.warning("[VisualProcessor] Equation detection error p%d: %s", page_num, results[2])

        return PageContent(
            page_num=page_num,
            raw_text=page_text,
            classification="mixed",
            quality_score=0.8,
            figures=figures,
            tables=tables,
            equations=equations,
            extraction_method="visual_processing",
        )

    # ── Batch process multiple pages ──────────────────────────────────────

    async def process_pages(
        self,
        file_path: str,
        pages: List[PageContent],
        concurrency: int = 4,
    ) -> List[PageContent]:
        """Enriches multiple pages with visual content in parallel.

        Only processes PDF files.  Merges visual detections into the
        existing PageContent objects.
        """
        if not pages:
            return pages

        self.figure_detector.reset_caption_budget()
        sem = asyncio.Semaphore(concurrency)

        async def _process_one(page: PageContent) -> PageContent:
            async with sem:
                result = await self.process_page(
                    file_path, page.page_num, page.raw_text
                )
                # Merge visual detections into existing page
                page.figures = result.figures
                page.tables = result.tables
                page.equations = result.equations
                return page

        tasks = [_process_one(p) for p in pages]
        await asyncio.gather(*tasks, return_exceptions=True)
        return pages

"""
Document Orchestrator — Central pipeline coordinator.

Drives the full document processing pipeline:
  File Input → Object Services → Content Classification → Text/Visual
  Extraction → Knowledge Tiler → Quality/CPAR → Storage Pipeline

Replaces both the old DocumentProcessor (doc_processor.py) and
StudyDocumentProcessor (study_doc_processor.py) with a single,
structured pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.documents.chunking.knowledge_tiler import KnowledgeTiler
from app.documents.extraction.content_classifier import ContentClassifier
from app.documents.extraction.text_extractor import TextExtractor
from app.documents.extraction.visual_processor import VisualProcessor
from app.documents.ingestion.object_services import ObjectServices
from app.documents.models import (
    CanonicalDocument,
    KnowledgeChunk,
    PageContent,
    PipelineDocument,
    PipelineStatus,
)
from app.documents.normalization.quality_validator import QualityValidator
from app.documents.retrieval.context_retriever import ContextRetriever
from app.documents.retrieval.storage_pipeline import StoragePipeline

logger = logging.getLogger(__name__)


class DocumentOrchestrator:
    """Central coordinator driving the full document processing pipeline."""

    def __init__(self) -> None:
        self.object_services = ObjectServices()
        self.classifier = ContentClassifier()
        self.text_extractor = TextExtractor()
        self.visual_processor = VisualProcessor()
        self.tiler = KnowledgeTiler()
        self.validator = QualityValidator()
        self.storage = StoragePipeline()
        self.retriever = ContextRetriever()

        # In-flight document tracking
        self._documents: Dict[str, PipelineDocument] = {}

    # ── Main pipeline entry ───────────────────────────────────────────────

    async def process(
        self,
        doc_id: str,
        file_path: str,
        file_name: str,
        session_id: str = "",
        subject: str = "General",
        user_id: Optional[str] = None,
        doc_hash: Optional[str] = None,
    ) -> CanonicalDocument:
        """Drives the full processing pipeline.

        Stages:
        1. Register (Object Services)
        2. Classify pages (Content Classifier)
        3. Extract text (Text Extractor + quality check + VLM fallback)
        4. Tile (Knowledge Tiler → 17 knowledge box types)
        5. Validate (Quality & CPAR)
        6. Store (Storage Pipeline → PostgreSQL/pgvector)

        Args:
            doc_id: Unique document identifier.
            file_path: Path to the uploaded file.
            file_name: Original file name.
            session_id: Study session ID.
            subject: Subject area hint.
            user_id: User who uploaded the document.
            doc_hash: Pre-computed SHA-256 hash (optional).

        Returns:
            CanonicalDocument with validated chunks and intelligence data.
        """
        # ── Stage 1: Register ────────────────────────────────────────────
        document = await self.object_services.register_document(
            doc_id=doc_id,
            file_path=file_path,
            file_name=file_name,
            session_id=session_id,
            user_id=user_id,
            subject=subject,
            doc_hash=doc_hash,
        )
        self._documents[doc_id] = document
        self._set_status(document, PipelineStatus.CLASSIFYING)

        try:
            # ── Stage 2: Extract ─────────────────────────────────────────
            self._set_status(document, PipelineStatus.EXTRACTING_TEXT)
            pages = await self._extract(document)
            document.pages = pages
            document.page_count = max(len(pages), document.page_count)

            # ── Stage 3: Tile ────────────────────────────────────────────
            self._set_status(document, PipelineStatus.TILING)
            chunks = self.tiler.tile_document(
                pages=pages,
                doc_id=doc_id,
                doc_name=file_name,
            )

            # ── Stage 4: Validate ────────────────────────────────────────
            self._set_status(document, PipelineStatus.VALIDATING)
            canonical = self.validator.validate(document, chunks)

            # ── Stage 5: Store ───────────────────────────────────────────
            self._set_status(document, PipelineStatus.STORING)
            await self.storage.store(canonical)

            # ── Done ─────────────────────────────────────────────────────
            self._set_status(document, PipelineStatus.COMPLETED)

            logger.info(
                "[Orchestrator] Pipeline completed for %s: %d chunks, "
                "%.1f%% coverage, avg confidence %.3f",
                doc_id,
                canonical.intelligence.total_chunks,
                canonical.intelligence.coverage_pct,
                canonical.intelligence.avg_confidence,
            )

            return canonical

        except Exception as exc:
            self._set_status(document, PipelineStatus.ERROR)
            document.error_message = str(exc)
            logger.exception("[Orchestrator] Pipeline error for %s", doc_id)

            # Return a partial result rather than crashing
            return CanonicalDocument(document=document)

    # ── Extraction dispatcher ─────────────────────────────────────────────

    async def _extract(
        self,
        document: PipelineDocument,
    ) -> List[PageContent]:
        """Routes to the correct extractor based on file type."""
        file_type = document.file_type
        file_path = document.file_path

        if file_type == "pdf":
            return await self._extract_pdf(document)
        elif file_type == "docx":
            return await self.text_extractor.extract_docx(file_path)
        elif file_type == "pptx":
            return await self.text_extractor.extract_pptx(file_path)
        elif file_type == "image":
            return await self.text_extractor.extract_image_file(file_path)
        elif file_type == "text":
            return await self.text_extractor.extract_text_file(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    async def _extract_pdf(
        self,
        document: PipelineDocument,
    ) -> List[PageContent]:
        """PDF extraction: fast text path + VLM OCR for scanned pages."""
        file_path = document.file_path

        # 1. Fast text extraction
        pages, scanned_nums = await self.text_extractor.extract_pdf_pages(file_path)
        document.page_count = len(pages)

        # 2. VLM OCR for scanned pages
        if scanned_nums:
            logger.info(
                "[Orchestrator] %d/%d scanned pages detected for %s, running VLM OCR...",
                len(scanned_nums), document.page_count, document.file_name,
            )
            self._set_status(document, PipelineStatus.EXTRACTING_VISUALS)
            ocr_pages = await self.text_extractor.ocr_scanned_pages(
                file_path, scanned_nums
            )

            # Merge OCR results into the page list
            ocr_by_num = {p.page_num: p for p in ocr_pages}
            for i, page in enumerate(pages):
                if page.page_num in ocr_by_num:
                    ocr_page = ocr_by_num[page.page_num]
                    if ocr_page.raw_text and ocr_page.quality_score > page.quality_score:
                        pages[i] = ocr_page

        return pages

    # ── Background enrichment (table/figure/equation extraction) ──────────

    async def run_background_enrichment(
        self,
        session_id: str,
        doc_id: str,
        file_path: str,
    ) -> None:
        """Background task: extracts tables, figures, and equations.

        Called after the fast text path completes so the user can
        start chatting immediately.  Updates document status to
        fully_processed when done.
        """
        if Path(file_path).suffix.lower() != ".pdf":
            try:
                from app.services.study_storage import update_document_status
                update_document_status(session_id, doc_id, "fully_processed")
            except Exception:
                pass
            return

        try:
            document = self._documents.get(doc_id)
            pages = document.pages if document else []

            if not pages:
                # Re-extract if pages not in memory (e.g., after server restart)
                pages, _ = await self.text_extractor.extract_pdf_pages(file_path)

            # Run visual processing on all pages
            enriched_pages = await self.visual_processor.process_pages(
                file_path, pages
            )

            # Re-tile with visual content
            tiler = KnowledgeTiler()
            enrichment_chunks: List[KnowledgeChunk] = []
            for page in enriched_pages:
                for table in page.tables:
                    tbl_chunk = tiler._tile_table(
                        table, doc_id, Path(file_path).name, [], 0
                    )
                    enrichment_chunks.append(tbl_chunk)

                for figure in page.figures:
                    fig_chunk = tiler._tile_figure(figure, doc_id, Path(file_path).name)
                    enrichment_chunks.append(fig_chunk)

            # Store enrichment chunks
            if enrichment_chunks:
                enrich_doc = document or PipelineDocument(
                    doc_id=doc_id, file_path=file_path,
                    file_name=Path(file_path).name, session_id=session_id,
                )
                enrich_canonical = CanonicalDocument(
                    document=enrich_doc, chunks=enrichment_chunks
                )
                await self.storage.store(enrich_canonical)

            # Update status
            try:
                from app.services.study_storage import update_document_status
                update_document_status(session_id, doc_id, "fully_processed")
            except Exception as exc:
                logger.debug("[Orchestrator] Status update notice: %s", exc)

        except Exception as exc:
            logger.error("[Orchestrator] Background enrichment error for %s: %s", doc_id, exc, exc_info=True)
            try:
                from app.services.study_storage import update_document_status
                update_document_status(session_id, doc_id, "fully_processed")
            except Exception:
                pass

    # ── Retrieval delegation ──────────────────────────────────────────────

    def retrieve_context(
        self,
        doc_id: str,
        query: str,
        top_k: int = 6,
        session_id: Optional[str] = None,
    ):
        """Delegates to ContextRetriever."""
        return self.retriever.retrieve(doc_id, query, top_k, session_id)

    def get_document_text(
        self,
        doc_id: str,
        max_chars: int = 12000,
    ) -> str:
        """Delegates to ContextRetriever."""
        return self.retriever.get_document_text(doc_id, max_chars)

    # ── Status management ─────────────────────────────────────────────────

    def get_status(self, doc_id: str) -> Optional[PipelineStatus]:
        doc = self._documents.get(doc_id)
        return doc.status if doc else None

    @staticmethod
    def _set_status(
        document: PipelineDocument,
        status: PipelineStatus,
    ) -> None:
        document.status = status
        logger.debug(
            "[Orchestrator] %s → %s", document.doc_id, status.value
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

document_orchestrator = DocumentOrchestrator()


# ── Task Queue Handler Registration ──────────────────────────────────────────

try:
    from app.services.task_queue import register_task_handler

    @register_task_handler("doc_enrichment")
    async def _handle_doc_enrichment(payload: Dict[str, Any]):
        s_id = payload.get("session_id", "")
        d_id = payload.get("doc_id", "")
        f_path = payload.get("file_path", "")
        await document_orchestrator.run_background_enrichment(s_id, d_id, f_path)
except Exception:
    pass

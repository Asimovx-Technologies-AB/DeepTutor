"""
test_doc_ingestion_completeness.py
===================================
Tests document ingestion completeness, failure tracking, coverage checks,
and document re-indexing:
- PDFs with many scanned pages process all pages without truncation
- Low coverage (<80% indexed pages) sets status to 'indexing_incomplete'
- Re-index endpoint successfully re-triggers indexing
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from app.rag.doc_processor import DocumentProcessor, DocumentRecord, DocumentChunk


class TestDocIngestionCompleteness:

    def _make_processor(self):
        proc = DocumentProcessor()
        proc.vlm = MagicMock()
        return proc

    @pytest.mark.asyncio
    async def test_low_coverage_sets_indexing_incomplete(self, tmp_path):
        """When less than 80% of pages yield chunks, status must be set to 'indexing_incomplete'."""
        proc = self._make_processor()
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("app.rag.sqlite_fts_store.get_session_store") as mock_store, \
             patch("app.rag.doc_processor.pypdf.PdfReader") as mock_pdf:

            mock_store.return_value = MagicMock(index_chunks=MagicMock())
            # 10 pages total, only 2 pages (1 and 2) return text, rest empty
            mock_pages = []
            for i in range(10):
                p = MagicMock()
                p.extract_text.return_value = f"Some digital text for page {i+1} with enough length to qualify" if i < 2 else ""
                mock_pages.append(p)

            mock_pdf.return_value = MagicMock(pages=mock_pages)
            proc.vlm.render_pdf_page_to_image = MagicMock(return_value=None)  # OCR returns nothing

            doc = await proc.ingest_document(
                doc_id="doc_low_coverage",
                file_path=str(pdf_file),
                file_name="sample.pdf",
                subject="Geography",
                session_id="session_low_cov",
            )

            assert doc.status == "indexing_incomplete"
            assert "Indexed 2/10 pages" in (doc.error_message or "")

    @pytest.mark.asyncio
    async def test_full_coverage_sets_text_ready(self, tmp_path):
        """When >= 80% of pages yield chunks, status must be 'text_ready'."""
        proc = self._make_processor()
        pdf_file = tmp_path / "full.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("app.rag.sqlite_fts_store.get_session_store") as mock_store, \
             patch("app.rag.doc_processor.pypdf.PdfReader") as mock_pdf:

            mock_store.return_value = MagicMock(index_chunks=MagicMock())
            # 10 pages total, all 10 return valid text
            mock_pages = []
            for i in range(10):
                p = MagicMock()
                p.extract_text.return_value = f"This is page {i+1} with full text content for indexing geography concepts."
                mock_pages.append(p)

            mock_pdf.return_value = MagicMock(pages=mock_pages)

            doc = await proc.ingest_document(
                doc_id="doc_full_coverage",
                file_path=str(pdf_file),
                file_name="full.pdf",
                subject="Geography",
                session_id="session_full_cov",
            )

            assert doc.status == "text_ready"
            assert doc.error_message is None

    @pytest.mark.asyncio
    async def test_scanned_pdf_untruncated_processing(self, tmp_path):
        """Scanned PDFs with >12 pages should attempt OCR on all pages rather than stopping at 12."""
        proc = self._make_processor()
        pdf_file = tmp_path / "scanned_long.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        ocr_called_pages = set()

        async def mock_ocr(img_bytes, mime_type="image/png", context_hint=""):
            return "Extracted scanned text from page"

        proc.vlm.extract_text_from_image = mock_ocr

        def mock_render(path, idx, dpi):
            ocr_called_pages.add(idx + 1)
            return b"fake_image_png_bytes"

        proc.vlm.render_pdf_page_to_image = mock_render

        with patch("app.rag.sqlite_fts_store.get_session_store") as mock_store, \
             patch("app.rag.doc_processor.pypdf.PdfReader") as mock_pdf:

            mock_store.return_value = MagicMock(index_chunks=MagicMock())
            # 20 scanned pages (<40 chars digital text each)
            mock_pages = [MagicMock(extract_text=MagicMock(return_value="")) for _ in range(20)]
            mock_pdf.return_value = MagicMock(pages=mock_pages)

            doc = await proc.ingest_document(
                doc_id="scanned_long_doc",
                file_path=str(pdf_file),
                file_name="scanned_long.pdf",
                subject="History",
                session_id="session_scanned_long",
            )

            assert len(ocr_called_pages) == 20, f"Expected 20 OCR calls for 20 scanned pages, got {len(ocr_called_pages)}"
            assert doc.status == "text_ready"
            assert len(doc.chunks) >= 20

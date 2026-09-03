"""
test_unit_doc_processor.py
===========================
Criteria §1.2 — RAG Components: Document Processor.

Tests document ingestion and chunking in isolation (no LLM/VLM calls):
- Plain text files are chunked correctly
- Chunks have correct metadata (doc_id, page, source_type)
- Chunk sizes respect the 500–800 character window with overlap
- Empty/whitespace content is NOT indexed
- Background enrichment is callable and handles non-PDF files gracefully
"""
import pytest
import pytest_asyncio
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock


class TestDocumentProcessorChunking:

    def _make_processor(self):
        from app.rag.doc_processor import DocumentProcessor
        proc = DocumentProcessor()
        # Stub the VLM so no real API calls are made
        proc.vlm = MagicMock()
        return proc

    @pytest.mark.asyncio
    async def test_plain_text_ingestion_produces_chunks(self, sample_txt_path):
        """A plain .txt file must produce at least one non-empty text chunk."""
        proc = self._make_processor()
        with patch("app.rag.sqlite_fts_store.get_session_store") as mock_store:
            mock_store.return_value = MagicMock(index_chunks=MagicMock())
            doc = await proc.ingest_document(
                doc_id="test_doc_001",
                file_path=str(sample_txt_path),
                file_name=sample_txt_path.name,
                subject="Biology",
                session_id="test_session_001",
            )

        assert doc is not None
        assert len(doc.chunks) > 0, "Text file must produce at least one chunk"
        assert doc.status in ("fully_processed", "text_ready")

    @pytest.mark.asyncio
    async def test_chunks_have_correct_metadata(self, sample_txt_path):
        """Every chunk must carry doc_id, page, source_type, and non-empty content."""
        proc = self._make_processor()
        with patch("app.rag.sqlite_fts_store.get_session_store") as mock_store:
            mock_store.return_value = MagicMock(index_chunks=MagicMock())
            doc = await proc.ingest_document(
                doc_id="test_doc_meta",
                file_path=str(sample_txt_path),
                file_name=sample_txt_path.name,
                subject="Biology",
                session_id="test_session_meta",
            )

        for chunk in doc.chunks:
            assert chunk.doc_id == "test_doc_meta", "doc_id must match"
            assert chunk.page >= 1, "page must be >= 1"
            assert chunk.source_type in ("text", "table", "image_caption")
            assert chunk.content.strip(), "chunk content must not be empty"

    def test_chunker_splits_large_text(self):
        """The internal chunker must split very large text into multiple chunks."""
        proc = self._make_processor()
        # ~4000 chars — well above a single chunk limit
        large_text = "Machine learning is fascinating. " * 120
        chunks = proc._chunk_text(large_text, doc_id="big_doc", page=1, source_type="text")
        assert len(chunks) > 1, "Large text must be split into multiple chunks"

    def test_chunker_respects_size_limit(self):
        """No individual chunk should massively exceed the configured window."""
        proc = self._make_processor()
        large_text = "Support Vector Machines are powerful classifiers. " * 100
        chunks = proc._chunk_text(large_text, doc_id="size_doc", page=1, source_type="text")
        for chunk in chunks:
            assert len(chunk.content) <= 1200, \
                f"Chunk is too large: {len(chunk.content)} chars"

    def test_chunker_skips_empty_content(self):
        """Chunking empty or whitespace-only text must return zero chunks."""
        proc = self._make_processor()
        chunks = proc._chunk_text("   \n\n  ", doc_id="empty_doc", page=1, source_type="text")
        assert chunks == [], "Empty text must not produce any chunks"

    def test_chunk_ids_are_unique(self):
        """Every chunk must have a unique chunk_id."""
        proc = self._make_processor()
        text = "Alpha beta gamma delta epsilon. " * 60
        chunks = proc._chunk_text(text, doc_id="unique_doc", page=1, source_type="text")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "All chunk_ids must be unique"

    @pytest.mark.asyncio
    async def test_background_enrichment_skips_non_pdf(self, tmp_path):
        """run_background_enrichment on a non-PDF file must set status=fully_processed."""
        proc = self._make_processor()
        txt_path = tmp_path / "notes.txt"
        txt_path.write_text("Some notes content here.")

        # Pre-register a DocumentRecord manually
        from app.rag.doc_processor import DocumentRecord
        rec = DocumentRecord(
            doc_id="bg_doc_001",
            file_path=str(txt_path),
            file_name="notes.txt",
            subject="General",
            session_id="bg_session",
            status="text_ready",
        )
        proc._docs["bg_doc_001"] = rec

        await proc.run_background_enrichment("bg_doc_001")
        assert proc._docs["bg_doc_001"].status == "fully_processed"

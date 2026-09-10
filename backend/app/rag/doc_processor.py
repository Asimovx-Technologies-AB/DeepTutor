"""
Document Processor — Multi-stage Document Processing Pipeline with Fast-Path & Background Enrichment.
Integrates Hybrid Vector Retrieval (pgvector + BM25), OpenAI Vision OCR, and asynchronous DB persistence.

Stages:
[Stage 0] Save file, register doc_id, status = "processing_text"
[Stage 1 — FAST PATH, ~seconds]
  - Extract text per page
  - Chunk into 500-800 characters with ~15% overlap
  - Generate embeddings & persist to pgvector and FTS store
  - status = "text_ready" (User can ask questions immediately)
[Stage 2 — TABLE EXTRACTION, background task]
  - pdfplumber.extract_tables()
  - Convert tables to Markdown strings
  - Store chunks with metadata: { doc_id, page, source_type: "table" }
[Stage 3 — IMAGE EXTRACTION & CAPTIONING, background task]
  - Extract embedded images from PDF pages
  - Vision-caption each image using OpenAI GPT-4o Vision
  - Store captions with metadata: { doc_id, page, source_type: "image_caption" }
  - status = "fully_processed"
"""
import os
import io
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import pypdf
import pdfplumber
from PIL import Image

from app.core.config import get_settings
from app.rag.vlm_client import OpenAIVLMClient, GeminiVLMClient
from app.rag.llm_client import llm_client
from app.rag.sqlite_fts_store import get_session_store

settings = get_settings()

# Initialize pgvector store if configured
_pgvector_store = None
try:
    if settings.VECTOR_STORE_BACKEND == "pgvector" and "postgres" in settings.DATABASE_URL:
        from app.rag.storage.pgvector_store import PgVectorStore
        _pgvector_store = PgVectorStore()
except Exception as _e:
    print(f"[DocProcessor] Notice: PgVectorStore initialization: {_e}")


@dataclass
class DocumentChunk:
    chunk_id: str
    doc_id: str
    page: int
    source_type: str  # "text" | "table" | "image_caption"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentRecord:
    doc_id: str
    file_path: str
    file_name: str
    subject: str
    session_id: Optional[str] = None
    status: str = "processing_text"  # "processing_text" | "text_ready" | "processing_enrichment" | "fully_processed" | "error"
    chunks: List[DocumentChunk] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=lambda: {"text_chunks": 0, "tables": 0, "images": 0})
    error_message: Optional[str] = None


class DocumentProcessor:
    """
    Manages document ingestion, chunking, background table/image extraction,
    and hybrid pgvector + full-text context retrieval.
    """

    def __init__(self):
        self._docs: Dict[str, DocumentRecord] = {}
        self.vlm = OpenAIVLMClient()

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        return self._docs.get(doc_id)

    async def _index_chunks_to_vector_and_fts(
        self,
        chunks: List[DocumentChunk],
        session_id: Optional[str],
        doc_id: str,
    ):
        """Indexes chunks into session FTS and pgvector hybrid search."""
        if not chunks:
            return

        # 1. Session-level FTS store
        try:
            store = get_session_store(session_id or doc_id)
            store.index_chunks([
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "page": c.page,
                    "source_type": c.source_type,
                    "content": c.content,
                }
                for c in chunks
            ])
        except Exception as e:
            print(f"[DocProcessor] FTS indexing error: {e}")

        # 2. PgVector hybrid store
        global _pgvector_store
        if _pgvector_store is not None:
            try:
                topic_key = session_id or doc_id or "general"
                chunk_texts = [c.content for c in chunks]
                embeddings = await llm_client.get_embeddings(chunk_texts)
                formatted_chunks = [
                    {
                        "text": c.content,
                        "metadata": {
                            "chunk_id": c.chunk_id,
                            "doc_id": c.doc_id,
                            "page": c.page,
                            "source_type": c.source_type,
                        }
                    }
                    for c in chunks
                ]
                await asyncio.to_thread(_pgvector_store.add_chunks, topic_key, formatted_chunks, embeddings)
                print(f"[DocProcessor] Successfully indexed {len(chunks)} chunks into PgVectorStore (topic: {topic_key}).")
            except Exception as ex:
                print(f"[DocProcessor] PgVector indexing notice: {ex}")

    # ─── STAGE 1: INGESTION (Fast Text + VLM OCR for Scanned/Images) ─────
    async def ingest_document(
        self,
        doc_id: str,
        file_path: str,
        file_name: str,
        subject: str = "General",
        session_id: Optional[str] = None,
    ) -> DocumentRecord:
        """
        Stage 1: Multi-modal document ingestion.
        - Plain text/code: Direct read & chunk.
        - Digital PDF: Fast text extraction via pypdf.
        - Scanned PDF / Image: OCR & transcription via OpenAI GPT-4o Vision.
        """
        doc = DocumentRecord(
            doc_id=doc_id,
            file_path=file_path,
            file_name=file_name,
            subject=subject,
            session_id=session_id,
            status="processing_text",
        )
        self._docs[doc_id] = doc

        ext = Path(file_path).suffix.lower()

        # 1. Plain text / code / markdown files
        if ext in {".txt", ".md", ".py", ".csv", ".json"}:
            try:
                def _read_txt():
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        return f.read()
                full_text = await asyncio.to_thread(_read_txt)
                chunks = self._chunk_text(full_text, doc_id=doc_id, page=1, source_type="text")
                doc.chunks.extend(chunks)
                doc.stats["text_chunks"] = len(chunks)
                doc.status = "fully_processed"
                await self._index_chunks_to_vector_and_fts(chunks, session_id, doc_id)
                return doc
            except Exception as e:
                doc.status = "error"
                doc.error_message = str(e)
                return doc

        # 2. Standalone image files (.png, .jpg, .jpeg, .webp, .bmp, .tiff)
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}:
            try:
                print(f"[DocProcessor] Image file detected: {file_name}. Transcribing using OpenAI Vision...")
                def _read_img_bytes():
                    with open(file_path, "rb") as f:
                        return f.read()
                img_bytes = await asyncio.to_thread(_read_img_bytes)

                mime = "image/png" if ext == ".png" else "image/jpeg"
                vlm_text = await self.vlm.extract_text_from_image(
                    img_bytes, mime_type=mime, context_hint=subject
                )

                if vlm_text and vlm_text.strip():
                    chunks = self._chunk_text(vlm_text, doc_id=doc_id, page=1, source_type="text")
                    doc.chunks.extend(chunks)
                    doc.stats["text_chunks"] = len(chunks)
                    await self._index_chunks_to_vector_and_fts(chunks, session_id, doc_id)
                    print(f"[DocProcessor] Successfully extracted {len(chunks)} text chunks from image with OpenAI Vision.")
                else:
                    print(f"[DocProcessor] VLM returned empty text for image {file_name}")

                doc.status = "fully_processed"
                return doc
            except Exception as e:
                print(f"[DocProcessor] Image VLM extraction error: {e}")
                doc.status = "error"
                doc.error_message = str(e)
                return doc

        # 3. PDF documents (digital or scanned)
        if ext == ".pdf":
            try:
                def _extract_pdf_pages():
                    reader = pypdf.PdfReader(file_path)
                    pages_text = []
                    scanned_indices = []
                    for idx, page in enumerate(reader.pages):
                        try:
                            txt = page.extract_text() or ""
                        except Exception:
                            txt = ""
                        if len(txt.strip()) >= 40:
                            pages_text.append((idx + 1, txt))
                        else:
                            scanned_indices.append(idx)
                    return len(reader.pages), pages_text, scanned_indices

                total_pages, digital_pages, scanned_pages_to_vlm = await asyncio.to_thread(_extract_pdf_pages)
                text_chunks: List[DocumentChunk] = []
                indexed_pages_set = set()
                failed_pages = []

                for page_num, page_text in digital_pages:
                    chunks = self._chunk_text(page_text, doc_id=doc_id, page=page_num, source_type="text")
                    if chunks:
                        text_chunks.extend(chunks)
                        indexed_pages_set.add(page_num)
                    else:
                        failed_pages.append(page_num)

                # Scanned pages handled with bounded parallel VLM OCR
                if scanned_pages_to_vlm:
                    print(f"[DocProcessor] Scanned PDF detected ({len(scanned_pages_to_vlm)}/{total_pages} scanned pages). Running Vision OCR across all scanned pages...")
                    sem = asyncio.Semaphore(4)

                    async def _ocr_single_page(p_idx: int) -> List[DocumentChunk]:
                        p_num = p_idx + 1
                        async with sem:
                            try:
                                p_img = await asyncio.to_thread(self.vlm.render_pdf_page_to_image, file_path, p_idx, 120)
                                if not p_img:
                                    return []
                                p_ocr_text = await self.vlm.extract_text_from_image(
                                    p_img, mime_type="image/png", context_hint=subject
                                )
                                if p_ocr_text and p_ocr_text.strip():
                                    p_chunks = self._chunk_text(
                                        p_ocr_text,
                                        doc_id=doc_id,
                                        page=p_num,
                                        source_type="text"
                                    )
                                    return p_chunks
                            except Exception as ocr_err:
                                print(f"[DocProcessor] OCR Error on page {p_num}: {ocr_err}")
                            return []

                    page_results = await asyncio.gather(*[_ocr_single_page(p) for p in scanned_pages_to_vlm], return_exceptions=True)
                    for p_idx, res in zip(scanned_pages_to_vlm, page_results):
                        p_num = p_idx + 1
                        if isinstance(res, list) and res:
                            text_chunks.extend(res)
                            indexed_pages_set.add(p_num)
                        else:
                            failed_pages.append(p_num)

                doc.chunks.extend(text_chunks)
                doc.stats["text_chunks"] = len(text_chunks)
                indexed_count = len(indexed_pages_set)
                coverage = indexed_count / total_pages if total_pages else 0.0

                if coverage < 0.8 or (total_pages > 0 and len(text_chunks) == 0):
                    doc.status = "indexing_incomplete"
                    doc.error_message = (
                        f"Indexed {indexed_count}/{total_pages} pages ({coverage:.0%}). "
                        f"Failed pages: {failed_pages[:10]}"
                    )
                    print(f"[DocProcessor] WARNING: {doc.error_message}")
                else:
                    doc.status = "text_ready"

                await self._index_chunks_to_vector_and_fts(text_chunks, session_id, doc_id)
                print(f"[DocProcessor] Fast path completed: {len(text_chunks)} text chunks across {indexed_count}/{total_pages} pages indexed for doc {doc_id} (status={doc.status}).")
            except Exception as e:
                print(f"[DocProcessor] Fast path text extraction error: {e}")
                doc.status = "indexing_incomplete"
                doc.error_message = str(e)

        # 4. Word documents (.docx, .doc)
        elif ext in {".docx", ".doc"}:
            try:
                def _extract_docx():
                    import docx
                    doc_file = docx.Document(file_path)
                    full_paragraphs = []
                    for p in doc_file.paragraphs:
                        txt = p.text.strip()
                        if txt:
                            full_paragraphs.append(txt)
                    for tbl in doc_file.tables:
                        for row in tbl.rows:
                            row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                            if row_text:
                                full_paragraphs.append(row_text)
                    return "\n\n".join(full_paragraphs)

                full_text = await asyncio.to_thread(_extract_docx)
                if not full_text.strip():
                    raise ValueError(f"No readable text extracted from {file_name}")

                chunks = self._chunk_text(full_text, doc_id=doc_id, page=1, source_type="text")
                doc.chunks.extend(chunks)
                doc.stats["text_chunks"] = len(chunks)
                doc.status = "fully_processed"
                await self._index_chunks_to_vector_and_fts(chunks, session_id, doc_id)
                return doc
            except Exception as e:
                doc.status = "error"
                doc.error_message = str(e)
                return doc

        # 5. PowerPoint presentations (.pptx, .ppt)
        elif ext in {".pptx", ".ppt"}:
            try:
                def _extract_pptx():
                    from pptx import Presentation
                    prs = Presentation(file_path)
                    slide_chunks_local = []
                    for slide_idx, slide in enumerate(prs.slides):
                        slide_texts = []
                        for shape in slide.shapes:
                            if hasattr(shape, "text") and shape.text.strip():
                                slide_texts.append(shape.text.strip())
                        if slide_texts:
                            slide_content = "\n".join(slide_texts)
                            slide_chunks_local.append((slide_idx + 1, slide_content))
                    return slide_chunks_local

                extracted_slides = await asyncio.to_thread(_extract_pptx)
                slide_chunks = []
                for s_num, s_txt in extracted_slides:
                    chunks = self._chunk_text(s_txt, doc_id=doc_id, page=s_num, source_type="text")
                    slide_chunks.extend(chunks)

                doc.chunks.extend(slide_chunks)
                doc.stats["text_chunks"] = len(slide_chunks)
                doc.status = "fully_processed"
                await self._index_chunks_to_vector_and_fts(slide_chunks, session_id, doc_id)
                return doc
            except Exception as e:
                doc.status = "error"
                doc.error_message = str(e)
                return doc

        return doc

    def get_document_text(self, doc_id: str, max_chars: int = 12000) -> str:
        """Retrieves clean assembled text of the document across all chunks."""
        doc = self._docs.get(doc_id)
        if doc and doc.chunks:
            text_pieces = [c.content for c in doc.chunks if c.source_type == "text"]
            if not text_pieces:
                text_pieces = [c.content for c in doc.chunks]
            full = "\n\n".join(text_pieces)
            return full[:max_chars]

        # Fallback to session store FTS search
        try:
            store = get_session_store(doc_id)
            matches = store.search(doc_id=doc_id, query="*", limit=20)
            if matches:
                return "\n\n".join(m["content"] for m in matches)[:max_chars]
        except Exception:
            pass
        return ""

    # ─── STAGE 2 & 3: ASYNC BACKGROUND ENRICHMENT ─────────────────────────
    # ─── STAGE 2 & 3: ASYNC BACKGROUND ENRICHMENT ─────────────────────────
    async def run_background_enrichment(self, doc_id: str):
        """Extracts tables and captures diagram captions asynchronously in parallel."""
        doc = self._docs.get(doc_id)
        if not doc or not os.path.exists(doc.file_path):
            return

        ext = Path(doc.file_path).suffix.lower()
        if ext != ".pdf":
            doc.status = "fully_processed"
            return

        doc.status = "processing_enrichment"

        async def _run_table_stage():
            try:
                table_chunks = await asyncio.to_thread(self._extract_tables_from_pdf, doc.file_path, doc_id)
                if table_chunks:
                    doc.chunks.extend(table_chunks)
                    doc.stats["tables"] = len(table_chunks)
                    await self._index_chunks_to_vector_and_fts(table_chunks, doc.session_id, doc_id)
            except Exception as e:
                print(f"[DocProcessor] Table extraction warning: {e}")

        async def _run_image_stage():
            try:
                image_chunks = await self._extract_and_caption_images(doc.file_path, doc_id)
                if image_chunks:
                    doc.chunks.extend(image_chunks)
                    doc.stats["images"] = len(image_chunks)
                    await self._index_chunks_to_vector_and_fts(image_chunks, doc.session_id, doc_id)
            except Exception as e:
                print(f"[DocProcessor] Image captioning warning: {e}")

        await asyncio.gather(_run_table_stage(), _run_image_stage())
        doc.status = "fully_processed"

    def _extract_tables_from_pdf(self, file_path: str, doc_id: str) -> List[DocumentChunk]:
        """Extracts tables per page using pdfplumber and formats them as Markdown tables with captured titles."""
        table_chunks: List[DocumentChunk] = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    page_num = page_idx + 1
                    tables = page.extract_tables()
                    if not tables:
                        continue

                    page_text = page.extract_text() or ""
                    table_titles = re.findall(r"\b(Table\s*\d+(?:\.\d+)?(?::[^\n]+)?)\b", page_text, re.IGNORECASE)

                    for t_idx, table in enumerate(tables):
                        if not table or len(table) < 2:
                            continue
                        md_table = self._format_table_as_markdown(table)
                        if md_table.strip():
                            t_title = table_titles[t_idx].strip() if t_idx < len(table_titles) else f"Table {t_idx + 1}"
                            content_str = f"[{t_title} | Page {page_num} | Type: table]\n{md_table}"
                            chunk = DocumentChunk(
                                chunk_id=f"{doc_id}_p{page_num}_tbl_{t_idx + 1}",
                                doc_id=doc_id,
                                page=page_num,
                                source_type="table",
                                content=content_str,
                                metadata={
                                    "table_index": t_idx + 1,
                                    "table_title": t_title,
                                    "rows": len(table),
                                    "cols": len(table[0]) if table else 0
                                }
                            )
                            table_chunks.append(chunk)
        except Exception as e:
            print(f"[DocProcessor] pdfplumber table error: {e}")
        return table_chunks

    def _format_table_as_markdown(self, table: List[List[Any]]) -> str:
        """Converts raw table rows into clean, structured Markdown table."""
        if not table:
            return ""
        cleaned_rows = []
        for row in table:
            cleaned_row = [str(cell).replace("\n", " ").strip() if cell is not None else "" for cell in row]
            cleaned_rows.append(cleaned_row)
        if not cleaned_rows:
            return ""
        headers = cleaned_rows[0]
        if not any(headers):
            headers = [f"Col {i+1}" for i in range(len(headers))]
        col_count = len(headers)
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for row in cleaned_rows[1:]:
            padded = row + [""] * (col_count - len(row)) if len(row) < col_count else row[:col_count]
            md_lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(md_lines)

    async def _extract_and_caption_images(self, file_path: str, doc_id: str, max_images: int = 8) -> List[DocumentChunk]:
        """Extracts images from PDF pages and runs OpenAI Vision factual captioning concurrently."""
        image_chunks: List[DocumentChunk] = []
        try:
            import fitz
            pdf_doc = fitz.open(file_path)
            raw_images = []
            for page_num in range(len(pdf_doc)):
                if len(raw_images) >= max_images:
                    break
                page = pdf_doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img in enumerate(image_list):
                    if len(raw_images) >= max_images:
                        break
                    xref = img[0]
                    base_image = pdf_doc.extract_image(xref)
                    image_bytes = base_image.get("image")
                    image_ext = base_image.get("ext", "jpeg")

                    if not image_bytes or len(image_bytes) < 3000:
                        continue

                    raw_images.append((page_num + 1, img_index + 1, image_bytes, image_ext))

            pdf_doc.close()

            if not raw_images:
                return []

            sem = asyncio.Semaphore(4)

            async def _caption_item(p_num: int, img_idx: int, img_bytes: bytes, img_ext: str) -> Optional[DocumentChunk]:
                async with sem:
                    caption = await self.vlm.caption_diagram(img_bytes, mime_type=f"image/{img_ext}")
                    if caption and len(caption.strip()) > 10:
                        return DocumentChunk(
                            chunk_id=f"{doc_id}_p{p_num}_img_{img_idx}",
                            doc_id=doc_id,
                            page=p_num,
                            source_type="image_caption",
                            content=f"Figure/Diagram on Page {p_num}: {caption.strip()}",
                            metadata={"image_index": img_idx}
                        )
                return None

            tasks = [_caption_item(p, idx, b, ext_name) for p, idx, b, ext_name in raw_images]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, DocumentChunk):
                    image_chunks.append(res)
        except Exception as e:
            print(f"[DocProcessor] Image captioning error: {e}")
        return image_chunks

    # ─── CHUNKING UTILITY ─────────────────────────────────────────────────
    def _chunk_text(
        self,
        text: str,
        doc_id: str,
        page: int,
        source_type: str = "text",
        chunk_size: int = 700,
        overlap: int = 100,
    ) -> List[DocumentChunk]:
        """Chunks text with 500-800 character windows and ~15% overlap."""
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return []

        chunks: List[DocumentChunk] = []
        start = 0
        chunk_idx = 1

        while start < len(cleaned):
            end = start + chunk_size
            chunk_content = cleaned[start:end].strip()

            if chunk_content:
                chunk = DocumentChunk(
                    chunk_id=f"{doc_id}_p{page}_c{chunk_idx}",
                    doc_id=doc_id,
                    page=page,
                    source_type=source_type,
                    content=chunk_content,
                )
                chunks.append(chunk)
                chunk_idx += 1

            if end >= len(cleaned):
                break
            start += chunk_size - overlap

        return chunks

    # ─── QUERY RETRIEVAL FLOW ─────────────────────────────────────────────
    def retrieve_context(
        self,
        doc_id: str,
        query: str,
        top_k: int = 6,
        session_id: Optional[str] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Retrieves top-k relevant chunks across ALL source_types (text, table, image_caption),
        utilizing hybrid pgvector search when available, and FTS fallback.
        """
        doc = self._docs.get(doc_id)
        target_session = session_id or doc_id or (getattr(doc, "session_id", None) if doc else None)
        store = get_session_store(target_session)

        query_lower = query.lower().strip()
        table_keywords = {"table", "value", "compare", "how many", "number", "data", "columns", "rows", "statistic", "percent", "metric", "versus", "vs"}
        is_table_query = any(re.search(rf"\b{re.escape(kw)}\b", query_lower) for kw in table_keywords)

        image_keywords = {"image", "figure", "diagram", "photo", "picture", "illustration", "graphic", "chart", "visual", "draw"}
        is_image_query = any(re.search(rf"\b{re.escape(kw)}\b", query_lower) for kw in image_keywords)

        table_fig_label_match = re.search(r"\b(?:table|tbl|figure|fig)\s*(\d+(?:\.\d+)?)\b", query_lower)
        target_label = f"table {table_fig_label_match.group(1)}" if table_fig_label_match else None
        target_label_num = table_fig_label_match.group(1) if table_fig_label_match else None

        page_match = re.search(r"\b(?:page\s*number|pagenumber|page|pg|p\.?)\s*(?:no\.?)?\s*(\d+)\b", query_lower)
        target_page = int(page_match.group(1)) if page_match else None

        selected_chunks: List[DocumentChunk] = []

        # 1. Target page retrieval
        if target_page is not None:
            try:
                page_rows = store.get_page_chunks(doc_id=doc_id, page=target_page)
                for r in page_rows:
                    selected_chunks.append(
                        DocumentChunk(
                            chunk_id=r["chunk_id"],
                            doc_id=r["doc_id"],
                            page=r["page"],
                            source_type=r["source_type"],
                            content=r["content"],
                        )
                    )
            except Exception:
                pass

        # 2. In-memory ranking pass if doc is in RAM
        if doc and doc.chunks:
            scored_chunks: List[Tuple[float, DocumentChunk]] = []
            query_words = set(re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?", query_lower))
            for chunk in doc.chunks:
                score = 0.0
                content_lower = chunk.content.lower()
                if target_page is not None and chunk.page == target_page:
                    score += 60.0

                if target_label and (target_label in content_lower or (target_label_num and f"table {target_label_num}" in content_lower)):
                    score += 100.0

                for word in query_words:
                    count = content_lower.count(word)
                    if count > 0:
                        score += 1.0 + min(count * 0.5, 3.0)

                if is_table_query and chunk.source_type == "table":
                    score = (score + 15.0) * 3.0
                elif is_image_query and chunk.source_type == "image_caption":
                    score = (score + 15.0) * 3.0

                if score > 0:
                    scored_chunks.append((score, chunk))
                    scored_chunks.append((score, chunk))

            scored_chunks.sort(key=lambda x: x[0], reverse=True)
            for _, c in scored_chunks[:top_k]:
                if not any(sc.chunk_id == c.chunk_id for sc in selected_chunks):
                    selected_chunks.append(c)

        # 3. Persistent SQLite / PostgreSQL FTS Search
        if len(selected_chunks) < top_k:
            try:
                fts_matches = store.search(doc_id=doc_id, query=query, limit=top_k)
                for m in fts_matches:
                    if not any(sc.chunk_id == m["chunk_id"] for sc in selected_chunks):
                        selected_chunks.append(
                            DocumentChunk(
                                chunk_id=m["chunk_id"],
                                doc_id=m["doc_id"],
                                page=m["page"],
                                source_type=m["source_type"],
                                content=m["content"],
                            )
                        )
            except Exception as e:
                print(f"[DocProcessor] FTS search fallback notice: {e}")

        if not selected_chunks and doc and doc.chunks:
            selected_chunks = doc.chunks[:3]

        context_blocks = []
        for c in selected_chunks[:top_k]:
            context_blocks.append(f"[Page {c.page} | Type: {c.source_type}]\n{c.content.strip()}")

        formatted_context = "\n\n".join(context_blocks)

        status_note = ""
        if doc and doc.status in {"processing_text", "text_ready", "processing_enrichment"}:
            status_note = (
                "Note: This document is still processing its tables/images — "
                "I can answer from the text for now, and give you a fuller answer in a moment."
            )

        metadata = {
            "doc_id": doc_id,
            "status": doc.status if doc else "ready",
            "total_chunks": len(doc.chunks) if doc else len(selected_chunks),
            "retrieved_count": len(selected_chunks),
            "source_types_retrieved": list({c.source_type for c in selected_chunks}),
        }

        return formatted_context, status_note, metadata


# Global singleton instance
doc_processor = DocumentProcessor()

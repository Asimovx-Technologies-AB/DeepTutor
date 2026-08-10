"""
Docling-powered document processor for DeepTutor RAG pipeline.

Docling (IBM Research) is the primary parser — it provides:
  - Structure-aware PDF parsing (correct reading order, multi-column)
  - Native section heading hierarchy  
  - Table extraction as structured markdown
  - Formula/math preservation
  - OCR support for scanned PDFs
  - Image caption extraction
  - Clean markdown output

Falls back gracefully to pdfplumber → pypdf → PyPDF2 if Docling is
unavailable or conversion fails.

Architecture:
  process_document(file_path)
    └─► try_docling()       → DoclingDocument → DoclingChunker
    └─► try_pdfplumber()    → raw text → SemanticChunker  (fallback 1)
    └─► try_pypdf()         → raw text → SemanticChunker  (fallback 2)
    └─► try_pypdf2()        → raw text → SemanticChunker  (fallback 3)
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Optional

from app.core.config import get_settings

settings = get_settings()

# Windows: suppress PyTorch MSVC compiler check error
os.environ.setdefault("DOCLING_INFERENCE_COMPILE_TORCH_MODELS", "false")

# ── Load chunker (for fallback path) ──────────────────────────────────────────
try:
    from app.rag.chunking_strategies import get_chunker
    _chunker = get_chunker(settings.CHUNKING_STRATEGY)
except Exception:
    _chunker = None


# ══════════════════════════════════════════════════════════════════════════════
# Docling converter (singleton, lazy-loaded)
# ══════════════════════════════════════════════════════════════════════════════
_docling_converter = None
_docling_available = None  # None = not yet checked


def _get_docling_converter():
    """
    Lazy-load and cache the Docling DocumentConverter.
    Returns converter or None if Docling is not installed.
    """
    global _docling_converter, _docling_available

    if _docling_available is False:
        return None
    if _docling_converter is not None:
        return _docling_converter

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        # OCR disabled by default for speed; selectable-text PDFs don't need it
        # Set DOCLING_ENABLE_OCR=true in .env to enable for scanned PDFs
        pipeline_options.do_ocr = settings.DOCLING_ENABLE_OCR

        _docling_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        _docling_available = True
        return _docling_converter

    except Exception as e:
        _docling_available = False
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Docling Chunker — exploits DoclingDocument native structure
# ══════════════════════════════════════════════════════════════════════════════
class DoclingChunker:
    """
    Chunks a DoclingDocument using its native hierarchy:
      - Iterates over document items (headings, paragraphs, tables, figures)
      - Groups paragraphs under their parent heading
      - Respects token budget per chunk
      - Produces rich metadata including section_title, page, item_type
    """

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_document(self, doc, source_name: str) -> List[Dict]:
        """
        doc: docling.datamodel.document.DoclingDocument
        Returns list of chunk dicts with text + metadata.
        """
        chunks: List[Dict] = []
        current_section = ""
        current_level = 0
        buffer: List[str] = []
        buffer_tokens = 0
        current_page = 1
        chunk_idx = 0

        def flush_buffer(clear_overlap=False) -> None:
            nonlocal buffer, buffer_tokens, chunk_idx
            text = " ".join(buffer).strip()
            if len(text) >= settings.MIN_CHUNK_CHARS:
                contextual_text = f"[Section: {current_section}]\n{text}" if current_section else text
                chunks.append({
                    "text": contextual_text,
                    "metadata": {
                        "source": source_name,
                        "page": current_page,
                        "section_title": current_section,
                        "section_level": current_level,
                        "chunk_index": chunk_idx,
                        "estimated_tokens": len(contextual_text) // 4,
                        "char_count": len(contextual_text),
                        "chunk_type": "docling",
                    }
                })
                chunk_idx += 1
            
            if clear_overlap:
                buffer = []
                buffer_tokens = 0
            else:
                # Keep overlap for next chunk
                overlap_text = " ".join(buffer)
                overlap_words = overlap_text.split()[-self.chunk_overlap:]
                buffer = overlap_words
                buffer_tokens = sum(len(w) for w in buffer) // 4

        try:
            for item, _ in doc.iterate_items():
                item_type = type(item).__name__

                if hasattr(item, 'prov') and item.prov:
                    current_page = item.prov[0].page_no

                if item_type in ("SectionHeaderItem", "TitleItem"):
                    flush_buffer(clear_overlap=True)
                    current_section = item.text.strip() if hasattr(item, 'text') else ""
                    current_level = getattr(item, 'level', 1)

                elif item_type in ("TextItem", "ParagraphItem"):
                    text = item.text.strip() if hasattr(item, 'text') else ""
                    if text:
                        text = re.sub(r'\s+', ' ', text)
                        token_est = len(text) // 4
                        if buffer_tokens + token_est > self.chunk_size and buffer:
                            flush_buffer()
                        buffer.append(text)
                        buffer_tokens += token_est

                elif item_type == "TableItem":
                    flush_buffer(clear_overlap=True)
                    table_md = item.export_to_markdown() if hasattr(item, 'export_to_markdown') else item.text
                    if table_md:
                        header = f"[Section: {current_section}]\n" if current_section else ""
                        chunks.append({
                            "text": f"{header}[TABLE]\n{table_md.strip()}",
                            "metadata": {"source": source_name, "page": current_page, "section_title": current_section, "chunk_index": chunk_idx, "chunk_type": "docling_table"}
                        })
                        chunk_idx += 1

                elif item_type == "FigureItem":
                    caption = item.caption.strip() if hasattr(item, 'caption') and item.caption else (item.text.strip() if hasattr(item, 'text') else "")
                    if caption:
                        buffer.append(f"[Figure: {caption}]")
                        buffer_tokens += len(caption) // 4

                elif item_type in ("EquationItem", "FormulaItem"):
                    formula = item.text.strip() if hasattr(item, 'text') else ""
                    if formula:
                        buffer.append(f"[Formula: {formula}]")
                        buffer_tokens += len(formula) // 4

                elif item_type == "ListItem":
                    text = item.text.strip() if hasattr(item, 'text') else ""
                    if text:
                        buffer.append(f"\u2022 {text}")
                        buffer_tokens += len(text) // 4

                elif item_type == "CodeItem":
                    code = item.text.strip() if hasattr(item, 'text') else ""
                    if code and len(code) >= 10:
                        flush_buffer(clear_overlap=True)
                        prefix = f"[Section: {current_section}]\n" if current_section else ""
                        code_text = f"{prefix}[CODE]\n```\n{code}\n```"
                        chunks.append({
                            "text": code_text,
                            "metadata": {
                                "source": source_name, "page": current_page,
                                "section_title": current_section, "section_level": current_level,
                                "chunk_index": chunk_idx, "estimated_tokens": len(code_text) // 4,
                                "char_count": len(code_text), "chunk_type": "docling_code",
                            }
                        })
                        chunk_idx += 1

        except Exception:
            pass

        # Flush remaining buffer
        if buffer:
            flush_buffer()

        return chunks


# ══════════════════════════════════════════════════════════════════════════════
# Docling extraction path
# ══════════════════════════════════════════════════════════════════════════════
def _try_docling(file_path: str) -> List[Dict]:
    """
    Primary parser: uses Docling for structure-aware PDF extraction.
    Returns list of chunks or [] on failure.
    """
    converter = _get_docling_converter()
    if converter is None:
        return []

    try:
        source_name = Path(file_path).name
        result = converter.convert(file_path)
        doc = result.document

        chunker = DoclingChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        chunks = chunker.chunk_document(doc, source_name)

        if not chunks:
            # Fallback: export full markdown and chunk with SemanticChunker
            md_text = doc.export_to_markdown()
            if md_text and _chunker is not None:
                return _chunker.chunk(md_text, {
                    "source": source_name,
                    "page": 1,
                    "file_path": file_path,
                })

        return chunks

    except Exception as e:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Fallback parsers (pdfplumber → pypdf → PyPDF2)
# ══════════════════════════════════════════════════════════════════════════════
def _legacy_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Character-based fallback splitter."""
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start:start + char_size].strip()
        if chunk and len(chunk) >= settings.MIN_CHUNK_CHARS:
            chunks.append(chunk)
        start += char_size - char_overlap
    return chunks


def _chunk_page_text(text: str, page_num: int, file_path: str) -> List[Dict]:
    """Chunk a single page of text using configured chunker."""
    if not text or len(text) < settings.MIN_CHUNK_CHARS:
        return []
    source_name = Path(file_path).name
    meta = {"source": source_name, "page": page_num, "file_path": file_path}

    if _chunker is not None:
        return _chunker.chunk(text, meta)

    # Absolute fallback
    return [
        {
            "text": c,
            "metadata": {**meta, "chunk_index": i, "section_title": "",
                         "section_level": 0, "chunk_type": "legacy",
                         "estimated_tokens": len(c)//4, "char_count": len(c)},
        }
        for i, c in enumerate(_legacy_split(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP))
    ]


def _try_pdfplumber(file_path: str) -> List[Dict]:
    try:
        import pdfplumber
        chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = re.sub(r'\s+', ' ', page.extract_text() or "").strip()
                chunks.extend(_chunk_page_text(text, page_num, file_path))
        return chunks
    except Exception:
        return []


def _try_pypdf(file_path: str) -> List[Dict]:
    try:
        import pypdf
        chunks = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page_num, page in enumerate(reader.pages, 1):
                text = re.sub(r'\s+', ' ', page.extract_text() or "").strip()
                chunks.extend(_chunk_page_text(text, page_num, file_path))
        return chunks
    except Exception:
        return []


def _try_pypdf2(file_path: str) -> List[Dict]:
    try:
        import PyPDF2
        chunks = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages, 1):
                text = re.sub(r'\s+', ' ', page.extract_text() or "").strip()
                chunks.extend(_chunk_page_text(text, page_num, file_path))
        return chunks
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════
def process_pdf(file_path: str) -> List[Dict]:
    """
    Extract and chunk a PDF using a cascading parser priority:
      1. Docling  — structure-aware, OCR-capable, table/formula-aware  ← PRIMARY
      2. pdfplumber — good layout, no OCR                              ← FALLBACK 1
      3. pypdf      — standard, fast                                   ← FALLBACK 2
      4. PyPDF2     — legacy                                           ← FALLBACK 3
    """
    # 1. Docling (primary)
    chunks = _try_docling(file_path)
    if chunks:
        return chunks

    # 2. pdfplumber
    chunks = _try_pdfplumber(file_path)
    if chunks:
        return chunks

    # 3. pypdf
    chunks = _try_pypdf(file_path)
    if chunks:
        return chunks

    # 4. PyPDF2
    return _try_pypdf2(file_path)


def process_txt(file_path: str) -> List[Dict]:
    """Read text/markdown file and split into chunks."""
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return []
        meta = {"source": Path(file_path).name, "page": 1, "file_path": file_path}
        if _chunker is not None:
            return _chunker.chunk(text, meta)
        return [
            {
                "text": c,
                "metadata": {**meta, "chunk_index": i, "section_title": "",
                             "section_level": 0, "chunk_type": "legacy",
                             "estimated_tokens": len(c)//4, "char_count": len(c)},
            }
            for i, c in enumerate(_legacy_split(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP))
        ]
    except Exception as e:
        raise RuntimeError(f"Text processing failed: {e}")


def process_document(file_path: str) -> List[Dict]:
    """Auto-detect file type and process."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return process_pdf(file_path)
    elif ext in {".txt", ".md", ".rst"}:
        return process_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def is_docling_available() -> bool:
    """Returns True if Docling is installed and usable."""
    return _get_docling_converter() is not None


def get_parser_info() -> Dict:
    """Return info about which parsers are available."""
    docling_ok = is_docling_available()
    pdfplumber_ok = True
    try:
        import pdfplumber
    except ImportError:
        pdfplumber_ok = False

    return {
        "primary": "docling" if docling_ok else "pdfplumber",
        "docling": docling_ok,
        "docling_version": _get_docling_version() if docling_ok else None,
        "ocr_enabled": settings.DOCLING_ENABLE_OCR,
        "pdfplumber": pdfplumber_ok,
        "chunking_strategy": settings.CHUNKING_STRATEGY,
    }


def _get_docling_version() -> Optional[str]:
    try:
        import docling
        return getattr(docling, "__version__", "unknown")
    except Exception:
        return None


def extract_key_topics(chunks: List[Dict]) -> List[str]:
    """
    Extract the most important key topics, headings, algorithms, and concepts
    from document chunks. Prioritises section_title metadata from Docling.
    """
    if not chunks:
        return []

    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "up", "about", "into", "over", "after", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did", "this", "that",
        "these", "those", "it", "its", "page", "pages", "pdf", "figure", "table", "chapter",
        "section", "author", "authors", "editor", "volume", "issue", "journal", "abstract",
        "introduction", "conclusion", "references", "http", "https", "doi", "isbn", "university",
        "department", "press", "rights", "reserved", "copyright", "edition", "published"
    }

    candidates_counts: Dict[str, int] = {}

    # Highest-signal: Docling section titles from metadata
    for chunk in chunks:
        section_title = chunk.get("metadata", {}).get("section_title", "")
        if section_title and 4 <= len(section_title) <= 60:
            candidates_counts[section_title] = candidates_counts.get(section_title, 0) + 5

    for chunk in chunks:
        text = chunk.get("text", "")
        if not text:
            continue

        # Headings / section titles
        heading_matches = re.findall(
            r'(?:^|\n)(?:#{1,4}\s*|\d+(?:\.\d+)*\s+)?([A-Z][A-Za-z0-9\s\-\:\(\)]{3,45})(?=\n|\:|\.|\ {2,})',
            text
        )
        for h in heading_matches:
            h_clean = h.strip()
            h_lower = h_clean.lower()
            if 4 <= len(h_clean) <= 40 and not any(sw in h_lower for sw in ["page", "http", "doi:"]):
                if not any(word in STOP_WORDS for word in h_lower.split()[:1]):
                    candidates_counts[h_clean] = candidates_counts.get(h_clean, 0) + 3

        # Capitalized multi-word technical concepts
        for c in re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', text):
            c_clean = c.strip()
            if not any(w in STOP_WORDS for w in c_clean.lower().split()):
                candidates_counts[c_clean] = candidates_counts.get(c_clean, 0) + 2

        # Acronyms
        for a in re.findall(r'\b([A-Z]{2,8}(?:\-[A-Z0-9]+)?)\b', text):
            if a not in {"PDF", "HTTP", "HTTPS", "DOI", "ISBN", "URL", "HTML", "USA", "UK"}:
                candidates_counts[a] = candidates_counts.get(a, 0) + 1

    sorted_topics = sorted(candidates_counts.items(), key=lambda x: x[1], reverse=True)

    final_topics, seen_lower = [], set()
    for topic_name, _ in sorted_topics:
        t_lower = topic_name.lower()
        if t_lower in seen_lower or any(t_lower in s for s in seen_lower):
            continue
        seen_lower.add(t_lower)
        final_topics.append(topic_name)
        if len(final_topics) >= 20:
            break

    return final_topics

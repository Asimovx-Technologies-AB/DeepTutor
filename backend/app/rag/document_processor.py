"""
Document processor: reads PDFs and text files, splits into chunks.
"""
import re
from pathlib import Path
from typing import List, Dict
from app.core.config import get_settings

settings = get_settings()


def _split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks by approximate token count (1 token ≈ 4 chars)."""
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    chunks = []
    start = 0
    while start < len(text):
        end = start + char_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += char_size - char_overlap
    return chunks


def _try_pdfplumber(file_path: str) -> List[Dict]:
    """Attempt extraction using pdfplumber."""
    try:
        import pdfplumber
        chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                text = re.sub(r'\s+', ' ', text).strip()
                if not text:
                    continue
                page_chunks = _split_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
                for i, chunk in enumerate(page_chunks):
                    chunks.append({
                        "text": chunk,
                        "metadata": {
                            "source": Path(file_path).name,
                            "page": page_num,
                            "chunk_index": i,
                            "file_path": file_path,
                        }
                    })
        return chunks
    except Exception:
        return []


def _try_pypdf(file_path: str) -> List[Dict]:
    """Attempt extraction using standard pypdf."""
    try:
        import pypdf
        chunks = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                text = re.sub(r'\s+', ' ', text).strip()
                if not text:
                    continue
                page_chunks = _split_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
                for i, chunk in enumerate(page_chunks):
                    chunks.append({
                        "text": chunk,
                        "metadata": {
                            "source": Path(file_path).name,
                            "page": page_num,
                            "chunk_index": i,
                            "file_path": file_path,
                        }
                    })
        return chunks
    except Exception:
        return []


def _try_pypdf2(file_path: str) -> List[Dict]:
    """Attempt extraction using legacy PyPDF2."""
    try:
        import PyPDF2
        chunks = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                text = re.sub(r'\s+', ' ', text).strip()
                if not text:
                    continue
                page_chunks = _split_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
                for i, chunk in enumerate(page_chunks):
                    chunks.append({
                        "text": chunk,
                        "metadata": {
                            "source": Path(file_path).name,
                            "page": page_num,
                            "chunk_index": i,
                            "file_path": file_path,
                        }
                    })
        return chunks
    except Exception:
        return []


def process_pdf(file_path: str) -> List[Dict]:
    """Extract text from PDF using a cascading fallback approach."""
    # 1. Try pdfplumber (best text layout recognition)
    chunks = _try_pdfplumber(file_path)
    if chunks:
        return chunks

    # 2. Try pypdf (modern pypdf standard)
    chunks = _try_pypdf(file_path)
    if chunks:
        return chunks

    # 3. Try PyPDF2 (legacy fallback)
    chunks = _try_pypdf2(file_path)
    if chunks:
        return chunks

    # If all parsers returned nothing
    return []


def process_txt(file_path: str) -> List[Dict]:
    """Read text file and split into chunks."""
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r'\s+', ' ', text).strip()
        raw_chunks = _split_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        return [
            {
                "text": chunk,
                "metadata": {
                    "source": Path(file_path).name,
                    "page": 1,
                    "chunk_index": i,
                    "file_path": file_path,
                }
            }
            for i, chunk in enumerate(raw_chunks)
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

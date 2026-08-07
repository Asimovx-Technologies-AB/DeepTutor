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


def extract_key_topics(chunks: List[Dict]) -> List[str]:
    """
    Extract the most important key topics, headings, algorithms, and concepts
    from document chunks during vectorization.
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

    for chunk in chunks:
        text = chunk.get("text", "")
        if not text:
            continue

        # 1. Regex for headings / section titles (e.g., '1.2 Support Vector Machines' or '### Feature Selection')
        heading_matches = re.findall(
            r'(?:^|\n)(?:#{1,4}\s*|\d+(?:\.\d+)*\s+)?([A-Z][A-Za-z0-9\s\-\:\(\)]{3,45})(?=\n|\:|\.|\s{2,})',
            text
        )
        for h in heading_matches:
            h_clean = h.strip()
            h_lower = h_clean.lower()
            if 4 <= len(h_clean) <= 40 and not any(sw in h_lower for sw in ["page", "http", "doi:"]):
                if not any(word in STOP_WORDS for word in h_lower.split()[:1]):
                    candidates_counts[h_clean] = candidates_counts.get(h_clean, 0) + 3

        # 2. Regex for capitalized multi-word technical concepts (e.g. 'Gradient Descent', 'Kernel Method')
        concept_matches = re.findall(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b',
            text
        )
        for c in concept_matches:
            c_clean = c.strip()
            c_lower = c_clean.lower()
            words = c_lower.split()
            if not any(w in STOP_WORDS for w in words):
                candidates_counts[c_clean] = candidates_counts.get(c_clean, 0) + 2

        # 3. Regex for prominent acronyms / capitalized methods (e.g., 'SVM', 'RLHF', 'BERT', 'CNN')
        acronym_matches = re.findall(r'\b([A-Z]{2,8}(?:\-[A-Z0-9]+)?)\b', text)
        for a in acronym_matches:
            if a not in {"PDF", "HTTP", "HTTPS", "DOI", "ISBN", "URL", "HTML", "USA", "UK"}:
                candidates_counts[a] = candidates_counts.get(a, 0) + 1

    # Sort candidates by frequency / score
    sorted_topics = sorted(candidates_counts.items(), key=lambda x: x[1], reverse=True)

    # Filter duplicates / substring matches
    final_topics = []
    seen_lower = set()

    for topic_name, score in sorted_topics:
        t_lower = topic_name.lower()
        if t_lower in seen_lower:
            continue
        # Avoid overlapping substrings if longer version exists
        if any(t_lower in s for s in seen_lower):
            continue

        seen_lower.add(t_lower)
        final_topics.append(topic_name)
        if len(final_topics) >= 15:
            break

    return final_topics


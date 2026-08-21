"""
Stage 1 — Semantic Chunker (500-1000 words per chunk)
=======================================================
Implements the diagram's specification:
  "Semantic Chunking: 500-1000 words + Page/Header Metadata"

Algorithm:
  1. Split page text into sentences.
  2. Group sentences into chunks targeting CHUNK_MIN_WORDS–CHUNK_MAX_WORDS.
  3. Keep CHUNK_OVERLAP_WORDS of overlap between consecutive chunks.
  4. Each chunk carries rich metadata:
       source, page, section_title, section_level, section_path,
       chunk_index, char_count, word_count, estimated_tokens,
       chunk_type, formulas (if any found in chunk)
"""
from __future__ import annotations

import re
from typing import List, Dict, Optional

from app.core.config import get_settings
from .section_tree import SectionNode, section_tree_to_lookup

settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
# Sentence Splitter
# ══════════════════════════════════════════════════════════════════════════════
_SENT_BOUNDARY = re.compile(
    r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s+'
)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences, preserving formula blocks."""
    # Protect formula blocks from sentence splitting
    placeholders: Dict[str, str] = {}
    for i, m in enumerate(re.finditer(r'\$\$.+?\$\$', text, re.DOTALL)):
        key = f"__FORMULA_{i}__"
        placeholders[key] = m.group()
        text = text[:m.start()] + key + text[m.end():]

    sents = _SENT_BOUNDARY.split(text)

    # Restore formulas
    restored = []
    for s in sents:
        for key, val in placeholders.items():
            s = s.replace(key, val)
        s = s.strip()
        if s:
            restored.append(s)
    return restored


def _count_words(text: str) -> int:
    return len(text.split())


# ══════════════════════════════════════════════════════════════════════════════
# SemanticChunker
# ══════════════════════════════════════════════════════════════════════════════
class SemanticChunker:
    """
    Chunks page dicts (from DocumentParser) into 500-1000 word chunks
    with rich page/section/formula metadata.
    """

    def __init__(
        self,
        min_words: int = None,
        max_words: int = None,
        overlap_words: int = None,
        min_chars: int = None,
    ):
        self.min_words = min_words or settings.CHUNK_MIN_WORDS
        self.max_words = max_words or settings.CHUNK_MAX_WORDS
        self.overlap_words = overlap_words or settings.CHUNK_OVERLAP_WORDS
        self.min_chars = min_chars or settings.MIN_CHUNK_CHARS

    def chunk_pages(
        self,
        pages: List[Dict],
        source_name: str,
        section_nodes: Optional[List[SectionNode]] = None,
    ) -> List[Dict]:
        """
        Convert list of page dicts to semantic chunks.

        Args:
            pages:         Output of DocumentParser.parse()
            source_name:   Display name of the document (file name)
            section_nodes: Output of build_section_tree() for metadata annotation

        Returns:
            List of chunk dicts:
            {
              "text": str,
              "metadata": {
                "source": str,
                "page": int,
                "section_title": str,
                "section_level": int,
                "section_path": str,
                "chunk_index": int,
                "char_count": int,
                "word_count": int,
                "estimated_tokens": int,
                "chunk_type": str,
                "formulas": List[str],
              }
            }
        """
        # Build page → section lookup for annotation
        page_section_lookup = section_tree_to_lookup(section_nodes) if section_nodes else {}

        chunks: List[Dict] = []
        chunk_idx = 0
        overlap_buffer: List[str] = []  # overlap words from previous chunk

        for page_data in pages:
            page_num = page_data.get("page", 1)
            text = page_data.get("text", "").strip()
            page_formulas = page_data.get("formulas", [])

            if not text or len(text) < self.min_chars:
                continue

            # Best matching section for this page
            section_nodes_for_page = page_section_lookup.get(page_num, [])
            section_title = section_nodes_for_page[0].title if section_nodes_for_page else ""
            section_level = section_nodes_for_page[0].level if section_nodes_for_page else 0
            section_path = section_nodes_for_page[0].full_path if section_nodes_for_page else ""

            sentences = _split_sentences(text)
            if not sentences:
                continue

            # Start buffer with overlap from previous page/chunk
            buffer: List[str] = list(overlap_buffer)
            buffer_words = _count_words(" ".join(buffer))

            extraction_method = page_data.get("extraction_method", "traditional")

            for sent in sentences:
                sent_words = _count_words(sent)

                # Flush if adding this sentence exceeds max
                if buffer_words + sent_words > self.max_words and buffer_words >= self.min_words:
                    chunk_text = " ".join(buffer).strip()
                    if len(chunk_text) >= self.min_chars:
                        chunk_formulas = [f for f in page_formulas if f in chunk_text]
                        # Prepend section header for context grounding
                        display_text = (
                            f"[Section: {section_path}]\n{chunk_text}"
                            if section_path else chunk_text
                        )
                        chunks.append(self._make_chunk(
                            display_text, source_name, page_num,
                            section_title, section_level, section_path,
                            chunk_idx, chunk_formulas, extraction_method,
                        ))
                        chunk_idx += 1

                    # Prepare overlap for next chunk
                    all_words = " ".join(buffer).split()
                    overlap_buffer = all_words[-self.overlap_words:]
                    buffer = list(overlap_buffer)
                    buffer_words = _count_words(" ".join(buffer))

                buffer.append(sent)
                buffer_words += sent_words

            # Flush remaining buffer at end of page
            if buffer:
                chunk_text = " ".join(buffer).strip()
                if len(chunk_text) >= self.min_chars:
                    chunk_formulas = [f for f in page_formulas if f in chunk_text]
                    display_text = (
                        f"[Section: {section_path}]\n{chunk_text}"
                        if section_path else chunk_text
                    )
                    chunks.append(self._make_chunk(
                        display_text, source_name, page_num,
                        section_title, section_level, section_path,
                        chunk_idx, chunk_formulas, extraction_method,
                    ))
                    chunk_idx += 1

                # Overlap buffer for next page
                all_words = " ".join(buffer).split()
                overlap_buffer = all_words[-self.overlap_words:]
            else:
                overlap_buffer = []

        return chunks

    def _make_chunk(
        self,
        text: str,
        source: str,
        page: int,
        section_title: str,
        section_level: int,
        section_path: str,
        chunk_index: int,
        formulas: List[str],
        extraction_method: str = "traditional",
    ) -> Dict:
        wc = _count_words(text)
        return {
            "text": text,
            "metadata": {
                "source": source,
                "page": page,
                "section_title": section_title,
                "section_level": section_level,
                "section_path": section_path,
                "chunk_index": chunk_index,
                "char_count": len(text),
                "word_count": wc,
                "estimated_tokens": wc * 4 // 3,   # ~1.33 tokens/word
                "chunk_type": "semantic",
                "has_formulas": len(formulas) > 0,
                "extraction_method": extraction_method,
            },
        }



# Singleton
semantic_chunker = SemanticChunker()

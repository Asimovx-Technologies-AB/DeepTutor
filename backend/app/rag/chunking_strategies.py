"""
Advanced Chunking Strategies for Industry-Level RAG.

Strategies:
  - SemanticChunker     : Splits on sentence/paragraph boundaries (DEFAULT)
  - SlidingWindowChunker: Fixed-size sliding window with sentence-complete edges
  - HierarchicalChunker : Produces (parent, child) chunk pairs for parent-doc retrieval

All strategies:
  - Preserve and prepend section headings to every chunk ("Section: X — ...")
  - Produce rich metadata: page, section_title, section_level, chunk_index,
    estimated_tokens, char_count, chunk_type
  - Discard chunks below MIN_CHUNK_CHARS
"""
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from app.core.config import get_settings

settings = get_settings()

# ── Sentence tokenizer (no heavy deps) ─────────────────────────────────────────
_SENT_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def _split_sentences(text: str) -> List[str]:
    """Lightweight sentence splitter — no NLTK required."""
    # Split on punctuation followed by whitespace + capital letter
    raw = _SENT_END.split(text)
    sentences = []
    for s in raw:
        s = s.strip()
        if s:
            sentences.append(s)
    return sentences


# ── Heading detector ───────────────────────────────────────────────────────────
_HEADING_PATTERNS = [
    # "## 2.3 Support Vector Machines" or "### Naive Bayes"
    re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE),
    # "2.3 Support Vector Machines" or "2. Random Forests"
    re.compile(r'^(\d+(?:\.\d+)*\.?)\s+([A-Z][^\n]{3,60})$', re.MULTILINE),
    # All-caps section headers "INTRODUCTION", "CONCLUSION"
    re.compile(r'^([A-Z][A-Z\s]{3,40})$', re.MULTILINE),
]


def _extract_sections(text: str) -> List[Tuple[str, str, int]]:
    """
    Extract (heading_text, body_text, heading_level) sections.
    Returns list of (heading, body, level) tuples.
    Falls back to single section if no headings found.
    """
    # Try to find heading positions using all patterns
    heading_spans: List[Tuple[int, str, int]] = []

    for pattern in _HEADING_PATTERNS:
        for match in pattern.finditer(text):
            line = match.group(0).strip()
            # Determine level from prefix
            if line.startswith('#'):
                level = len(match.group(1))
                title = match.group(2).strip()
            elif re.match(r'^\d', line):
                dots = line.split()[0].count('.')
                level = dots + 1
                title = ' '.join(line.split()[1:])
            else:
                level = 1
                title = line
            heading_spans.append((match.start(), title, level))

    if not heading_spans:
        return [("", text, 0)]

    # Sort by position
    heading_spans.sort(key=lambda x: x[0])

    sections = []
    for i, (pos, title, level) in enumerate(heading_spans):
        next_pos = heading_spans[i + 1][0] if i + 1 < len(heading_spans) else len(text)
        body = text[pos:next_pos].strip()
        # Remove the heading line itself from body
        body_lines = body.split('\n')
        body = '\n'.join(body_lines[1:]).strip() if len(body_lines) > 1 else ""
        if body:
            sections.append((title, body, level))

    # Add any text before first heading
    if heading_spans[0][0] > 0:
        preamble = text[:heading_spans[0][0]].strip()
        if len(preamble) > settings.MIN_CHUNK_CHARS:
            sections.insert(0, ("Introduction", preamble, 0))

    return sections if sections else [("", text, 0)]


def _tokens_approx(text: str) -> int:
    """Fast token count approximation (1 token ≈ 4 chars)."""
    return len(text) // 4


# ══════════════════════════════════════════════════════════════════════════════
# SemanticChunker
# ══════════════════════════════════════════════════════════════════════════════
class SemanticChunker:
    """
    Splits documents into semantically coherent chunks respecting:
    - Sentence boundaries (no mid-sentence splits)
    - Paragraph structure
    - Section headings (prepended to every chunk for context)

    Chunks are sized by approximate token count with configurable overlap.
    """

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        min_chunk_chars: int = None,
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.min_chunk_chars = min_chunk_chars or settings.MIN_CHUNK_CHARS

    def chunk(self, text: str, metadata: Dict) -> List[Dict]:
        """
        Chunk a page/section of text.
        metadata must contain at least: source, page
        """
        if not text or len(text) < self.min_chunk_chars:
            return []

        sections = _extract_sections(text)
        chunks: List[Dict] = []
        chunk_idx = 0

        for heading, body, level in sections:
            section_chunks = self._chunk_section(body, heading, level)
            for raw_chunk, section_title, section_level in section_chunks:
                raw_chunk = raw_chunk.strip()
                if len(raw_chunk) < self.min_chunk_chars:
                    continue

                # Prepend section heading to each chunk for contextual retrieval
                if section_title:
                    contextual_text = f"[Section: {section_title}]\n{raw_chunk}"
                else:
                    contextual_text = raw_chunk

                chunk_meta = {
                    **metadata,
                    "section_title": section_title,
                    "section_level": section_level,
                    "chunk_index": chunk_idx,
                    "estimated_tokens": _tokens_approx(contextual_text),
                    "char_count": len(contextual_text),
                    "chunk_type": "semantic",
                }
                chunks.append({
                    "text": contextual_text,
                    "metadata": chunk_meta,
                })
                chunk_idx += 1

        return chunks

    def _chunk_section(
        self, body: str, heading: str, level: int
    ) -> List[Tuple[str, str, int]]:
        """Split a section body into token-limited chunks at sentence boundaries."""
        sentences = _split_sentences(body)
        if not sentences:
            return []

        results: List[Tuple[str, str, int]] = []
        current_sentences: List[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = _tokens_approx(sentence)

            # If single sentence overflows, split it at word boundary
            if sentence_tokens > self.chunk_size:
                if current_sentences:
                    results.append((' '.join(current_sentences), heading, level))
                    current_sentences = []
                    current_tokens = 0
                # Hard-split long sentence
                words = sentence.split()
                word_chunk: List[str] = []
                word_tokens = 0
                for word in words:
                    word_tokens += len(word) // 4 + 1
                    word_chunk.append(word)
                    if word_tokens >= self.chunk_size:
                        results.append((' '.join(word_chunk), heading, level))
                        word_chunk = []
                        word_tokens = 0
                if word_chunk:
                    current_sentences = [' '.join(word_chunk)]
                    current_tokens = word_tokens
                continue

            if current_tokens + sentence_tokens > self.chunk_size and current_sentences:
                results.append((' '.join(current_sentences), heading, level))
                # Overlap: keep last N tokens worth of sentences
                overlap_tokens = 0
                overlap_sentences: List[str] = []
                for s in reversed(current_sentences):
                    st = _tokens_approx(s)
                    if overlap_tokens + st <= self.chunk_overlap:
                        overlap_sentences.insert(0, s)
                        overlap_tokens += st
                    else:
                        break
                current_sentences = overlap_sentences
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_tokens += sentence_tokens

        if current_sentences:
            results.append((' '.join(current_sentences), heading, level))

        return results


# ══════════════════════════════════════════════════════════════════════════════
# SlidingWindowChunker
# ══════════════════════════════════════════════════════════════════════════════
class SlidingWindowChunker:
    """
    Fixed-size sliding window chunker that still respects sentence boundaries.
    Simpler than SemanticChunker, useful as fallback.
    """

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None, min_chunk_chars: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.min_chunk_chars = min_chunk_chars or settings.MIN_CHUNK_CHARS

    def chunk(self, text: str, metadata: Dict) -> List[Dict]:
        sentences = _split_sentences(text)
        if not sentences:
            return []
        chunks = []
        idx = 0
        buf: List[str] = []
        buf_tokens = 0

        def flush(buf: List[str], idx: int) -> Optional[Dict]:
            joined = ' '.join(buf).strip()
            if len(joined) < self.min_chunk_chars:
                return None
            return {
                "text": joined,
                "metadata": {
                    **metadata,
                    "chunk_index": idx,
                    "estimated_tokens": _tokens_approx(joined),
                    "char_count": len(joined),
                    "chunk_type": "sliding_window",
                    "section_title": "",
                    "section_level": 0,
                },
            }

        for sent in sentences:
            st = _tokens_approx(sent)
            if buf_tokens + st > self.chunk_size and buf:
                c = flush(buf, idx)
                if c:
                    chunks.append(c)
                    idx += 1
                # Overlap
                overlap_buf: List[str] = []
                overlap_tokens = 0
                for s in reversed(buf):
                    ot = _tokens_approx(s)
                    if overlap_tokens + ot <= self.chunk_overlap:
                        overlap_buf.insert(0, s)
                        overlap_tokens += ot
                    else:
                        break
                buf = overlap_buf
                buf_tokens = overlap_tokens
            buf.append(sent)
            buf_tokens += st

        if buf:
            c = flush(buf, idx)
            if c:
                chunks.append(c)
        return chunks


# ══════════════════════════════════════════════════════════════════════════════
# HierarchicalChunker
# ══════════════════════════════════════════════════════════════════════════════
class HierarchicalChunker:
    """
    Produces (parent_chunk, child_chunks) pairs.
    - Parent: full section (large context)
    - Children: sentence-level chunks for precise retrieval

    Store children in vector DB; retrieve children, then fetch parent
    for LLM context (Parent-Document Retrieval pattern).
    """

    def __init__(self, parent_size: int = 1024, child_size: int = 256, min_chunk_chars: int = None):
        self.parent_size = parent_size
        self.child_size = child_size
        self.min_chunk_chars = min_chunk_chars or settings.MIN_CHUNK_CHARS
        self._parent_chunker = SlidingWindowChunker(chunk_size=parent_size, chunk_overlap=0)
        self._child_chunker = SemanticChunker(chunk_size=child_size, chunk_overlap=32)

    def chunk(self, text: str, metadata: Dict) -> List[Dict]:
        """Returns child chunks with parent_id in metadata."""
        parents = self._parent_chunker.chunk(text, metadata)
        all_children: List[Dict] = []

        for parent_idx, parent in enumerate(parents):
            children = self._child_chunker.chunk(parent["text"], {
                **parent["metadata"],
                "parent_id": f"{metadata.get('source', 'doc')}_p{metadata.get('page', 0)}_parent{parent_idx}",
                "parent_text": parent["text"],
                "chunk_type": "hierarchical_child",
            })
            # Override chunk index to be globally unique
            for i, child in enumerate(children):
                child["metadata"]["chunk_index"] = parent_idx * 1000 + i
            all_children.extend(children)

        return all_children


# ══════════════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════════════
def get_chunker(strategy: str = None):
    """Return the configured chunker based on CHUNKING_STRATEGY setting."""
    strategy = strategy or settings.CHUNKING_STRATEGY
    if strategy == "sliding_window":
        return SlidingWindowChunker()
    elif strategy == "hierarchical":
        return HierarchicalChunker()
    else:
        return SemanticChunker()  # Default: semantic

"""
Knowledge Tiler — Semantic chunking with 17 knowledge box classifications.

The core innovation replacing naive character-window chunking.  Every chunk
produced is classified into one of the 17 KnowledgeBoxType categories and
enriched with structural metadata: section path, named concepts, parent/child
hierarchy, confidence scores, and provenance tracking.

Knowledge Box Types:
    paragraph, definition, concept, heading, example, explanation,
    procedure, formula, theorem, proof, table, figure, diagram,
    note, warning, question, exercise
"""
from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.documents.extraction.text_summarizer import TextSummarizer
from app.documents.models import (
    EXTRACTION_CONFIDENCE,
    KNOWLEDGE_BOX_WEIGHTS,
    EquationData,
    FigureData,
    KnowledgeBoxType,
    KnowledgeChunk,
    PageContent,
    TableData,
)

logger = logging.getLogger(__name__)


class KnowledgeTiler:
    """
    Converts extracted pages into semantically-enriched KnowledgeChunks.

    Each chunk is classified into one of 17 knowledge box types and carries
    rich metadata for downstream retrieval, quiz generation, and analytics.
    """

    def __init__(
        self,
        target_size: int = 650,
        overlap_pct: float = 0.15,
        min_chunk_chars: int = 40,
    ) -> None:
        self.target_size = target_size
        self.overlap_pct = overlap_pct
        self.min_chunk_chars = min_chunk_chars
        self.summarizer = TextSummarizer()

    # ── Main entry point ──────────────────────────────────────────────────

    def tile_document(
        self,
        pages: List[PageContent],
        doc_id: str,
        doc_name: str,
    ) -> List[KnowledgeChunk]:
        """Converts extracted pages into KnowledgeChunks with full metadata.

        This is the main pipeline entry point.  It:
        1. Detects headings across all pages to build the section tree
        2. Tiles text content with sentence-boundary awareness
        3. Creates dedicated chunks for tables, figures, and equations
        4. Assigns knowledge box types to every chunk
        5. Builds parent-child relationships
        6. Computes confidence and weight scores

        Args:
            pages: List of PageContent from the extraction stage.
            doc_id: Document identifier.
            doc_name: Display name of the document.

        Returns:
            List of KnowledgeChunks ready for quality validation.
        """
        # 1. Build global heading index across all pages
        all_text = "\n\n".join(p.raw_text for p in pages if p.raw_text)
        headings = self.summarizer.detect_headings(all_text)

        # 2. Tile each page
        all_chunks: List[KnowledgeChunk] = []
        char_offset = 0  # Track position for section path lookup

        for page in pages:
            # Text chunks
            text_chunks = self._tile_text_page(
                page, doc_id, doc_name, headings, char_offset
            )
            all_chunks.extend(text_chunks)

            # Table chunks
            for table in page.tables:
                tbl_chunk = self._tile_table(table, doc_id, doc_name, headings, char_offset)
                all_chunks.append(tbl_chunk)

            # Figure chunks
            for figure in page.figures:
                fig_chunk = self._tile_figure(figure, doc_id, doc_name)
                all_chunks.append(fig_chunk)

            # Equation chunks (standalone display equations only)
            for equation in page.equations:
                if equation.is_display:
                    eq_chunk = self._tile_equation(
                        equation, doc_id, doc_name, headings, char_offset
                    )
                    all_chunks.append(eq_chunk)

            char_offset += len(page.raw_text) + 2  # +2 for \n\n separator

        # 3. Assign parent-child relationships
        all_chunks = self._assign_parent_child(all_chunks)

        # 4. Compute weights
        for chunk in all_chunks:
            chunk.weight = self._compute_weight(chunk)

        logger.info(
            "[KnowledgeTiler] Tiled %d chunks from %d pages for doc %s. "
            "Types: %s",
            len(all_chunks), len(pages), doc_id,
            dict(self._count_by_type(all_chunks)),
        )

        return all_chunks

    # ── Text page tiling ──────────────────────────────────────────────────

    def _tile_text_page(
        self,
        page: PageContent,
        doc_id: str,
        doc_name: str,
        headings: List[Dict[str, Any]],
        char_offset: int,
    ) -> List[KnowledgeChunk]:
        """Tiles a page's text into sentence-boundary-aware chunks.

        Each chunk is classified into a knowledge box type based on its
        content patterns.
        """
        text = page.raw_text
        if not text or len(text.strip()) < self.min_chunk_chars:
            return []

        # Clean whitespace
        text = " ".join(text.split())
        raw_chunks = self._split_text(text)

        chunks: List[KnowledgeChunk] = []
        for c_idx, chunk_text in enumerate(raw_chunks):
            if len(chunk_text) < self.min_chunk_chars:
                continue

            # Classify knowledge box type
            box_type = self.summarizer.classify_knowledge_box(chunk_text)

            # Get section path
            section_path = self.summarizer.build_section_path(
                headings, char_offset + text.find(chunk_text[:50])
            )

            # Extract named concepts
            concepts = self.summarizer.extract_concepts_heuristic(chunk_text)

            # Compute confidence
            confidence = self._compute_confidence(
                page.extraction_method, box_type
            )

            # Build content with document context prefix
            content = f"[Doc: {doc_name} | Page {page.page_num} | Type: {box_type.value}] {chunk_text}"

            chunks.append(KnowledgeChunk(
                chunk_id=f"{doc_id}_p{page.page_num}_c{c_idx}",
                doc_id=doc_id,
                content=content,
                knowledge_box=box_type,
                topic=section_path.split(" > ")[0] if section_path else "",
                chapter_section=section_path,
                page=page.page_num,
                named_concepts=concepts,
                confidence=confidence,
                provenance={
                    "parser": "pymupdf",
                    "method": page.extraction_method,
                    "quality_score": page.quality_score,
                },
            ))

        return chunks

    # ── Table tiling ──────────────────────────────────────────────────────

    def _tile_table(
        self,
        table: TableData,
        doc_id: str,
        doc_name: str,
        headings: List[Dict[str, Any]],
        char_offset: int,
    ) -> KnowledgeChunk:
        """Creates a single KnowledgeChunk for a table."""
        content = (
            f"[{table.title} | Page {table.page_num} | Type: table]\n"
            f"{table.markdown}"
        )

        section_path = self.summarizer.build_section_path(headings, char_offset)

        return KnowledgeChunk(
            chunk_id=f"{doc_id}_p{table.page_num}_tbl_{table.table_index}",
            doc_id=doc_id,
            content=content,
            knowledge_box=KnowledgeBoxType.TABLE,
            topic=section_path.split(" > ")[0] if section_path else "",
            chapter_section=section_path,
            page=table.page_num,
            named_concepts=[table.title] if table.title else [],
            confidence=EXTRACTION_CONFIDENCE.get("pdfplumber_table", 0.85),
            provenance={
                "parser": "pdfplumber",
                "method": "table_extraction",
                "row_count": table.row_count,
                "col_count": table.col_count,
            },
        )

    # ── Figure tiling ─────────────────────────────────────────────────────

    def _tile_figure(
        self,
        figure: FigureData,
        doc_id: str,
        doc_name: str,
    ) -> KnowledgeChunk:
        """Creates a KnowledgeChunk for a figure/diagram."""
        # Classify as diagram vs figure based on caption content
        box_type = KnowledgeBoxType.DIAGRAM
        if figure.caption:
            caption_lower = figure.caption.lower()
            if any(w in caption_lower for w in ("photo", "photograph", "picture", "image")):
                box_type = KnowledgeBoxType.FIGURE

        content = (
            f"Figure/Diagram on Page {figure.page_num}: "
            f"{figure.caption}" if figure.caption
            else f"Figure on Page {figure.page_num} (no caption available)"
        )

        return KnowledgeChunk(
            chunk_id=f"{doc_id}_p{figure.page_num}_fig_{figure.image_index}",
            doc_id=doc_id,
            content=content,
            knowledge_box=box_type,
            page=figure.page_num,
            confidence=EXTRACTION_CONFIDENCE.get("vlm_figure_caption", 0.60),
            provenance={
                "parser": "pymupdf",
                "method": "vlm_figure_caption",
                "mime_type": figure.mime_type,
            },
        )

    # ── Equation tiling ───────────────────────────────────────────────────

    def _tile_equation(
        self,
        equation: EquationData,
        doc_id: str,
        doc_name: str,
        headings: List[Dict[str, Any]],
        char_offset: int,
    ) -> KnowledgeChunk:
        """Creates a KnowledgeChunk for a standalone equation."""
        content = f"[Formula | Page {equation.page_num}] {equation.latex}"
        if equation.context_text:
            content += f"\nContext: {equation.context_text}"

        section_path = self.summarizer.build_section_path(headings, char_offset)

        return KnowledgeChunk(
            chunk_id=f"{doc_id}_p{equation.page_num}_eq_{hash(equation.latex) % 10000}",
            doc_id=doc_id,
            content=content,
            knowledge_box=KnowledgeBoxType.FORMULA,
            topic=section_path.split(" > ")[0] if section_path else "",
            chapter_section=section_path,
            page=equation.page_num,
            named_concepts=[],
            confidence=EXTRACTION_CONFIDENCE.get("regex_equation", 0.90),
            provenance={
                "parser": "regex",
                "method": "regex_equation",
                "is_display": equation.is_display,
            },
        )

    # ── Sentence-boundary-aware text splitting ────────────────────────────

    def _split_text(self, text: str) -> List[str]:
        """Splits text into chunks with sentence-boundary awareness.

        Target size is self.target_size characters with self.overlap_pct
        overlap.  Attempts to split at sentence boundaries (. ! ? ;).
        """
        if not text:
            return []

        if len(text) <= self.target_size:
            return [text]

        overlap_chars = int(self.target_size * self.overlap_pct)
        chunks: List[str] = []
        start = 0

        while start < len(text):
            end = start + self.target_size
            if end >= len(text):
                chunk = text[start:].strip()
                if chunk:
                    chunks.append(chunk)
                break

            # Try to find a sentence boundary
            boundary = max(
                text.rfind(". ", start, end),
                text.rfind("! ", start, end),
                text.rfind("? ", start, end),
                text.rfind("; ", start, end),
            )

            if boundary != -1 and boundary > start + (self.target_size // 2):
                chunk = text[start:boundary + 1].strip()
                if chunk:
                    chunks.append(chunk)
                start = boundary + 1
            else:
                # Fallback: split at word boundary
                space = text.rfind(" ", start, end)
                if space != -1 and space > start:
                    chunk = text[start:space].strip()
                    if chunk:
                        chunks.append(chunk)
                    start = space + 1
                else:
                    chunk = text[start:end].strip()
                    if chunk:
                        chunks.append(chunk)
                    start = end - overlap_chars

        return chunks

    # ── Parent-child hierarchy ────────────────────────────────────────────

    @staticmethod
    def _assign_parent_child(
        chunks: List[KnowledgeChunk],
    ) -> List[KnowledgeChunk]:
        """Builds parent-child relationships based on section hierarchy.

        A heading chunk is the parent of all subsequent non-heading chunks
        in the same section until the next heading at the same or higher level.
        """
        # Index heading chunks
        heading_stack: List[KnowledgeChunk] = []

        for chunk in chunks:
            if chunk.knowledge_box == KnowledgeBoxType.HEADING:
                # Pop same-level or lower headings from stack
                while heading_stack:
                    heading_stack.pop()
                heading_stack.append(chunk)
            elif heading_stack:
                # Link to the most recent heading as parent
                parent = heading_stack[-1]
                chunk.parent_chunk_id = parent.chunk_id
                if chunk.chunk_id not in parent.child_chunk_ids:
                    parent.child_chunk_ids.append(chunk.chunk_id)

        return chunks

    # ── Confidence computation ────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(
        extraction_method: str,
        box_type: KnowledgeBoxType,
    ) -> float:
        """Computes confidence score based on extraction method and content type.

        Digital text gets high confidence (0.95), VLM OCR gets lower (0.70),
        and specific box types may adjust slightly.
        """
        base = EXTRACTION_CONFIDENCE.get(extraction_method, 0.80)

        # Slight adjustments by box type
        if box_type in (KnowledgeBoxType.HEADING, KnowledgeBoxType.DEFINITION):
            base = min(base + 0.03, 1.0)  # Headings/defs are easier to detect
        elif box_type in (KnowledgeBoxType.PROOF, KnowledgeBoxType.PROCEDURE):
            base = max(base - 0.02, 0.0)  # Slightly harder to detect accurately

        return round(base, 3)

    # ── Weight computation ────────────────────────────────────────────────

    @staticmethod
    def _compute_weight(chunk: KnowledgeChunk) -> float:
        """Computes retrieval importance weight based on knowledge box type,
        concept count, and content length.
        """
        base_weight = KNOWLEDGE_BOX_WEIGHTS.get(chunk.knowledge_box, 1.0)

        # Boost for chunks with named concepts
        if chunk.named_concepts:
            base_weight += min(len(chunk.named_concepts) * 0.05, 0.3)

        # Slight boost for medium-length chunks (most informative)
        content_len = len(chunk.content)
        if 200 <= content_len <= 800:
            base_weight += 0.1
        elif content_len < 100:
            base_weight -= 0.2

        return round(max(0.1, base_weight), 3)

    # ── Stats helper ──────────────────────────────────────────────────────

    @staticmethod
    def _count_by_type(
        chunks: List[KnowledgeChunk],
    ) -> Dict[str, int]:
        """Counts chunks by knowledge box type."""
        counts: Dict[str, int] = {}
        for chunk in chunks:
            key = chunk.knowledge_box.value
            counts[key] = counts.get(key, 0) + 1
        return counts

"""
Quality Validator — Post-tiling quality assurance and CPAR validation.

Validates KnowledgeChunks after tiling: removes too-short chunks,
deduplicates by content hash, detects garbled text, and computes
the DocumentIntelligence analytics summary.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import List

from app.documents.models import (
    CanonicalDocument,
    DocumentIntelligence,
    KnowledgeChunk,
    PipelineDocument,
)

logger = logging.getLogger(__name__)


class QualityValidator:
    """Post-tiling quality assurance producing CanonicalDocument."""

    def __init__(self, min_chunk_chars: int = 40) -> None:
        self.min_chunk_chars = min_chunk_chars

    # ── Main entry ────────────────────────────────────────────────────────

    def validate(
        self,
        document: PipelineDocument,
        chunks: List[KnowledgeChunk],
    ) -> CanonicalDocument:
        """Validates chunks and produces a CanonicalDocument.

        Steps:
        1. Remove too-short chunks
        2. Deduplicate by content hash
        3. Flag garbled chunks
        4. Compute DocumentIntelligence

        Args:
            document: The pipeline document envelope.
            chunks: Raw KnowledgeChunks from the Knowledge Tiler.

        Returns:
            CanonicalDocument with validated chunks and intelligence data.
        """
        errors: List[str] = []
        original_count = len(chunks)

        # 1. Remove too-short chunks
        chunks = self._remove_too_short(chunks)
        removed_short = original_count - len(chunks)
        if removed_short > 0:
            logger.info(
                "[QualityValidator] Removed %d chunks below %d chars",
                removed_short, self.min_chunk_chars,
            )

        # 2. Deduplicate
        pre_dedup = len(chunks)
        chunks = self._deduplicate(chunks)
        removed_dupes = pre_dedup - len(chunks)
        if removed_dupes > 0:
            logger.info("[QualityValidator] Removed %d duplicate chunks", removed_dupes)

        # 3. Flag garbled text
        chunks, garbled_count = self._filter_garbled(chunks)
        if garbled_count > 0:
            errors.append(f"{garbled_count} chunks had garbled/encoding issues")
            logger.warning("[QualityValidator] %d garbled chunks removed", garbled_count)

        # 4. Compute intelligence
        intelligence = self._compute_intelligence(document, chunks, errors)

        return CanonicalDocument(
            document=document,
            chunks=chunks,
            intelligence=intelligence,
        )

    # ── Step 1: Minimum length filter ─────────────────────────────────────

    def _remove_too_short(
        self,
        chunks: List[KnowledgeChunk],
    ) -> List[KnowledgeChunk]:
        """Removes chunks with content below minimum character threshold."""
        return [
            c for c in chunks
            if len(c.content.strip()) >= self.min_chunk_chars
        ]

    # ── Step 2: Content-hash deduplication ────────────────────────────────

    @staticmethod
    def _deduplicate(
        chunks: List[KnowledgeChunk],
    ) -> List[KnowledgeChunk]:
        """Removes duplicate chunks by content hash within the document."""
        seen: set = set()
        unique: List[KnowledgeChunk] = []

        for chunk in chunks:
            # Hash the actual content (skip the metadata prefix)
            content = chunk.content.strip()
            # Strip the [Doc: ... | Page ... | Type: ...] prefix before hashing
            clean = re.sub(r"^\[Doc:.*?\]\s*", "", content)
            content_hash = hashlib.md5(clean.encode("utf-8")).hexdigest()

            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(chunk)

        return unique

    # ── Step 3: Garbled text detection ────────────────────────────────────

    @staticmethod
    def _filter_garbled(
        chunks: List[KnowledgeChunk],
    ) -> tuple:
        """Removes chunks with encoding issues or garbled text.

        Returns (filtered_chunks, count_removed).
        """
        filtered: List[KnowledgeChunk] = []
        removed = 0

        for chunk in chunks:
            text = chunk.content
            # Check for high ratio of non-ASCII / replacement characters
            bad_chars = sum(
                1 for c in text
                if ord(c) > 0xFFFF or c in "\ufffd\ufffe\uffff"
            )
            if len(text) > 0 and (bad_chars / len(text)) > 0.1:
                removed += 1
                continue

            # Check for very low word density (likely garbled binary)
            words = re.findall(r"[a-zA-Z]{2,}", text)
            word_chars = sum(len(w) for w in words)
            if len(text) > 50 and word_chars / len(text) < 0.15:
                removed += 1
                continue

            filtered.append(chunk)

        return filtered, removed

    # ── Step 4: Intelligence computation ──────────────────────────────────

    @staticmethod
    def _compute_intelligence(
        document: PipelineDocument,
        chunks: List[KnowledgeChunk],
        errors: List[str],
    ) -> DocumentIntelligence:
        """Aggregates analytics from validated chunks."""
        # Count chunks by knowledge box type
        type_counter = Counter(c.knowledge_box.value for c in chunks)

        # Pages that have at least one chunk
        indexed_pages = set(c.page for c in chunks)
        total_pages = max(document.page_count, 1)
        coverage = len(indexed_pages) / total_pages

        # Average confidence
        avg_conf = (
            sum(c.confidence for c in chunks) / len(chunks)
            if chunks else 0.0
        )

        # Top concepts (most frequent across chunks)
        concept_counter: Counter = Counter()
        for chunk in chunks:
            for concept in chunk.named_concepts:
                concept_counter[concept] += 1
        top_concepts = [c for c, _ in concept_counter.most_common(15)]

        return DocumentIntelligence(
            total_pages=total_pages,
            indexed_pages=len(indexed_pages),
            coverage_pct=round(coverage * 100, 1),
            chunk_counts=dict(type_counter),
            total_chunks=len(chunks),
            detected_subject=document.subject,
            extraction_errors=errors,
            avg_confidence=round(avg_conf, 3),
            top_concepts=top_concepts,
        )

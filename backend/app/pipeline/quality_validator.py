import logging
from typing import List, Dict, Any, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)


class QualityValidator:
    """
    Validation Stage: Quality Validation.
    Enforces chunk size limits, eliminates low-quality fragments,
    verifies graph reference integrity, and validates confidence scores.
    """

    @classmethod
    def validate_chunks(
        cls, chunks: List[Dict[str, Any]], relationships: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        valid_chunks: List[Dict[str, Any]] = []
        dropped_count = 0
        total_tokens = 0

        chunk_ids = set()

        for chunk in chunks:
            content = chunk.get("content", "").strip()
            # Estimate token count
            tokens = len(content) // 4

            # Drop meaningless tiny chunks unless they are section headers or formulas
            if tokens < 10 and chunk.get("chunk_type") not in ["section_header", "formula"]:
                dropped_count += 1
                continue

            # Cap confidence between 0.0 and 1.0
            conf = chunk.get("confidence", 1.0)
            chunk["confidence"] = max(0.0, min(1.0, float(conf)))

            chunk_ids.add(chunk["id"])
            total_tokens += tokens
            valid_chunks.append(chunk)

        # Validate graph edges: eliminate edges referring to non-existent or dropped chunks
        valid_relationships = []
        for rel in relationships:
            src = rel.get("source_chunk_id")
            tgt = rel.get("target_chunk_id")
            if src in chunk_ids and tgt in chunk_ids and src != tgt:
                valid_relationships.append(rel)

        metrics = {
            "input_chunk_count": len(chunks),
            "valid_chunk_count": len(valid_chunks),
            "dropped_chunks": dropped_count,
            "total_tokens_estimated": total_tokens,
            "valid_relationships_count": len(valid_relationships),
            "validation_passed": len(valid_chunks) > 0,
        }

        return valid_chunks, valid_relationships, metrics

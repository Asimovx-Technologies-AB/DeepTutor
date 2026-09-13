import re
from typing import List, Dict, Any, Tuple, Set


class SemanticKnowledgeExtractor:
    """
    Convergence Stage: Semantic Knowledge Extractor.
    Extracts key topics, concepts, entities, definitions, examples,
    and semantic relationships from normalized text and structural blocks.
    """

    DEFINITION_PATTERNS = [
        re.compile(r"\b([A-Z][a-zA-Z\s]{2,30})\s+(?:is defined as|refers to|denotes|is termed as|is characterized by)\b", re.IGNORECASE),
        re.compile(r"\bDefinition(?:\s*\d+)?:\s*([^.\n]+)", re.IGNORECASE),
    ]

    EXAMPLE_PATTERNS = [
        re.compile(r"(?:for example|for instance|e\.g\.|consider the following example)[,:\s]+([^.\n]+(?:\.[^.\n]+)?)", re.IGNORECASE),
        re.compile(r"\bExample(?:\s*\d+)?:\s*([^.\n]+)", re.IGNORECASE),
    ]

    STOPWORDS = {
        "the", "and", "is", "in", "to", "of", "a", "an", "that", "this", "it", "for", "with",
        "as", "by", "on", "are", "be", "was", "were", "from", "at", "which", "or", "have", "has"
    }

    @classmethod
    def extract_semantics(cls, text: str, chapter_section: str | None = None) -> Dict[str, Any]:
        """
        Extracts semantic properties from a chunk of text.
        """
        if not text:
            return {
                "topic": chapter_section or "General",
                "related_concepts": [],
                "keywords_entities": [],
                "definitions": [],
                "examples": [],
                "inferred_type": "text",
            }

        # 1. Extract definitions
        definitions: List[str] = []
        for pat in cls.DEFINITION_PATTERNS:
            for match in pat.finditer(text):
                definitions.append(match.group(0).strip())

        # 2. Extract examples
        examples: List[str] = []
        for pat in cls.EXAMPLE_PATTERNS:
            for match in pat.finditer(text):
                examples.append(match.group(0).strip())

        # 3. Extract keywords and entities (capitalized phrases and key noun terms)
        capitalized = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        entities = set()
        for term in capitalized:
            term_clean = term.strip()
            if term_clean.lower() not in cls.STOPWORDS and len(term_clean) > 2:
                entities.add(term_clean)

        # 4. Extract mathematical or technical concepts
        tech_terms = re.findall(r"\b(?:algorithm|theorem|equation|matrix|vector|derivative|integral|model|distribution|function)\b", text, re.IGNORECASE)
        for term in tech_terms:
            entities.add(term.lower())

        # Infer specialized chunk type
        inferred_type = "text"
        if definitions:
            inferred_type = "definition"
        elif examples:
            inferred_type = "example"
        elif "$$" in text or r"\begin{equation}" in text:
            inferred_type = "formula"
        elif text.strip().startswith("|") and text.strip().endswith("|"):
            inferred_type = "table"

        # Topic fallback
        topic = chapter_section.split(">")[-1].strip() if chapter_section else "General"

        return {
            "topic": topic,
            "related_concepts": list(entities)[:10],
            "keywords_entities": list(entities)[:15],
            "definitions": definitions,
            "examples": examples,
            "inferred_type": inferred_type,
        }

    @classmethod
    def infer_relationships(
        cls, chunk_a_id: str, chunk_a_meta: Dict[str, Any],
        chunk_b_id: str, chunk_b_meta: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Detects semantic relationships between two knowledge chunks.
        e.g., 'defines', 'prerequisite_of', 'elaborates', 'contrasts_with'.
        """
        rels = []
        concepts_a = set(chunk_a_meta.get("related_concepts", []))
        concepts_b = set(chunk_b_meta.get("related_concepts", []))
        overlap = concepts_a.intersection(concepts_b)

        if not overlap:
            return rels

        # Chunk A is definition and Chunk B uses or elaborates on the concept
        if chunk_a_meta.get("chunk_type") == "definition" and chunk_b_meta.get("chunk_type") in ["example", "text", "formula"]:
            rels.append({
                "source_chunk_id": chunk_a_id,
                "target_chunk_id": chunk_b_id,
                "relation_type": "defines",
                "weight": 0.9,
                "edge_metadata": {"shared_concepts": list(overlap)}
            })

        # Concept overlap across sequential or related sections
        if len(overlap) >= 2:
            rels.append({
                "source_chunk_id": chunk_a_id,
                "target_chunk_id": chunk_b_id,
                "relation_type": "elaborates",
                "weight": min(len(overlap) * 0.3, 1.0),
                "edge_metadata": {"shared_concepts": list(overlap)}
            })

        return rels

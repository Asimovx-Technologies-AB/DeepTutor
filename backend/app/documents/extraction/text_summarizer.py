"""
Text Summarizer — Section heading detection, concept extraction, and
knowledge-box template classification.

The 'Contextual NLP Models' stage in the pipeline diagram.  Operates on
extracted page text to produce structural metadata consumed by the
Knowledge Tiler.
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional

from app.documents.models import KnowledgeBoxType

logger = logging.getLogger(__name__)

# ─── Heading detection patterns ──────────────────────────────────────────────

# Matches lines that look like section headings:
#   "Chapter 3: Photosynthesis"
#   "3.2  Cell Division"
#   "INTRODUCTION"
#   "## Markdown heading"
_HEADING_PATTERNS = [
    # Markdown headings
    re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE),
    # "Chapter N" or "CHAPTER N"
    re.compile(
        r"^(?:chapter|CHAPTER)\s+(\d+(?:\.\d+)?)\s*[:\.\-–—]?\s*(.+)$",
        re.MULTILINE,
    ),
    # Numbered sections like "3.2  Cell Division" or "3.2.1 Methods"
    re.compile(
        r"^(\d+(?:\.\d+){0,3})\s{2,}([A-Z][A-Za-z\s,\-&:]+)$",
        re.MULTILINE,
    ),
    # ALL-CAPS lines (≥3 words, likely section titles)
    re.compile(r"^([A-Z][A-Z\s\-&:]{8,})$", re.MULTILINE),
]

# ─── Knowledge box detection patterns ────────────────────────────────────────

_BOX_PATTERNS: Dict[KnowledgeBoxType, List[re.Pattern]] = {
    KnowledgeBoxType.DEFINITION: [
        re.compile(r"(?:^|\n)\s*(?:Definition|DEFINITION)\s*[\d.]*\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"\bis\s+defined\s+as\b", re.IGNORECASE),
        re.compile(r"\bwe\s+define\b", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*Def\s*\d", re.IGNORECASE),
    ],
    KnowledgeBoxType.THEOREM: [
        re.compile(r"(?:^|\n)\s*(?:Theorem|THEOREM|Lemma|LEMMA|Corollary|COROLLARY|Proposition)\s*[\d.]*\s*[:\.\-–—(]", re.IGNORECASE),
    ],
    KnowledgeBoxType.PROOF: [
        re.compile(r"(?:^|\n)\s*(?:Proof|PROOF)\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"\bQ\.E\.D\b|□|∎|▪", re.IGNORECASE),
    ],
    KnowledgeBoxType.EXAMPLE: [
        re.compile(r"(?:^|\n)\s*(?:Example|EXAMPLE|Worked\s+Example|Illustration)\s*[\d.]*\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*(?:e\.g\.|for\s+example|for\s+instance)\s*[,:]", re.IGNORECASE),
    ],
    KnowledgeBoxType.EXERCISE: [
        re.compile(r"(?:^|\n)\s*(?:Exercise|EXERCISE|Problem|PROBLEM)\s*[\d.]*\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*(?:Practice\s+(?:Problem|Question)s?)\s*[\d.]*\s*[:\.\-–—]", re.IGNORECASE),
    ],
    KnowledgeBoxType.QUESTION: [
        re.compile(r"(?:^|\n)\s*(?:Question|Q)\s*[\d.]+\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*\d+\)\s+.+\?$", re.MULTILINE),
    ],
    KnowledgeBoxType.PROCEDURE: [
        re.compile(r"(?:^|\n)\s*(?:Algorithm|ALGORITHM|Procedure|PROCEDURE|Steps?)\s*[\d.]*\s*[:\.\-–—]", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*Step\s+\d+\s*[:\.\-–—]", re.IGNORECASE),
    ],
    KnowledgeBoxType.NOTE: [
        re.compile(r"(?:^|\n)\s*(?:Note|NOTE|Remark|REMARK|NB|N\.B\.)\s*[:\.\-–—]", re.IGNORECASE),
    ],
    KnowledgeBoxType.WARNING: [
        re.compile(r"(?:^|\n)\s*(?:Warning|WARNING|Caution|CAUTION|Important|IMPORTANT)\s*[:\.\-–—]", re.IGNORECASE),
    ],
    KnowledgeBoxType.FORMULA: [
        # Standalone display equations
        re.compile(r"^\s*\$\$[^$]+\$\$\s*$", re.MULTILINE),
        re.compile(r"\\begin\{(?:equation|align|gather|displaymath)\}", re.IGNORECASE),
    ],
    KnowledgeBoxType.EXPLANATION: [
        re.compile(r"(?:^|\n)\s*(?:Explanation|EXPLANATION|Discussion|Analysis)\s*[:\.\-–—]", re.IGNORECASE),
    ],
    KnowledgeBoxType.CONCEPT: [
        re.compile(r"(?:^|\n)\s*(?:Key\s+Concept|Concept|Fundamental|Principle)\s*[:\.\-–—]", re.IGNORECASE),
    ],
}

# ─── Named concept extraction patterns ───────────────────────────────────────

_CONCEPT_PATTERNS = [
    # Bold text (Markdown): **term** or __term__
    re.compile(r"\*\*([A-Za-z][A-Za-z\s\-]{2,40})\*\*"),
    re.compile(r"__([A-Za-z][A-Za-z\s\-]{2,40})__"),
    # Definitions: "X is defined as", "X refers to"
    re.compile(r"(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\s+(?:is\s+defined\s+as|refers\s+to|is\s+called)", re.MULTILINE),
    # LaTeX-wrapped terms: $X$
    re.compile(r"\$([A-Za-z_][A-Za-z0-9_\s]{0,20})\$"),
    # Capitalized multi-word noun phrases (2-4 words)
    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"),
]


class TextSummarizer:
    """Extracts structural metadata from page text for the Knowledge Tiler."""

    # ── Heading detection ─────────────────────────────────────────────────

    @staticmethod
    def detect_headings(text: str) -> List[Dict[str, Any]]:
        """Detects section headings in the text.

        Returns:
            [{level: int, title: str, start_pos: int, end_pos: int}]
        """
        headings: List[Dict[str, Any]] = []

        for pattern in _HEADING_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) >= 2:
                    level_indicator, title = groups[0], groups[1]
                    # Determine heading level
                    if level_indicator.startswith("#"):
                        level = len(level_indicator)
                    elif re.match(r"\d+(\.\d+)*", level_indicator):
                        level = level_indicator.count(".") + 1
                    else:
                        level = 1
                    title = title.strip().rstrip(":")
                elif len(groups) == 1:
                    level = 1
                    title = groups[0].strip()
                else:
                    continue

                if len(title) < 3 or len(title) > 120:
                    continue

                headings.append({
                    "level": min(level, 6),
                    "title": title,
                    "start_pos": match.start(),
                    "end_pos": match.end(),
                })

        # Deduplicate and sort by position
        seen = set()
        unique: List[Dict[str, Any]] = []
        for h in sorted(headings, key=lambda x: x["start_pos"]):
            key = (h["title"].lower(), h["start_pos"])
            if key not in seen:
                seen.add(key)
                unique.append(h)

        return unique

    # ── Section tree ──────────────────────────────────────────────────────

    @staticmethod
    def build_section_path(
        headings: List[Dict[str, Any]],
        char_position: int,
    ) -> str:
        """Returns the section path for a given character position.

        Example: "Ch 3 > 3.2 Photosynthesis > Light Reactions"
        """
        # Find the heading stack at this position
        active: List[str] = []
        active_levels: List[int] = []

        for h in headings:
            if h["start_pos"] > char_position:
                break
            level = h["level"]
            # Pop deeper or same-level headings
            while active_levels and active_levels[-1] >= level:
                active.pop()
                active_levels.pop()
            active.append(h["title"])
            active_levels.append(level)

        return " > ".join(active) if active else ""

    # ── Knowledge box classification ──────────────────────────────────────

    @staticmethod
    def classify_knowledge_box(text: str) -> KnowledgeBoxType:
        """Classifies a chunk of text into one of the 17 knowledge box types.

        Uses pattern matching against the text content.  Checks more
        specific types first (theorem, proof, definition) before falling
        back to general types (paragraph, explanation).
        """
        if not text or len(text.strip()) < 5:
            return KnowledgeBoxType.PARAGRAPH

        # Check heading first (very short, likely a title line)
        lines = text.strip().splitlines()
        if len(lines) <= 2 and len(text.strip()) < 100:
            for pattern in _HEADING_PATTERNS:
                if pattern.search(text):
                    return KnowledgeBoxType.HEADING

        # Check specific knowledge box patterns in priority order
        priority_order = [
            KnowledgeBoxType.THEOREM,
            KnowledgeBoxType.PROOF,
            KnowledgeBoxType.DEFINITION,
            KnowledgeBoxType.FORMULA,
            KnowledgeBoxType.EXAMPLE,
            KnowledgeBoxType.EXERCISE,
            KnowledgeBoxType.QUESTION,
            KnowledgeBoxType.PROCEDURE,
            KnowledgeBoxType.WARNING,
            KnowledgeBoxType.NOTE,
            KnowledgeBoxType.CONCEPT,
            KnowledgeBoxType.EXPLANATION,
        ]

        for box_type in priority_order:
            patterns = _BOX_PATTERNS.get(box_type, [])
            for pattern in patterns:
                if pattern.search(text):
                    return box_type

        # Fallback: if text is mostly about explaining something
        if len(text) > 200:
            return KnowledgeBoxType.EXPLANATION

        return KnowledgeBoxType.PARAGRAPH

    # ── Named concept extraction ──────────────────────────────────────────

    @staticmethod
    def extract_concepts_heuristic(text: str) -> List[str]:
        """Regex/NLP extraction of named concepts from text.

        Extracts: bold terms, defined terms, capitalized noun phrases,
        LaTeX-wrapped variables.

        Returns deduplicated list of concept strings.
        """
        if not text or len(text) < 20:
            return []

        concepts: set = set()

        for pattern in _CONCEPT_PATTERNS:
            for match in pattern.finditer(text):
                term = match.group(1).strip()
                # Filter noise
                if (
                    len(term) >= 3
                    and len(term) <= 50
                    and not term.isupper()  # Skip ALL_CAPS noise
                    and term.lower() not in {
                        "the", "and", "for", "that", "this", "with",
                        "from", "are", "was", "were", "has", "have",
                        "been", "not", "but", "all", "can", "will",
                    }
                ):
                    concepts.add(term)

        return sorted(concepts)[:20]  # Cap at 20 concepts per chunk

    async def extract_concepts_llm(self, text: str) -> List[str]:
        """LLM fallback for concept extraction on low-confidence chunks.

        Uses the existing llm_client to extract key academic terms.
        """
        if not text or len(text) < 50:
            return []

        try:
            from app.rag.llm_client import llm_client

            prompt = (
                "Extract the key academic concepts, terms, and named entities "
                "from this text. Return ONLY a JSON array of strings, no other text.\n\n"
                f"Text:\n{text[:4000]}"
            )
            raw = await llm_client.generate(prompt)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```\w*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)

            import json
            concepts = json.loads(cleaned)
            if isinstance(concepts, list):
                return [str(c).strip() for c in concepts if c and len(str(c)) <= 50][:20]
        except Exception as exc:
            logger.debug("[TextSummarizer] LLM concept extraction error: %s", exc)

        return []

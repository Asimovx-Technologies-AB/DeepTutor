"""
Stage 1 — Document Parsing & Preprocessing Pipeline.

Exports:
    DocumentParser   — multi-engine cascade parser
    SemanticChunker  — 500-1000 word semantic chunker
    SectionNode      — section tree node dataclass
    build_section_tree — build heading hierarchy from raw text
"""
from .parser import DocumentParser, document_parser
from .section_tree import SectionNode, build_section_tree
from .chunker import SemanticChunker, semantic_chunker

__all__ = [
    "DocumentParser", "document_parser",
    "SectionNode", "build_section_tree",
    "SemanticChunker", "semantic_chunker",
]

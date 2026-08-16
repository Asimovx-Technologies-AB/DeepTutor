"""
Stage 1 — Section Tree Builder
================================
Builds a hierarchical section tree from page text extracted by DocumentParser.

SectionNode holds:
  - title      : heading text
  - level      : heading depth (1=H1, 2=H2, ...)
  - page       : page number where heading appears
  - path       : full ancestor path, e.g. ["Introduction", "Background", "Related Work"]
  - children   : nested sub-sections
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SectionNode:
    title: str
    level: int
    page: int
    path: List[str] = field(default_factory=list)
    children: List["SectionNode"] = field(default_factory=list)

    @property
    def full_path(self) -> str:
        """Human-readable breadcrumb, e.g. 'Methods > Data Collection'."""
        return " > ".join(self.path + [self.title]) if self.path else self.title

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "page": self.page,
            "path": self.path,
            "full_path": self.full_path,
            "children": [c.to_dict() for c in self.children],
        }


from app.rag.topic_sanitizer import is_valid_academic_topic, clean_and_format_topic

_HEADING_PATTERNS = [
    # Markdown headings  # H1 / ## H2 / ...
    re.compile(r'^(#{1,6})\s+(.+)$'),
    # Numbered sections  1. / 1.2 / 1.2.3
    re.compile(r'^(\d+(?:\.\d+)*)[.\)]\s+([A-Z].{2,80})$'),
]


def _detect_heading(line: str) -> Optional[tuple[int, str]]:
    """Return (level, title) if line looks like a valid academic heading, else None."""
    line = line.strip()
    if not line or len(line) > 120:
        return None

    # Markdown #-headings
    m = _HEADING_PATTERNS[0].match(line)
    if m:
        raw_title = m.group(2).strip()
        clean_title = clean_and_format_topic(raw_title)
        if clean_title:
            return len(m.group(1)), clean_title

    # Numbered sections
    m = _HEADING_PATTERNS[1].match(line)
    if m:
        raw_title = m.group(2).strip()
        clean_title = clean_and_format_topic(raw_title)
        if clean_title:
            level = m.group(1).count(".") + 1
            return min(level, 6), clean_title

    # ALL CAPS (2–8 words, max 70 chars, must be valid lexical heading, not table/code data)
    if line.isupper() and 2 <= len(line.split()) <= 8 and len(line) <= 70:
        clean_title = clean_and_format_topic(line)
        if clean_title:
            return 1, clean_title

    return None


def build_section_tree(pages: List[dict]) -> List[SectionNode]:
    """
    Build a flat list of SectionNodes from page dicts
    (output of DocumentParser.parse()).

    Each node knows its level, page, and ancestor path.
    """
    nodes: List[SectionNode] = []
    # Stack stores (level, SectionNode) for building ancestor path
    stack: List[tuple[int, SectionNode]] = []

    for page_data in pages:
        page_num = page_data.get("page", 1)
        text = page_data.get("text", "")

        for line in text.split("\n"):
            result = _detect_heading(line)
            if not result:
                continue
            level, title = result

            # Pop stack to find the correct parent level
            while stack and stack[-1][0] >= level:
                stack.pop()

            path = [s.title for _, s in stack]
            node = SectionNode(title=title, level=level, page=page_num, path=path)

            # Attach as child of parent (last item on stack)
            if stack:
                stack[-1][1].children.append(node)
            nodes.append(node)
            stack.append((level, node))

    return nodes


def section_tree_to_lookup(nodes: List[SectionNode]) -> dict:
    """
    Flatten a section tree into a lookup dict:
        {page_number: [SectionNode, ...]}
    For fast per-page section annotation during chunking.
    """
    lookup: dict = {}
    for node in nodes:
        lookup.setdefault(node.page, []).append(node)
    return lookup

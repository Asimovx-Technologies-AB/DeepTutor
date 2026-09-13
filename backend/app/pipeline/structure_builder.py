import re
import uuid
from typing import List, Dict, Any, Optional
from app.schemas.layout import LayoutBlock
from app.schemas.document import StructuralNode


class DocumentStructureBuilder:
    """
    Convergence Stage: Document Structure Builder.
    Reconstructs document hierarchy (Chapter -> Section -> Subsection -> Content)
    from font styles, numbering patterns (e.g., '1.2', 'Chapter 3'), and reading order.
    """

    HEADING_REGEX = re.compile(
        r"^(?:(?:chapter|unit|module|part)\s+\d+|(?:\d+\.)+\d*|\b[A-Z0-9\s]{4,}\b)",
        re.IGNORECASE
    )

    @classmethod
    def build_structure(cls, pages_blocks: List[Dict[str, Any]]) -> List[StructuralNode]:
        """
        Builds a hierarchical tree of StructuralNodes from all pages.
        """
        root_nodes: List[StructuralNode] = []
        current_chapter: Optional[StructuralNode] = None
        current_section: Optional[StructuralNode] = None

        for page in pages_blocks:
            page_num = page.get("page_number", 1)
            blocks: List[LayoutBlock] = page.get("blocks", [])

            for block in blocks:
                text = block.text.strip()
                if not text:
                    continue

                is_heading = block.block_type == "heading" or cls._is_numbered_heading(text)

                if is_heading:
                    level, clean_title = cls._determine_heading_level(text)

                    node = StructuralNode(
                        id=str(uuid.uuid4()),
                        title=clean_title,
                        level=level,
                        path=clean_title,
                        page_start=page_num,
                        page_end=page_num,
                        chunk_ids=[],
                        children=[],
                    )

                    if level == 1:
                        # Top-level Chapter
                        node.path = clean_title
                        root_nodes.append(node)
                        current_chapter = node
                        current_section = None
                    elif level == 2:
                        # Section under chapter
                        if current_chapter:
                            node.path = f"{current_chapter.path} > {clean_title}"
                            current_chapter.children.append(node)
                        else:
                            root_nodes.append(node)
                        current_section = node
                    else:
                        # Subsection
                        if current_section:
                            node.path = f"{current_section.path} > {clean_title}"
                            current_section.children.append(node)
                        elif current_chapter:
                            node.path = f"{current_chapter.path} > {clean_title}"
                            current_chapter.children.append(node)
                        else:
                            root_nodes.append(node)

        # If document had no explicit headings, create a default top-level structure
        if not root_nodes:
            default_node = StructuralNode(
                id=str(uuid.uuid4()),
                title="Document Overview",
                level=1,
                path="Document Overview",
                page_start=1,
                page_end=len(pages_blocks) if pages_blocks else 1,
                chunk_ids=[],
                children=[],
            )
            root_nodes.append(default_node)

        return root_nodes

    @classmethod
    def _is_numbered_heading(cls, text: str) -> bool:
        first_line = text.split("\n")[0].strip()
        if len(first_line) > 100:
            return False
        return bool(cls.HEADING_REGEX.match(first_line))

    @classmethod
    def _determine_heading_level(cls, text: str) -> (int, str):
        first_line = text.split("\n")[0].strip()
        lower = first_line.lower()

        if "chapter" in lower or "module" in lower or "part" in lower or "unit" in lower:
            return 1, first_line

        # Count dotted numbers: "1." -> 1, "1.2" -> 2, "1.2.3" -> 3
        match = re.match(r"^(\d+(?:\.\d+)*)", first_line)
        if match:
            num_dots = match.group(1).count(".")
            level = min(num_dots + 1, 3)
            return level, first_line

        if first_line.isupper() and len(first_line) > 3:
            return 1, first_line

        return 2, first_line

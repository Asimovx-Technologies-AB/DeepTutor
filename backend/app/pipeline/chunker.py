import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.schemas.chunk import KnowledgeChunkBase, KnowledgeChunkCreate
from app.schemas.layout import LayoutBlock, TableAsset, FormulaAsset
from app.schemas.document import StructuralNode
from app.pipeline.semantic_extractor import SemanticKnowledgeExtractor


class KnowledgeChunker:
    """
    Knowledge Chunks Generator.
    Produces rich knowledge units embodying all 14 specified dimensions:
    1. Content
    2. Type
    3. Topic
    4. Chapter / Section
    5. Prev / Next Chunk
    6. Parent / Child
    7. Related Concepts
    8. Keywords / Entities
    9. Formulas
    10. Examples
    11. Source URI
    12. Confidence
    13. Provenance
    14. Knowledge Relationship Metadata
    """

    @classmethod
    def generate_chunks(
        cls,
        doc_id: str,
        pages_data: List[Dict[str, Any]],
        structure_tree: List[StructuralNode],
        tables: List[TableAsset],
        formulas: List[FormulaAsset],
    ) -> List[Dict[str, Any]]:
        raw_chunks: List[Dict[str, Any]] = []
        chunk_counter = 0

        # Create quick lookup for formulas by page
        formulas_by_page: Dict[int, List[str]] = {}
        for f in formulas:
            formulas_by_page.setdefault(f.page_number, []).append(f.latex)

        # 1. Process regular text & layout blocks page by page
        for page in pages_data:
            page_num = page.get("page_number", 1)
            blocks: List[LayoutBlock] = page.get("blocks", [])

            # Match page with active chapter/section from structure tree
            chapter_section = cls._find_chapter_section_for_page(structure_tree, page_num)

            # Group blocks into coherent semantic chunks (approx settings.MAX_CHUNK_TOKENS tokens)
            current_chunk_text_parts: List[str] = []
            current_bbox: Optional[List[float]] = None
            current_chunk_type = "text"

            for block in blocks:
                text = block.text.strip()
                if not text:
                    continue

                # If this block is a heading or formula, treat it appropriately
                if block.block_type == "heading":
                    # Flush existing chunk before starting a new heading
                    if current_chunk_text_parts:
                        chunk_dict = cls._build_chunk_record(
                            doc_id=doc_id,
                            chunk_index=chunk_counter,
                            page_num=page_num,
                            content="\n\n".join(current_chunk_text_parts),
                            chunk_type=current_chunk_type,
                            chapter_section=chapter_section,
                            bbox=current_bbox,
                            formulas=formulas_by_page.get(page_num, []),
                            provenance_source="pymupdf_normalized",
                        )
                        raw_chunks.append(chunk_dict)
                        chunk_counter += 1
                        current_chunk_text_parts = []
                        current_bbox = None

                    current_chunk_type = "section_header"
                    chapter_section = text

                # Combine text
                current_chunk_text_parts.append(text)
                current_bbox = cls._merge_bboxes(current_bbox, block.bbox)

                # Estimate tokens (approx 4 chars per token)
                accumulated_text = "\n\n".join(current_chunk_text_parts)
                estimated_tokens = len(accumulated_text) // 4

                if estimated_tokens >= settings.MAX_CHUNK_TOKENS:
                    chunk_dict = cls._build_chunk_record(
                        doc_id=doc_id,
                        chunk_index=chunk_counter,
                        page_num=page_num,
                        content=accumulated_text,
                        chunk_type=current_chunk_type,
                        chapter_section=chapter_section,
                        bbox=current_bbox,
                        formulas=formulas_by_page.get(page_num, []),
                        provenance_source="pymupdf_normalized",
                    )
                    raw_chunks.append(chunk_dict)
                    chunk_counter += 1
                    current_chunk_text_parts = []
                    current_bbox = None
                    current_chunk_type = "text"

            # Flush any remaining text on the page
            if current_chunk_text_parts:
                accumulated_text = "\n\n".join(current_chunk_text_parts)
                chunk_dict = cls._build_chunk_record(
                    doc_id=doc_id,
                    chunk_index=chunk_counter,
                    page_num=page_num,
                    content=accumulated_text,
                    chunk_type=current_chunk_type,
                    chapter_section=chapter_section,
                    bbox=current_bbox,
                    formulas=formulas_by_page.get(page_num, []),
                    provenance_source="pymupdf_normalized",
                )
                raw_chunks.append(chunk_dict)
                chunk_counter += 1

        # 2. Add Tables as distinct First-Class Knowledge Chunks
        for table in tables:
            table_chunk = cls._build_chunk_record(
                doc_id=doc_id,
                chunk_index=chunk_counter,
                page_num=table.page_number,
                content=f"### Table (Page {table.page_number})\n\n{table.markdown}",
                chunk_type="table",
                chapter_section=cls._find_chapter_section_for_page(structure_tree, table.page_number),
                bbox=table.bbox,
                formulas=[],
                provenance_source="table_detector",
            )
            raw_chunks.append(table_chunk)
            chunk_counter += 1

        # 3. Establish Sequential Lineage (Prev / Next chunk pointers)
        for i in range(len(raw_chunks)):
            if i > 0:
                raw_chunks[i]["prev_chunk_id"] = raw_chunks[i - 1]["id"]
            if i < len(raw_chunks) - 1:
                raw_chunks[i]["next_chunk_id"] = raw_chunks[i + 1]["id"]

        # 4. Connect Chunks to Structure Tree (Parent / Child)
        cls._link_parent_child_hierarchy(structure_tree, raw_chunks)

        return raw_chunks

    @classmethod
    def _build_chunk_record(
        cls,
        doc_id: str,
        chunk_index: int,
        page_num: int,
        content: str,
        chunk_type: str,
        chapter_section: Optional[str],
        bbox: Optional[List[float]],
        formulas: List[str],
        provenance_source: str,
    ) -> Dict[str, Any]:
        chunk_id = str(uuid.uuid4())
        
        # Semantic extraction
        semantics = SemanticKnowledgeExtractor.extract_semantics(content, chapter_section)
        final_type = chunk_type if chunk_type in ["section_header", "table", "formula"] else semantics["inferred_type"]

        # Source URI string representation
        bbox_str = f"[{','.join(str(round(c, 1)) for c in bbox)}]" if bbox else "none"
        source_uri = f"doc://{doc_id}/page/{page_num}?bbox={bbox_str}"

        # Combine text for search indexing
        search_terms = [content]
        if semantics["keywords_entities"]:
            search_terms.append(" ".join(semantics["keywords_entities"]))
        if chapter_section:
            search_terms.append(chapter_section)
        search_text = "\n".join(search_terms)

        return {
            "id": chunk_id,
            "document_id": doc_id,
            "page_number": page_num,
            "chunk_index": chunk_index,
            # 14 Dimensions
            "content": content,
            "chunk_type": final_type,
            "topic": semantics["topic"],
            "chapter_section": chapter_section,
            "prev_chunk_id": None, # Filled later
            "next_chunk_id": None, # Filled later
            "parent_id": None, # Linked later
            "child_ids": [],
            "related_concepts": semantics["related_concepts"],
            "keywords_entities": semantics["keywords_entities"],
            "formulas": formulas[:5], # Relevant formulas on this page/chunk
            "examples": semantics["examples"],
            "source_uri": source_uri,
            "bbox_coordinates": bbox,
            "confidence": 0.95,
            "provenance": {
                "parser": "PyMuPDF",
                "source": provenance_source,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "relationship_metadata": {
                "entity_count": len(semantics["keywords_entities"]),
                "definition_count": len(semantics["definitions"]),
                "example_count": len(semantics["examples"]),
            },
            "search_text": search_text,
            "embedding": None, # Populated by EmbeddingService
        }

    @classmethod
    def _find_chapter_section_for_page(cls, nodes: List[StructuralNode], page_num: int) -> str:
        for node in nodes:
            if node.page_start <= page_num <= node.page_end:
                if node.children:
                    for child in node.children:
                        if child.page_start <= page_num <= child.page_end:
                            return child.path
                return node.path
        return "Document Overview"

    @classmethod
    def _link_parent_child_hierarchy(cls, nodes: List[StructuralNode], chunks: List[Dict[str, Any]]):
        for node in nodes:
            node_chunks = [c for c in chunks if c["page_number"] >= node.page_start and c["page_number"] <= node.page_end]
            for c in node_chunks:
                if not c["parent_id"]:
                    c["parent_id"] = node.id
            node.chunk_ids = [c["id"] for c in node_chunks]

            if node.children:
                cls._link_parent_child_hierarchy(node.children, chunks)

    @staticmethod
    def _merge_bboxes(b1: Optional[List[float]], b2: Optional[List[float]]) -> Optional[List[float]]:
        if not b1:
            return b2
        if not b2:
            return b1
        return [
            min(b1[0], b2[0]),
            min(b1[1], b2[1]),
            max(b1[2], b2[2]),
            max(b1[3], b2[3]),
        ]

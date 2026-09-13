from typing import List, Dict, Any
from app.schemas.document import (
    CanonicalDocumentRepresentation,
    DocumentMetadataRead,
    PageLayoutInfo,
    StructuralNode,
    RelationshipEdge
)
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset


class CanonicalDocumentBuilder:
    """
    Synthesizes the Canonical Document Representation:
    The unified standardized data model of the parsed and structured document.
    """

    @classmethod
    def assemble_canonical(
        cls,
        doc_metadata: Dict[str, Any],
        pages_data: List[Dict[str, Any]],
        structure_tree: List[StructuralNode],
        chunks: List[Dict[str, Any]],
        tables: List[TableAsset],
        formulas: List[FormulaAsset],
        relationships: List[Dict[str, Any]],
    ) -> CanonicalDocumentRepresentation:
        # Build PageLayoutInfo
        page_infos = []
        for p in pages_data:
            page_infos.append(
                PageLayoutInfo(
                    page_number=p.get("page_number", 1),
                    width=p.get("width", 612.0),
                    height=p.get("height", 792.0),
                    dpi=p.get("dpi", 150),
                    classification=p.get("classification", "digital"),
                    character_density=p.get("character_density", 0.0),
                    blocks=p.get("blocks", []),
                )
            )

        # Build KnowledgeChunkRead
        chunk_reads = []
        for c in chunks:
            chunk_reads.append(
                KnowledgeChunkRead(
                    id=c["id"],
                    document_id=c["document_id"],
                    page_number=c["page_number"],
                    chunk_index=c["chunk_index"],
                    content=c["content"],
                    chunk_type=c.get("chunk_type", "text"),
                    topic=c.get("topic"),
                    chapter_section=c.get("chapter_section"),
                    prev_chunk_id=c.get("prev_chunk_id"),
                    next_chunk_id=c.get("next_chunk_id"),
                    parent_id=c.get("parent_id"),
                    child_ids=c.get("child_ids", []),
                    related_concepts=c.get("related_concepts", []),
                    keywords_entities=c.get("keywords_entities", []),
                    formulas=c.get("formulas", []),
                    examples=c.get("examples", []),
                    source_uri=c.get("source_uri"),
                    bbox_coordinates=c.get("bbox_coordinates"),
                    confidence=c.get("confidence", 1.0),
                    provenance=c.get("provenance", {}),
                    relationship_metadata=c.get("relationship_metadata", {}),
                    search_text=c.get("search_text"),
                    has_embedding=bool(c.get("embedding")),
                )
            )

        # Build RelationshipEdge
        rel_edges = []
        for r in relationships:
            rel_edges.append(
                RelationshipEdge(
                    source_chunk_id=r["source_chunk_id"],
                    target_chunk_id=r["target_chunk_id"],
                    relation_type=r["relation_type"],
                    weight=r.get("weight", 1.0),
                    edge_metadata=r.get("edge_metadata", {}),
                )
            )

        return CanonicalDocumentRepresentation(
            metadata=DocumentMetadataRead(**doc_metadata),
            pages=page_infos,
            structure_tree=structure_tree,
            knowledge_chunks=chunk_reads,
            tables=tables,
            formulas=formulas,
            relationships=rel_edges,
        )

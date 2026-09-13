import io
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF
from PIL import Image
from app.schemas.layout import LayoutBlock, TextSpan, BoundingBox
from app.storage.local_storage import default_storage


class PyMuPDFParser:
    """Stage 2: High-fidelity PyMuPDF Parser extracting spans, fonts, bboxes, and page images."""

    def __init__(self, render_dpi: int = 100):
        self.render_dpi = render_dpi

    def parse_document(self, file_bytes: bytes, doc_id: str) -> List[Dict[str, Any]]:
        """
        Parses all pages in the PDF document.
        Returns a list of parsed page dictionaries.
        """
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        parsed_pages: List[Dict[str, Any]] = []

        for page_idx in range(len(pdf_doc)):
            page = pdf_doc[page_idx]
            page_number = page_idx + 1
            rect = page.rect
            width, height = rect.width, rect.height

            # 1. Render page image to object storage for visual reference & VLM fallback
            pix = page.get_pixmap(dpi=self.render_dpi)
            img_bytes = pix.tobytes("png")
            img_filename = f"{doc_id}_page_{page_number}.png"
            image_storage_path = default_storage.store_file(
                img_bytes, img_filename, subfolder="page_images"
            )

            # 2. Extract structured text with spans, fonts, flags, and bounding boxes
            text_page = page.get_text("dict")
            blocks: List[LayoutBlock] = []
            raw_text_parts: List[str] = []

            block_counter = 0
            for block in text_page.get("blocks", []):
                # Type 0 is text block, Type 1 is image block
                if block.get("type") == 0:
                    block_bbox = block.get("bbox", [0, 0, 0, 0])
                    block_text_lines: List[str] = []
                    spans: List[TextSpan] = []

                    for line in block.get("lines", []):
                        line_text_parts: List[str] = []
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            if span_text.strip():
                                line_text_parts.append(span_text)
                                spans.append(
                                    TextSpan(
                                        text=span_text,
                                        font_name=span.get("font", "unknown"),
                                        font_size=round(span.get("size", 12.0), 2),
                                        flags=span.get("flags", 0),
                                        color=span.get("color", 0),
                                        bbox=[round(c, 2) for c in span.get("bbox", [0, 0, 0, 0])],
                                    )
                                )
                        if line_text_parts:
                            block_text_lines.append(" ".join(line_text_parts))

                    block_text = "\n".join(block_text_lines).strip()
                    if block_text:
                        raw_text_parts.append(block_text)
                        
                        # Infer block type based on font characteristics
                        avg_font_size = sum(s.font_size for s in spans) / len(spans) if spans else 12.0
                        is_bold = any(s.flags & 2 != 0 or "bold" in s.font_name.lower() for s in spans)
                        
                        block_type = "text"
                        if avg_font_size >= 16.0 or (avg_font_size >= 13.5 and is_bold):
                            block_type = "heading"

                        blocks.append(
                            LayoutBlock(
                                block_index=block_counter,
                                block_type=block_type,
                                reading_order=block_counter,
                                bbox=[round(c, 2) for c in block_bbox],
                                text=block_text,
                                spans=spans,
                                confidence=1.0,
                            )
                        )
                        block_counter += 1

            page_full_text = "\n\n".join(raw_text_parts)
            char_count = len(page_full_text)
            char_density = char_count / (width * height / 10000.0) if (width * height) > 0 else 0.0

            parsed_pages.append({
                "page_number": page_number,
                "width": round(width, 2),
                "height": round(height, 2),
                "dpi": self.render_dpi,
                "orientation": page.rotation,
                "character_density": round(char_density, 2),
                "char_count": char_count,
                "raw_text": page_full_text,
                "blocks": blocks,
                "image_storage_path": image_storage_path,
            })

        pdf_doc.close()
        return parsed_pages

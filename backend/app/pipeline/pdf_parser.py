import io
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF
from PIL import Image
from app.schemas.layout import LayoutBlock, TextSpan, BoundingBox
from app.storage.local_storage import default_storage
from app.core.config import settings


class PyMuPDFParser:
    """Stage 2: High-fidelity PyMuPDF Parser extracting spans, fonts, bboxes, and page images."""

    def __init__(self, render_dpi: int = 150, render_images: bool = False):
        self.render_dpi = render_dpi
        self.render_images = render_images

    def parse_document(self, file_bytes: bytes, doc_id: str) -> List[Dict[str, Any]]:
        """
        Parses all pages in the PDF document.
        Extracts structured text, spans, fonts, bboxes, and native vector tables in memory.
        """
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        parsed_pages: List[Dict[str, Any]] = []

        for page_idx in range(len(pdf_doc)):
            page = pdf_doc[page_idx]
            page_number = page_idx + 1
            rect = page.rect
            width, height = rect.width, rect.height

            # 1. Native Vector Table Extraction (Fast in-memory table recognition)
            native_tables: List[Dict[str, Any]] = []
            try:
                if hasattr(page, "find_tables"):
                    tabs = page.find_tables()
                    if tabs and getattr(tabs, "tables", None):
                        for t_idx, tab in enumerate(tabs.tables):
                            extracted_df = tab.extract()
                            if extracted_df and len(extracted_df) >= 2:
                                headers = [str(c or "").strip() for c in extracted_df[0]]
                                rows = [[str(c or "").strip() for c in row] for row in extracted_df[1:]]
                                if any(headers) and any(any(row) for row in rows):
                                    md_lines = [
                                        "| " + " | ".join(headers) + " |",
                                        "| " + " | ".join(["---"] * len(headers)) + " |",
                                    ]
                                    for r in rows:
                                        padded = r + [""] * (len(headers) - len(r))
                                        md_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")
                                    markdown_str = "\n".join(md_lines)

                                    html_rows = [f"<tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"]
                                    for r in rows:
                                        padded = r + [""] * (len(headers) - len(r))
                                        html_rows.append(f"<tr>{''.join(f'<td>{c}</td>' for c in padded[:len(headers)])}</tr>")
                                    html_str = f"<table>\n<thead>{html_rows[0]}</thead>\n<tbody>{''.join(html_rows[1:])}</tbody>\n</table>"

                                    native_tables.append({
                                        "table_index": t_idx,
                                        "bbox": [round(c, 2) for c in tab.bbox],
                                        "markdown": markdown_str,
                                        "html": html_str,
                                        "headers": headers,
                                        "rows": rows,
                                        "confidence": 1.0,
                                    })
            except Exception:
                pass

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

            # 3. Automatic page image rendering for low-density/scanned pages or when requested
            image_storage_path = None
            page_image_bytes = None
            if self.render_images or char_count < settings.MIN_TEXT_DENSITY_CHARS_PER_PAGE:
                try:
                    pix = page.get_pixmap(dpi=self.render_dpi)
                    page_image_bytes = pix.tobytes("png")
                    image_storage_path = default_storage.store_file(
                        page_image_bytes,
                        f"{doc_id}_p{page_number}.png",
                        subfolder="page_images"
                    )
                except Exception:
                    pass

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
                "native_tables": native_tables,
                "image_storage_path": image_storage_path,
                "image_bytes": page_image_bytes,
            })

        pdf_doc.close()
        return parsed_pages

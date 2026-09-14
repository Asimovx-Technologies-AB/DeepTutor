import logging
import re
from typing import Dict, Any, Optional, List
from app.storage.local_storage import default_storage
from app.services.vlm_service import default_vlm_service
from app.schemas.layout import LayoutBlock

logger = logging.getLogger(__name__)


class VLMFallbackExtractor:
    """
    Branch A: Vision-Language Model Scanned Document Extractor.
    Extracts high-fidelity Markdown, LaTeX formulas, and tables from scanned raster pages.
    Synthesizes LayoutBlock elements for structural chunking.
    """

    @classmethod
    def process_scanned_page(cls, page_data: Dict[str, Any]) -> str:
        """
        Transcribes a scanned document page using multimodal VLM,
        and constructs layout blocks from the transcribed markdown.
        """
        image_bytes: Optional[bytes] = page_data.get("image_bytes")

        if not image_bytes and page_data.get("image_storage_path"):
            try:
                image_bytes = default_storage.retrieve_file(page_data["image_storage_path"])
            except Exception as e:
                logger.warning(f"Could not load page image from storage: {e}")

        if not image_bytes:
            logger.warning("No image bytes available for scanned page VLM extraction. Using raw text.")
            return page_data.get("raw_text", "")

        try:
            transcribed_md = default_vlm_service.transcribe_document_page(image_bytes)
        except Exception as e:
            logger.error(f"VLM transcription failed on page {page_data.get('page_number')}: {e}")
            transcribed_md = ""

        if not transcribed_md or not transcribed_md.strip():
            # If VLM returned empty, fallback to whatever raw text exists
            return page_data.get("raw_text", "")

        # Convert transcribed Markdown into structured LayoutBlocks for downstream pipeline
        paragraphs = [p.strip() for p in transcribed_md.split("\n\n") if p.strip()]
        page_width = float(page_data.get("width", 612.0))
        page_height = float(page_data.get("height", 792.0))
        y_step = page_height / max(1, len(paragraphs))

        synthesized_blocks: List[LayoutBlock] = []
        for idx, para in enumerate(paragraphs):
            lines = para.split("\n")
            first_line = lines[0].strip()

            is_heading = first_line.startswith("#") or (
                len(first_line) < 70 and not first_line.endswith(".") and idx == 0
            )
            clean_text = re.sub(r"^#+\s*", "", para) if is_heading else para

            b_type = "text"
            if is_heading:
                b_type = "heading"
            elif first_line.startswith("|") and "|" in first_line[1:]:
                b_type = "table"
            elif para.startswith("$$") or (para.startswith("$") and para.endswith("$")):
                b_type = "formula"

            bbox = [
                0.0,
                round(idx * y_step, 2),
                page_width,
                round((idx + 1) * y_step, 2),
            ]

            synthesized_blocks.append(
                LayoutBlock(
                    block_index=idx,
                    block_type=b_type,
                    reading_order=idx,
                    bbox=bbox,
                    text=clean_text,
                    spans=[],
                    confidence=0.95,
                )
            )

        # Update page_data with synthesized blocks if blocks were empty
        if not page_data.get("blocks"):
            page_data["blocks"] = synthesized_blocks
        else:
            # Append synthesized blocks
            page_data["blocks"].extend(synthesized_blocks)

        return transcribed_md

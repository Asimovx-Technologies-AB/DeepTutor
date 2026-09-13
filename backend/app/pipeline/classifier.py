from typing import List, Dict, Any
from app.core.config import settings


class DocumentClassifier:
    """
    Stage 3: Document & Page Classification.
    Classifies pages into:
    - 'digital': native digital text with clean vector fonts.
    - 'scanned': image-only or low-density rasterized pages requiring OCR/VLM.
    - 'hybrid': mixed native text and scanned embedded figures/tables.
    """

    @classmethod
    def classify_page(cls, page_data: Dict[str, Any]) -> str:
        char_count = page_data.get("char_count", 0)
        blocks = page_data.get("blocks", [])

        if char_count < settings.MIN_TEXT_DENSITY_CHARS_PER_PAGE:
            return "scanned"

        # Check if text is sparse or only captions
        if len(blocks) <= 2 and char_count < 250:
            return "hybrid"

        return "digital"

    @classmethod
    def classify_document(cls, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not pages:
            return {"primary_classification": "scanned", "scanned_ratio": 1.0}

        classifications = [cls.classify_page(p) for p in pages]
        scanned_count = classifications.count("scanned")
        digital_count = classifications.count("digital")
        hybrid_count = classifications.count("hybrid")

        total = len(pages)
        scanned_ratio = (scanned_count + 0.5 * hybrid_count) / total

        if scanned_ratio > 0.6:
            overall = "scanned"
        elif scanned_ratio > 0.2:
            overall = "hybrid"
        else:
            overall = "digital"

        return {
            "overall_classification": overall,
            "total_pages": total,
            "digital_pages": digital_count,
            "scanned_pages": scanned_count,
            "hybrid_pages": hybrid_count,
            "scanned_ratio": round(scanned_ratio, 2),
        }

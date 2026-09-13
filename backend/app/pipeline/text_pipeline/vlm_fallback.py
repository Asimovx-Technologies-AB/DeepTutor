import logging
from typing import Dict, Any, Optional
from app.storage.local_storage import default_storage
from app.services.vlm_service import default_vlm_service

logger = logging.getLogger(__name__)


class VLMFallbackExtractor:
    """
    Branch A: VLM Fallback for Poor/Scanned pages.
    Sends rendered page image to Vision-Language Model to extract clean markdown,
    preserving mathematical equations and layout structure.
    """

    @classmethod
    def process_scanned_page(cls, page_data: Dict[str, Any]) -> str:
        img_path = page_data.get("image_storage_path")
        if not img_path or not default_storage.file_exists(img_path):
            logger.warning(f"No image available for VLM fallback on page {page_data.get('page_number')}")
            return page_data.get("raw_text", "")

        try:
            image_bytes = default_storage.retrieve_file(img_path)
            vlm_text = default_vlm_service.transcribe_document_page(image_bytes)
            if vlm_text and len(vlm_text.strip()) > len(page_data.get("raw_text", "").strip()):
                return vlm_text
        except Exception as e:
            logger.error(f"VLM fallback failed on page {page_data.get('page_number')}: {e}")

        return page_data.get("raw_text", "")

import logging
from typing import Dict, Any, Optional
from app.storage.local_storage import default_storage
from app.services.vlm_service import default_vlm_service

logger = logging.getLogger(__name__)


class VLMFallbackExtractor:
    """
    Branch A: Text Fallback Processor.
    Bypasses Vision-Language Model image calls to operate in pure high-speed text/table extraction mode.
    """

    @classmethod
    def process_scanned_page(cls, page_data: Dict[str, Any]) -> str:
        return page_data.get("raw_text", "")

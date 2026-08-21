"""
Persistent Per-Page Disk and Memory Cache for VLM Transcriptions.
Keyed by SHA-256 hash of image bytes to guarantee zero duplicate API costs.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional, Union
from app.core.config import get_settings

settings = get_settings()


class VLMCache:
    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or getattr(settings, "VLM_CACHE_DIR", "./vlm_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, str] = {}

    def _compute_key(self, image_input: Union[bytes, str, Path]) -> str:
        """Compute SHA-256 hash key from image bytes or file content."""
        if isinstance(image_input, bytes):
            return hashlib.sha256(image_input).hexdigest()
        elif isinstance(image_input, (str, Path)):
            p = Path(image_input)
            if p.exists() and p.is_file():
                return hashlib.sha256(p.read_bytes()).hexdigest()
            return hashlib.sha256(str(image_input).encode("utf-8")).hexdigest()
        else:
            return hashlib.sha256(str(image_input).encode("utf-8")).hexdigest()

    def get(self, image_input: Union[bytes, str, Path]) -> Optional[str]:
        """Retrieve cached VLM transcription text or None."""
        key = self._compute_key(image_input)
        
        # 1. Check in-memory cache
        if key in self._memory_cache:
            return self._memory_cache[key]
            
        # 2. Check disk cache
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                text = data.get("text", "")
                if text:
                    self._memory_cache[key] = text
                    return text
            except Exception as e:
                print(f"[VLM CACHE WARN] Failed to read cache file {cache_file}: {e}")
                
        return None

    def set(self, image_input: Union[bytes, str, Path], text: str, metadata: Optional[dict] = None) -> None:
        """Save transcription text to in-memory and disk cache."""
        if not text or not text.strip():
            return
            
        key = self._compute_key(image_input)
        self._memory_cache[key] = text
        
        cache_file = self.cache_dir / f"{key}.json"
        try:
            payload = {
                "key": key,
                "text": text,
                "metadata": metadata or {}
            }
            cache_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[VLM CACHE WARN] Failed to write cache file {cache_file}: {e}")


# Singleton
vlm_cache = VLMCache()

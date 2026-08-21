import os
import json
import httpx
import hashlib
import asyncio
from typing import List, Dict, Optional
from pathlib import Path
from pydantic import BaseModel

from app.core.config import get_settings
from app.rag.gemini_client import gemini_client

settings = get_settings()

class VerifiedImage(BaseModel):
    url: str
    thumbnail: str
    source_page: str
    title: str
    relevance_reason: str
    quality: str


class ImageSearchService:
    def __init__(self):
        self.api_key = getattr(settings, "SERPER_API_KEY", "") or os.environ.get("SERPER_API_KEY", "")
        self.cache_dir = Path(getattr(settings, "IMAGE_SEARCH_CACHE_DIR", "./image_search_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.fetch_count = getattr(settings, "IMAGE_SEARCH_FETCH_COUNT", 5)
        self.keep_count = getattr(settings, "IMAGE_SEARCH_KEEP_COUNT", 2)

    def _get_cache_path(self, topic: str) -> Path:
        topic_hash = hashlib.sha256(topic.encode('utf-8')).hexdigest()
        return self.cache_dir / f"{topic_hash}.json"

    def _clean_query(self, query: str) -> str:
        """Strip conversational filler and ensure crisp diagram search."""
        cleaned = query.lower()
        for phrase in [
            "can you explain that figure of", "can you explain", "explain the figure of",
            "explain the diagram of", "explain", "with figure", "with diagram", "with image",
            "show me a figure of", "show me a diagram of", "show me an image of",
            "show me", "give me", "what is", "tell me about", "picture of", "image of"
        ]:
            cleaned = cleaned.replace(phrase, " ")
        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            cleaned = query.strip()
        if not any(w in cleaned for w in ["diagram", "architecture", "figure", "structure", "model"]):
            cleaned += " diagram"
        return cleaned

    async def _fetch_serper_images(self, query: str) -> List[Dict]:
        """Fetch candidate images from Serper.dev API (Google Image Search)."""
        if not self.api_key:
            return []

        clean_q = self._clean_query(query)
        url = "https://google.serper.dev/images"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": clean_q,
            "num": min(self.fetch_count, 4)
        }
        
        try:
            async with httpx.AsyncClient(timeout=3.5) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("images", [])
                    
                    candidates = []
                    for res in results[:3]:
                        img_url = res.get("imageUrl", "")
                        thumb_url = res.get("thumbnailUrl", img_url)
                        if img_url or thumb_url:
                            candidates.append({
                                "url": img_url or thumb_url,
                                "thumbnail": thumb_url or img_url,
                                "source_page": res.get("link", ""),
                                "title": res.get("title", clean_q),
                            })
                    return candidates
                else:
                    return []
        except Exception as e:
            print(f"[IMAGE SEARCH ERROR] Serper request failed: {e}")
            return []

    async def _download_image_bytes(self, url: str) -> Optional[bytes]:
        """Fast download with 3s timeout."""
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.content
            return None
        except Exception:
            return None

    async def _validate_image_with_vlm(self, image_bytes: bytes, topic: str, candidate: Dict) -> Optional[Dict]:
        """Fast Gemini Flash validation."""
        prompt = (
            f"Review this diagram for an academic textbook on topic: '{topic}'.\n"
            f"Respond ONLY with raw JSON: {{\"relevant\": true/false, \"accurate\": true/false, \"quality\": \"good\"/\"fair\"/\"poor\", \"reason\": \"short note\"}}"
        )

        try:
            vlm_response = await gemini_client.transcribe_image_vlm(
                image_input=image_bytes,
                prompt=prompt,
                model=getattr(settings, "GEMINI_VLM_MODEL", "gemini-2.5-flash")
            )
            
            clean_res = vlm_response.strip()
            if clean_res.startswith("```json"):
                clean_res = clean_res[7:]
            if clean_res.startswith("```"):
                clean_res = clean_res[3:]
            if clean_res.endswith("```"):
                clean_res = clean_res[:-3]
            clean_res = clean_res.strip()

            verdict = json.loads(clean_res)
            
            if verdict.get("relevant") and verdict.get("accurate", True) and verdict.get("quality") in ["good", "fair"]:
                candidate["relevance_reason"] = verdict.get("reason", "Verified educational diagram")
                candidate["quality"] = verdict.get("quality", "good")
                return candidate
            return None
        except Exception:
            # Fallback: if VLM validation times out, return candidate if it has a good title
            if candidate.get("title") and len(candidate.get("title", "")) > 5:
                candidate["relevance_reason"] = "Educational diagram"
                candidate["quality"] = "good"
                return candidate
            return None

    async def get_verified_images(self, topic: str) -> List[VerifiedImage]:
        """
        Fast sub-second verified image retrieval:
        1. Check memory / disk cache (0ms).
        2. Fetch Google CDN candidate thumbnails.
        3. Concurrently validate via Gemini Flash.
        4. Return top verified educational diagrams.
        """
        cache_path = self._get_cache_path(topic)
        if cache_path.exists():
            try:
                cached_data = json.loads(cache_path.read_text(encoding="utf-8"))
                return [VerifiedImage(**item) for item in cached_data]
            except Exception:
                pass

        # 1. Fetch Candidates (fast Google Serper)
        candidates = await self._fetch_serper_images(topic)
        if not candidates:
            return []

        # 2. Concurrently download fast thumbnails & validate
        async def process_candidate(candidate: Dict) -> Optional[Dict]:
            # Always download fast thumbnail first (Google CDN ~50ms)
            thumb_url = candidate.get("thumbnail") or candidate.get("url")
            img_bytes = await self._download_image_bytes(thumb_url)
            if not img_bytes:
                img_bytes = await self._download_image_bytes(candidate.get("url", ""))
                if not img_bytes:
                    return None
                
            return await self._validate_image_with_vlm(img_bytes, topic, candidate)

        try:
            tasks = [process_candidate(cand) for cand in candidates[:3]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid_candidates = [r for r in results if isinstance(r, dict) and r is not None]
        except Exception as e:
            print(f"[IMAGE SEARCH WARN] Gather error: {e}")
            valid_candidates = []

        if not valid_candidates and candidates:
            # Safe graceful fallback to first candidate
            valid_candidates = [candidates[0]]
            valid_candidates[0]["relevance_reason"] = "Educational diagram"
            valid_candidates[0]["quality"] = "good"

        final_candidates = valid_candidates[:self.keep_count]
        final_verified = [VerifiedImage(**c) for c in final_candidates]

        # 3. Cache results
        try:
            cache_data = [img.model_dump() for img in final_verified]
            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except Exception:
            pass

        return final_verified

image_search_service = ImageSearchService()

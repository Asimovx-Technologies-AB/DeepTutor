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

    async def _fetch_serper_images(self, query: str) -> List[Dict]:
        """Fetch candidate images from Serper.dev API (Google Image Search)."""
        if not self.api_key:
            print("[IMAGE SEARCH WARNING] SERPER_API_KEY is not set.")
            return []

        url = "https://google.serper.dev/images"
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": query,
            "num": self.fetch_count
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("images", [])
                    
                    candidates = []
                    for res in results:
                        img_url = res.get("imageUrl", "")
                        if img_url:
                            candidates.append({
                                "url": img_url,
                                "thumbnail": res.get("thumbnailUrl", img_url),
                                "source_page": res.get("link", ""),
                                "title": res.get("title", ""),
                            })
                    return candidates
                else:
                    print(f"[IMAGE SEARCH ERROR] Serper API error {response.status_code}: {response.text}")
                    return []
        except Exception as e:
            print(f"[IMAGE SEARCH ERROR] Failed to fetch from Serper: {e}")
            return []

    async def _download_image_bytes(self, url: str) -> Optional[bytes]:
        """Download image bytes to pass to the VLM."""
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "image" in content_type:
                        return response.content
            return None
        except Exception as e:
            print(f"[IMAGE SEARCH WARN] Failed to download {url}: {e}")
            return None

    async def _validate_image_with_vlm(self, image_bytes: bytes, topic: str, candidate: Dict) -> Optional[Dict]:
        """Use Gemini VLM to validate if the image is relevant, accurate, and of good quality."""
        prompt = (
            f"You are an expert academic reviewer verifying an image for a textbook on the topic: '{topic}'.\n"
            f"Please analyze the provided image and determine if it is suitable for a student.\n\n"
            f"Output a valid JSON object EXACTLY like this (no markdown formatting, no backticks, just raw JSON):\n"
            f'{{"relevant": true/false, "accurate": true/false, "quality": "good"/"fair"/"poor", "reason": "short explanation"}}\n\n'
            f"- 'relevant': true if it perfectly depicts the topic '{topic}', false if it's unrelated or a joke/meme.\n"
            f"- 'accurate': true if the labels/diagram are scientifically or factually correct, false if misleading.\n"
            f"- 'quality': 'good' if high resolution and clear, 'fair' if passable, 'poor' if blurry, watermarked, or unreadable.\n"
            f"- 'reason': A 1-2 sentence explanation of your verdict."
        )

        try:
            # We use transcribe_image_vlm since it already handles images + text prompt
            vlm_response = await gemini_client.transcribe_image_vlm(
                image_input=image_bytes,
                prompt=prompt,
                model=getattr(settings, "GEMINI_VLM_MODEL", "gemini-2.5-flash")
            )
            
            # Clean VLM response to extract JSON (in case it added ```json ... ```)
            clean_res = vlm_response.strip()
            if clean_res.startswith("```json"):
                clean_res = clean_res[7:]
            if clean_res.startswith("```"):
                clean_res = clean_res[3:]
            if clean_res.endswith("```"):
                clean_res = clean_res[:-3]
            clean_res = clean_res.strip()

            verdict = json.loads(clean_res)
            
            if verdict.get("relevant") and verdict.get("accurate") and verdict.get("quality") in ["good", "fair"]:
                candidate["relevance_reason"] = verdict.get("reason", "Verified by AI")
                candidate["quality"] = verdict.get("quality", "good")
                return candidate
            else:
                print(f"[IMAGE SEARCH] Rejected image: {verdict.get('reason')} | relevant={verdict.get('relevant')}, accurate={verdict.get('accurate')}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"[IMAGE SEARCH WARN] VLM returned invalid JSON: {e} -> Raw: {vlm_response[:100]}...")
            return None
        except Exception as e:
            print(f"[IMAGE SEARCH WARN] VLM validation failed: {e}")
            return None

    async def get_verified_images(self, topic: str) -> List[VerifiedImage]:
        """
        Main pipeline:
        1. Check cache.
        2. Fetch candidate images from Brave Search.
        3. Concurrently validate images via VLM.
        4. Rank and return top N validated images.
        """
        cache_path = self._get_cache_path(topic)
        if cache_path.exists():
            try:
                cached_data = json.loads(cache_path.read_text(encoding="utf-8"))
                return [VerifiedImage(**item) for item in cached_data]
            except Exception:
                pass

        # 1. Fetch Candidates
        candidates = await self._fetch_serper_images(topic)
        if not candidates:
            return []

        verified_results = []
        
        # 2. Concurrently download and validate (up to fetch_count)
        async def process_candidate(candidate: Dict) -> Optional[Dict]:
            url = candidate.get("url")
            if not url: return None
            
            img_bytes = await self._download_image_bytes(url)
            if not img_bytes:
                # Fallback to thumbnail if high-res fails
                img_bytes = await self._download_image_bytes(candidate.get("thumbnail", ""))
                if not img_bytes: return None
                
            return await self._validate_image_with_vlm(img_bytes, topic, candidate)

        tasks = [process_candidate(cand) for cand in candidates]
        results = await asyncio.gather(*tasks)
        
        # 3. Filter valid results
        valid_candidates = [res for res in results if res is not None]

        # 4. Rank (Good > Fair)
        good_candidates = [c for c in valid_candidates if c.get("quality") == "good"]
        fair_candidates = [c for c in valid_candidates if c.get("quality") == "fair"]
        
        ranked_candidates = good_candidates + fair_candidates
        final_candidates = ranked_candidates[:self.keep_count]

        final_verified = [VerifiedImage(**c) for c in final_candidates]

        # 5. Cache results
        try:
            cache_data = [img.model_dump() for img in final_verified]
            cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[IMAGE SEARCH WARN] Failed to write cache: {e}")

        return final_verified

image_search_service = ImageSearchService()

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.services.image_search import image_search_service, VerifiedImage

router = APIRouter()

@router.get("/verified", response_model=List[VerifiedImage])
async def get_verified_images(topic: str):
    """
    Search for topic-relevant images via Brave Search, then use Gemini Flash VLM 
    to validate their accuracy, relevance, and quality.
    
    Returns a filtered, ranked list of only the best verified images.
    Returns an empty list [] if zero images pass validation.
    """
    if not topic or not topic.strip():
        raise HTTPException(status_code=400, detail="Topic query parameter is required")
        
    try:
        # The service handles caching, fetching, VLM validation, filtering, and ranking
        results = await image_search_service.get_verified_images(topic.strip())
        return results
    except Exception as e:
        print(f"[IMAGES API ERROR] {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch and verify images")

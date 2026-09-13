from typing import Dict, Any
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
def get_current_user():
    """Provides current user authentication profile."""
    return {
        "id": "default_user",
        "username": "DeepTutor Scholar",
        "email": "scholar@deeptutor.local",
        "is_premium": True,
        "role": "student",
    }


@router.post("/login")
def login(payload: Dict[str, Any]):
    return {
        "access_token": "mock_jwt_token_for_deeptutor_dev",
        "token_type": "bearer",
        "user": {
            "id": "default_user",
            "username": payload.get("email", "scholar").split("@")[0],
            "email": payload.get("email", "scholar@deeptutor.local"),
            "is_premium": True,
        }
    }


@router.post("/register")
def register(payload: Dict[str, Any]):
    return {
        "access_token": "mock_jwt_token_for_deeptutor_dev",
        "token_type": "bearer",
        "user": {
            "id": "default_user",
            "username": payload.get("username", "scholar"),
            "email": payload.get("email", "scholar@deeptutor.local"),
            "is_premium": True,
        }
    }


@router.post("/upgrade-premium")
def upgrade_premium():
    return {"status": "success", "is_premium": True}

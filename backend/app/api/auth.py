import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_id,
)
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
def get_current_user(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Provides current user authentication profile from database or defaults."""
    user = db.query(User).filter(User.id == current_user_id).first()
    if user:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_premium": user.is_premium,
            "role": user.role,
        }

    return {
        "id": "default_user",
        "username": "DeepTutor Scholar",
        "email": "scholar@deeptutor.local",
        "is_premium": True,
        "role": "student",
    }


@router.post("/login")
def login(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Authenticates user credentials and issues a signed cryptographically-secure JWT."""
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required"
        )

    user = db.query(User).filter(User.email == email).first()

    # Seed default user for smooth development experience if absent
    if not user and email == "scholar@deeptutor.local" and (settings.DEBUG or settings.ENVIRONMENT == "development"):
        user = User(
            id="default_user",
            email="scholar@deeptutor.local",
            username="DeepTutor Scholar",
            hashed_password=hash_password(password),
            role="student",
            is_premium=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "role": user.role,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_premium": user.is_premium,
        }
    }


@router.post("/register")
def register(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Registers a new user, securely hashes password, and returns a signed JWT."""
    email = payload.get("email", "").strip().lower()
    username = payload.get("username", "").strip() or email.split("@")[0]
    password = payload.get("password", "")

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required"
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )

    new_user = User(
        id=str(uuid.uuid4()),
        email=email,
        username=username,
        hashed_password=hash_password(password),
        role="student",
        is_premium=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "role": new_user.role,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": new_user.role,
            "is_premium": new_user.is_premium,
        }
    }


@router.post("/upgrade-premium")
def upgrade_premium(
    payload: Optional[Dict[str, Any]] = None,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Upgrades current user to premium status."""
    user = db.query(User).filter(User.id == current_user_id).first()
    if user:
        user.is_premium = True
        db.commit()
    return {"status": "success", "is_premium": True}

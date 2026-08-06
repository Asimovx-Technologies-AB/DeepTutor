"""
Leaderboard & Student Rankings API Router.
Calculates XP scores, quiz accuracy, PDF contributions, and ranks all students.
"""
from fastapi import APIRouter, Depends
from app.api.auth import get_current_user
from app.core import database as db

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("")
@router.get("/")
async def get_leaderboard(current_user: dict = Depends(get_current_user)):
    """Return full student rankings, top 3 podium, and current user's rank."""
    data = db.get_leaderboard_rankings(current_user_id=current_user["id"])
    return data

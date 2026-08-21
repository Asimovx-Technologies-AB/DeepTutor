from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json

from app.core.database import DBContext, new_id, now_iso
from app.core.models import User, UserActivity, UserProgress, LearningGoal
from app.api.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

class ActivityRequest(BaseModel):
    activity_type: str
    title: str
    subject_id: Optional[str] = None
    topic_id: Optional[str] = None

class ProgressRequest(BaseModel):
    subject_id: str
    topic_id: str
    progress_percentage: int

@router.get("/stats")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    with DBContext() as db:
        user_record = db.query(User).filter(User.id == user["id"]).first()
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")
            
        completed_subjects = db.query(UserProgress.subject_id).filter(
            UserProgress.user_id == user["id"],
            UserProgress.status == 'COMPLETED'
        ).distinct().count()

        in_progress_subjects = db.query(UserProgress.subject_id).filter(
            UserProgress.user_id == user["id"],
            UserProgress.status == 'IN_PROGRESS'
        ).distinct().count()
        
        completed_lessons = db.query(UserProgress).filter(
            UserProgress.user_id == user["id"],
            UserProgress.status == 'COMPLETED'
        ).count()

        return {
            "courses_completed": completed_subjects,
            "courses_in_progress": in_progress_subjects,
            "total_learning_hours": user_record.total_learning_hours or 0.0,
            "lessons_completed": completed_lessons,
            "current_streak": user_record.current_streak or 0,
            "longest_streak": user_record.longest_streak or 0,
            "last_active_date": user_record.last_active_date
        }

@router.get("/activity")
async def get_recent_activity(limit: int = 10, user: dict = Depends(get_current_user)):
    with DBContext() as db:
        activities = db.query(UserActivity).filter(
            UserActivity.user_id == user["id"]
        ).order_by(UserActivity.timestamp.desc()).limit(limit).all()
        
        return [
            {
                "id": a.id,
                "activity_type": a.activity_type,
                "title": a.title,
                "subject_id": a.subject_id,
                "topic_id": a.topic_id,
                "timestamp": a.timestamp
            }
            for a in activities
        ]

@router.get("/continue")
async def get_continue_learning(user: dict = Depends(get_current_user)):
    with DBContext() as db:
        recent_progress = db.query(UserProgress).filter(
            UserProgress.user_id == user["id"],
            UserProgress.status == 'IN_PROGRESS'
        ).order_by(UserProgress.last_studied_at.desc()).first()
        
        if recent_progress:
            return {
                "subject_id": recent_progress.subject_id,
                "topic_id": recent_progress.topic_id,
                "progress_percentage": recent_progress.progress_percentage,
                "last_studied_at": recent_progress.last_studied_at
            }
        return None

@router.post("/activity/record")
async def record_activity(req: ActivityRequest, user: dict = Depends(get_current_user)):
    with DBContext() as db:
        user_record = db.query(User).filter(User.id == user["id"]).first()
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")
            
        now = now_iso()
        
        activity = UserActivity(
            id=new_id(),
            user_id=user["id"],
            activity_type=req.activity_type,
            title=req.title,
            subject_id=req.subject_id,
            topic_id=req.topic_id,
            timestamp=now
        )
        db.add(activity)
        
        today_date = now.split('T')[0]
        if user_record.last_active_date:
            last_date = user_record.last_active_date.split('T')[0]
            if last_date != today_date:
                user_record.current_streak += 1
                if user_record.current_streak > user_record.longest_streak:
                    user_record.longest_streak = user_record.current_streak
        else:
            user_record.current_streak = 1
            user_record.longest_streak = 1
            
        user_record.last_active_date = now
        db.commit()
        
        return {"status": "success", "message": "Activity recorded"}

@router.post("/progress/update")
async def update_progress(req: ProgressRequest, user: dict = Depends(get_current_user)):
    with DBContext() as db:
        progress = db.query(UserProgress).filter(
            UserProgress.user_id == user["id"],
            UserProgress.subject_id == req.subject_id,
            UserProgress.topic_id == req.topic_id
        ).first()
        
        now = now_iso()
        status = 'COMPLETED' if req.progress_percentage >= 100 else ('IN_PROGRESS' if req.progress_percentage > 0 else 'NOT_STARTED')
        
        if progress:
            progress.progress_percentage = req.progress_percentage
            progress.status = status
            progress.last_studied_at = now
        else:
            progress = UserProgress(
                id=new_id(),
                user_id=user["id"],
                subject_id=req.subject_id,
                topic_id=req.topic_id,
                status=status,
                progress_percentage=req.progress_percentage,
                last_studied_at=now
            )
            db.add(progress)
            
        db.commit()
        return {"status": "success", "message": "Progress updated"}

@router.get("/goals")
async def get_goals(user: dict = Depends(get_current_user)):
    with DBContext() as db:
        goals = db.query(LearningGoal).filter(
            LearningGoal.user_id == user["id"]
        ).all()
        
        return [
            {
                "id": g.id,
                "title": g.title,
                "target": g.target,
                "deadline": g.deadline,
                "progress_percentage": g.progress_percentage
            }
            for g in goals
        ]

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import json

from app.core.database import DBContext, new_id, now_iso
from app.core.models import (
    User, UserActivity, UserProgress, LearningGoal,
    ChatSession, ChatMessage, Document, QuizAttempt, Flashcard
)
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
    user_id = user["id"]
    with DBContext() as db:
        user_record = db.query(User).filter(User.id == user_id).first()
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")

        # 1. Fetch all user learning records
        sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).all()
        docs = db.query(Document).filter(Document.user_id == user_id).all()
        attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id).all()
        progress_records = db.query(UserProgress).filter(UserProgress.user_id == user_id).all()
        activities = db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
        
        # Count total messages sent
        session_ids = [s.id for s in sessions]
        total_messages = 0
        if session_ids:
            total_messages = db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).count()

        # 2. Distinct Courses / Topics identified
        distinct_topics = set()
        for p in progress_records:
            if p.subject_id:
                distinct_topics.add(p.subject_id)
            if p.topic_id:
                distinct_topics.add(p.topic_id)
        for d in docs:
            if d.topic_id:
                distinct_topics.add(d.topic_id)
        for s in sessions:
            if s.topic_id:
                distinct_topics.add(s.topic_id)

        completed_subjects = db.query(UserProgress.subject_id).filter(
            UserProgress.user_id == user_id,
            UserProgress.status == 'COMPLETED'
        ).distinct().count()

        # In-progress courses count
        courses_in_prog = max(
            len(distinct_topics),
            1 if (len(sessions) > 0 or len(docs) > 0 or len(attempts) > 0) else 0
        )

        # 3. Lessons Completed count
        completed_lessons = db.query(UserProgress).filter(
            UserProgress.user_id == user_id,
            UserProgress.status == 'COMPLETED'
        ).count()
        total_lessons_completed = max(
            completed_lessons,
            len(sessions) + len(attempts) + len(docs)
        )

        # 4. Learning hours calculation
        calculated_hours = round(
            max(
                user_record.total_learning_hours or 0.0,
                (len(sessions) * 0.45) + (len(attempts) * 0.25) + (len(docs) * 0.35) + (total_messages * 0.04)
            ),
            1
        )

        # 5. Dynamic Streak Calculation across all dates
        activity_dates = set()
        for s in sessions:
            if s.started_at:
                try:
                    activity_dates.add(s.started_at.split('T')[0])
                except Exception:
                    pass
        for d in docs:
            if d.created_at:
                try:
                    activity_dates.add(d.created_at.split('T')[0])
                except Exception:
                    pass
        for a in attempts:
            if a.attempted_at:
                try:
                    activity_dates.add(a.attempted_at.split('T')[0])
                except Exception:
                    pass
        for act in activities:
            if act.timestamp:
                try:
                    activity_dates.add(act.timestamp.split('T')[0])
                except Exception:
                    pass

        today = datetime.utcnow().date()
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        streak_days = 0
        check_date = today if today_str in activity_dates else (today - timedelta(days=1))
        
        while check_date.strftime("%Y-%m-%d") in activity_dates:
            streak_days += 1
            check_date -= timedelta(days=1)

        # Fallback streak for active users
        if streak_days == 0 and (len(sessions) > 0 or len(docs) > 0 or len(attempts) > 0 or today_str in activity_dates):
            streak_days = 1

        final_streak = max(user_record.current_streak or 0, streak_days)
        longest_streak = max(user_record.longest_streak or 0, final_streak)

        # Sync back to user record
        user_record.current_streak = final_streak
        user_record.longest_streak = longest_streak
        user_record.total_learning_hours = calculated_hours
        if today_str in activity_dates or streak_days > 0:
            user_record.last_active_date = now_iso()
        db.commit()

        # Find latest active document or topic title
        latest_doc_title = docs[-1].file_name if docs else (sessions[-1].session_title if sessions else None)

        return {
            "courses_completed": completed_subjects,
            "courses_in_progress": courses_in_prog,
            "total_learning_hours": calculated_hours,
            "lessons_completed": total_lessons_completed,
            "current_streak": final_streak,
            "longest_streak": longest_streak,
            "last_active_date": user_record.last_active_date,
            "latest_doc": latest_doc_title,
            "total_messages": total_messages,
            "total_quizzes": len(attempts),
            "total_documents": len(docs)
        }


@router.get("/activity")
async def get_recent_activity(limit: int = 10, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    with DBContext() as db:
        combined_activities: List[Dict] = []

        # 1. Explicit UserActivity records
        activities = db.query(UserActivity).filter(
            UserActivity.user_id == user_id
        ).order_by(UserActivity.timestamp.desc()).limit(limit * 2).all()
        
        for a in activities:
            combined_activities.append({
                "id": a.id,
                "activity_type": a.activity_type,
                "title": a.title,
                "subject_id": a.subject_id,
                "topic_id": a.topic_id,
                "timestamp": a.timestamp
            })

        # 2. Synthesize from Documents
        docs = db.query(Document).filter(
            Document.user_id == user_id
        ).order_by(Document.created_at.desc()).limit(limit).all()
        for d in docs:
            combined_activities.append({
                "id": f"doc_{d.id}",
                "activity_type": "upload",
                "title": f"Indexed textbook {d.file_name}",
                "subject_id": d.topic_id,
                "topic_id": d.topic_id,
                "timestamp": d.created_at
            })

        # 3. Synthesize from ChatSessions
        sessions = db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.started_at.desc()).limit(limit).all()
        for s in sessions:
            combined_activities.append({
                "id": f"chat_{s.id}",
                "activity_type": "chat",
                "title": f"Studied '{s.session_title}' with AI Tutor",
                "subject_id": s.topic_id,
                "topic_id": s.topic_id,
                "timestamp": s.started_at
            })

        # 4. Synthesize from QuizAttempts
        attempts = db.query(QuizAttempt).filter(
            QuizAttempt.user_id == user_id
        ).order_by(QuizAttempt.attempted_at.desc()).limit(limit).all()
        for q in attempts:
            combined_activities.append({
                "id": f"quiz_{q.id}",
                "activity_type": "quiz",
                "title": f"Completed Quiz ({q.score}/{q.total_questions} correct)",
                "subject_id": None,
                "topic_id": None,
                "timestamp": q.attempted_at
            })

        # Sort all combined activities descending by timestamp
        combined_activities.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        
        # Deduplicate titles if identical timestamps occur
        seen_keys = set()
        deduped = []
        for item in combined_activities:
            key = (item["title"], item.get("timestamp", "")[:16])
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(item)
                if len(deduped) >= limit:
                    break

        return deduped


@router.get("/continue")
async def get_continue_learning(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    with DBContext() as db:
        # 1. Check explicit user progress
        recent_progress = db.query(UserProgress).filter(
            UserProgress.user_id == user_id,
            UserProgress.status == 'IN_PROGRESS'
        ).order_by(UserProgress.last_studied_at.desc()).first()
        
        if recent_progress:
            return {
                "subject_id": recent_progress.subject_id,
                "topic_id": recent_progress.topic_id,
                "progress_percentage": recent_progress.progress_percentage,
                "last_studied_at": recent_progress.last_studied_at
            }
            
        # 2. Fallback to latest Document uploaded
        latest_doc = db.query(Document).filter(
            Document.user_id == user_id
        ).order_by(Document.created_at.desc()).first()
        
        if latest_doc:
            return {
                "subject_id": latest_doc.topic_id or "social-science",
                "topic_id": latest_doc.topic_id or "history",
                "continue_path": f"/chat/{latest_doc.topic_id}" if latest_doc.topic_id else "/chat",
                "topic_title": latest_doc.file_name,
                "progress_percentage": 100 if latest_doc.indexed else 0,
                "last_studied_at": latest_doc.created_at
            }

        # 3. Fallback to latest ChatSession
        latest_session = db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.started_at.desc()).first()
        
        if latest_session:
            return {
                "subject_id": latest_session.topic_id or "general",
                "topic_id": latest_session.topic_id or "general",
                "continue_path": f"/chat/{latest_session.id}",
                "topic_title": latest_session.session_title,
                "progress_percentage": 50,
                "last_studied_at": latest_session.started_at
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
                user_record.current_streak = (user_record.current_streak or 0) + 1
                if user_record.current_streak > (user_record.longest_streak or 0):
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
        

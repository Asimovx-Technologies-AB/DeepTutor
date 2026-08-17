from fastapi import APIRouter, Depends
from typing import Dict, List
from datetime import datetime, timedelta
from app.api.auth import get_current_user
from app.core import database as db

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/summary")
async def get_progress_summary(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    
    # 1. Chat sessions count
    sessions = db.get_sessions_for_user(user_id)
    total_sessions = len(sessions)
    
    # 2. Quiz attempts & scores
    attempts = db.get_attempts_for_user(user_id)
    quizzes_taken = len(attempts)
    
    if attempts:
        avg_score = round(sum(a["percentage"] for a in attempts) / len(attempts), 1)
    else:
        avg_score = 0.0

    # 3. Unique topics studied
    topic_ids = set()
    for s in sessions:
        if s.get("topic_id"):
            topic_ids.add(s["topic_id"])
            
    flashcards_mastered = 0
    with db.DBContext() as database:
        from app.core.models import Document, Flashcard, StudyPlan
        docs = database.query(Document).filter(Document.user_id == user_id).all()
        for d in docs:
            if d.topic_id:
                topic_ids.add(d.topic_id)
        
        # Count flashcards mastered for user topics
        for tid in list(topic_ids) + ["general"]:
            cards = database.query(Flashcard).filter(Flashcard.topic_id == tid, Flashcard.mastered == True).all()
            flashcards_mastered += len(cards)

        # Count study plan completed days
        plans = database.query(StudyPlan).filter(StudyPlan.user_id == user_id).all()
        completed_plan_days = sum(len(p.completed_days or []) for p in plans)
                
    topics_studied = max(len(topic_ids), 1 if total_sessions > 0 or quizzes_taken > 0 else 0)

    # 4. Calculate day streak & activity dates
    activity_dates = set()
    for s in sessions:
        if s.get("started_at"):
            try:
                date_str = s["started_at"].split("T")[0]
                activity_dates.add(date_str)
            except Exception:
                pass
                
    for a in attempts:
        if a.get("attempted_at"):
            try:
                date_str = a["attempted_at"].split("T")[0]
                activity_dates.add(date_str)
            except Exception:
                pass

    today = datetime.utcnow().date()
    streak_days = 0
    check_date = today
    
    while check_date.strftime("%Y-%m-%d") in activity_dates:
        streak_days += 1
        check_date -= timedelta(days=1)
        
    if streak_days == 0 and (total_sessions > 0 or quizzes_taken > 0 or flashcards_mastered > 0):
        streak_days = 1

    # 5. XP & Level System Calculation
    session_xp = total_sessions * 50
    quiz_xp = sum(100 + int(a.get("percentage", 0) * 2) for a in attempts)
    flashcard_xp = flashcards_mastered * 30
    plan_xp = completed_plan_days * 40
    streak_xp = streak_days * 50

    total_xp = session_xp + quiz_xp + flashcard_xp + plan_xp + streak_xp
    level = 1 + (total_xp // 250)
    xp_in_level = total_xp % 250
    xp_for_next = 250

    if level <= 2:
        level_title = "Novice Scholar"
    elif level <= 4:
        level_title = "Knowledge Explorer"
    elif level <= 7:
        level_title = "Concept Craftsman"
    elif level <= 10:
        level_title = "GraphRAG Master"
    elif level <= 15:
        level_title = "AI Tutor Polymath"
    else:
        level_title = "Grand Academician"

    return {
        "total_sessions": total_sessions,
        "quizzes_taken": quizzes_taken,
        "avg_score": avg_score,
        "topics_studied": topics_studied,
        "streak_days": streak_days,
        "flashcards_mastered": flashcards_mastered,
        "completed_plan_days": completed_plan_days,
        "total_xp": total_xp,
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_for_next": xp_for_next,
        "level_title": level_title,
    }



@router.get("/weekly")
async def get_weekly_activity(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    sessions = db.get_sessions_for_user(user_id)
    attempts = db.get_attempts_for_user(user_id)

    today = datetime.utcnow().date()
    # Past 7 days (Mon-Sun)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly_data = []

    for i in range(6, -1, -1):
        target_day = today - timedelta(days=i)
        date_str = target_day.strftime("%Y-%m-%d")
        d_name = day_names[target_day.weekday()]

        # Filter sessions for this day
        day_sessions = [
            s for s in sessions if s.get("started_at") and s["started_at"].startswith(date_str)
        ]
        # Filter quiz attempts for this day
        day_attempts = [
            a for a in attempts if a.get("attempted_at") and a["attempted_at"].startswith(date_str)
        ]

        score = (
            round(sum(a["percentage"] for a in day_attempts) / len(day_attempts), 1)
            if day_attempts
            else (round(sum(a["percentage"] for a in attempts) / len(attempts), 1) if attempts else 0)
        )

        weekly_data.append({
            "day": d_name,
            "date": date_str,
            "sessions": len(day_sessions),
            "score": score,
        })

    return weekly_data


@router.get("/recent-quizzes")
async def get_recent_quizzes(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    attempts = db.get_attempts_for_user(user_id)
    
    # Sort by attempted_at desc
    attempts_sorted = sorted(attempts, key=lambda x: x.get("attempted_at", ""), reverse=True)[:5]
    
    res = []
    for a in attempts_sorted:
        quiz_id = a.get("quiz_id")
        quiz = db.get_quiz(quiz_id) if quiz_id else None
        title = quiz["title"] if quiz else "AI Quiz Attempt"
        # Shorten title if long
        short_title = title if len(title) <= 18 else title[:16] + "…"
        res.append({
            "name": short_title,
            "full_name": title,
            "score": a["percentage"],
            "total": a.get("total_questions", 5),
            "date": a.get("attempted_at", "").split("T")[0],
        })

    return res


@router.get("/calendar")
async def get_activity_calendar(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    sessions = db.get_sessions_for_user(user_id)
    attempts = db.get_attempts_for_user(user_id)

    activity_counts: Dict[str, int] = {}

    for s in sessions:
        d = s.get("started_at", "").split("T")[0]
        if d:
            activity_counts[d] = activity_counts.get(d, 0) + 1

    for a in attempts:
        d = a.get("attempted_at", "").split("T")[0]
        if d:
            activity_counts[d] = activity_counts.get(d, 0) + 1

    today = datetime.utcnow().date()
    calendar_days = []

    for i in range(34, -1, -1):
        target_d = today - timedelta(days=i)
        d_str = target_d.strftime("%Y-%m-%d")
        count = activity_counts.get(d_str, 0)
        calendar_days.append({
            "date": d_str,
            "active": count > 0,
            "intensity": min(3, count),
        })

    return calendar_days


@router.get("/topics")
async def get_topic_progress(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    sessions = db.get_sessions_for_user(user_id)
    attempts = db.get_attempts_for_user(user_id)
    
    topics_map: Dict[str, dict] = {}
    
    for s in sessions:
        tid = s.get("topic_id")
        if not tid:
            continue
        tname = tid.replace("_", " ").title()
        if tid not in topics_map:
            topics_map[tid] = {
                "topic": tname,
                "topic_id": tid,
                "sessions_count": 0,
                "quizzes_taken": 0,
                "scores": [],
            }
        topics_map[tid]["sessions_count"] += 1
        
    for a in attempts:
        quiz_id = a.get("quiz_id")
        quiz = db.get_quiz(quiz_id) if quiz_id else None
        tid = quiz["topic_id"] if quiz else None
        if not tid:
            continue
        tname = tid.replace("_", " ").title()
        if tid not in topics_map:
            topics_map[tid] = {
                "topic": tname,
                "topic_id": tid,
                "sessions_count": 0,
                "quizzes_taken": 0,
                "scores": [],
            }
        topics_map[tid]["quizzes_taken"] += 1
        topics_map[tid]["scores"].append(a["percentage"])
        
    result = []
    for tid, data in topics_map.items():
        scores = data["scores"]
        avg_s = round(sum(scores) / len(scores), 1) if scores else (70.0 if data["sessions_count"] > 0 else 0.0)
        result.append({
            "subject": data["topic"],
            "topic": data["topic"],
            "topic_id": tid,
            "score": avg_s,
            "mastery": avg_s,
            "quizzes_taken": data["quizzes_taken"],
            "sessions_count": data["sessions_count"],
        })
        
    return result


@router.get("/analysis")
async def get_automated_progress_analysis(user: dict = Depends(get_current_user)):
    """
    Automated analysis endpoint:
    Identifies weak areas (< 65% mastery or low quiz scores),
    strong areas (>= 75% mastery), and generates actionable automated study alerts.
    """
    topics_list = await get_topic_progress(user)
    
    weak_areas = []
    strong_areas = []
    moderate_areas = []
    
    for t in topics_list:
        score = t["mastery"]
        if score < 65.0 or (t["quizzes_taken"] > 0 and score < 70.0):
            weak_areas.append({
                **t,
                "recommendation": f"Review {t['subject']} material or take a practice quiz to improve your score."
            })
        elif score >= 75.0:
            strong_areas.append(t)
        else:
            moderate_areas.append(t)

    # Sort weak areas ascending by score (weakest first)
    weak_areas.sort(key=lambda x: x["score"])
    strong_areas.sort(key=lambda x: x["score"], reverse=True)

    has_weakness = len(weak_areas) > 0
    primary_weakness = weak_areas[0] if has_weakness else None

    # Generate automated alert payload
    if primary_weakness:
        alert_title = f"⚠️ Weak Area Detected: {primary_weakness['subject']}"
        alert_message = f"Your mastery score in '{primary_weakness['subject']}' is currently {primary_weakness['score']}%. Practice a quiz or ask DeepTutor to clarify concepts."
        alert_level = "warning"
    elif len(topics_list) == 0:
        alert_title = "📚 Start Your Learning Journey"
        alert_message = "Upload a PDF study document or ask questions to enable automated performance analysis."
        alert_level = "info"
    else:
        alert_title = "🌟 High Mastery Across Topics!"
        alert_message = f"Great work! You are performing well in all {len(topics_list)} studied topics. Keep up your daily streak."
        alert_level = "success"

    return {
        "has_weakness": has_weakness,
        "primary_weakness": primary_weakness,
        "weak_areas": weak_areas,
        "strong_areas": strong_areas,
        "moderate_areas": moderate_areas,
        "total_topics_analyzed": len(topics_list),
        "alert": {
            "title": alert_title,
            "message": alert_message,
            "level": alert_level,
        }
    }


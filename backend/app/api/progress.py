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
        raw_title = quiz["title"] if quiz else "AI Quiz Attempt"
        clean_title = raw_title.replace("Quiz:", "").strip()
        short_title = clean_title if len(clean_title) <= 16 else clean_title[:14] + "…"
        res.append({
            "name": short_title,
            "full_name": raw_title,
            "score": round(a.get("percentage", 0), 1),
            "total": a.get("total_questions", 5),
            "date": a.get("attempted_at", "").split("T")[0] if a.get("attempted_at") else "Today",
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


import re

UUID_REGEX = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


CHAPTER_TITLES = {
    "math-10-1": "Arithmetic Sequences",
    "math-10-2": "Circles and Angles",
    "math-10-3": "Arithmetic Sequences & Algebra",
    "math-10-4": "Mathematics of Chance",
    "math-10-5": "Second Degree Equations",
    "math-10-6": "Trigonometry",
    "math-10-7": "Coordinates",
    "sslc-math": "Class 10 Mathematics",
    "phys-10-1": "Wave Motion & Oscillations",
    "phys-10-2": "Refraction of Light & Lenses",
    "phys-10-3": "Dispersion of Light & Colour",
    "phys-10-4": "Magnetic Effect of Electric Current",
    "sslc-physics": "Class 10 Physics",
    "chem-10-1": "Nomenclature of Organic Compounds & Isomerism",
    "chem-10-2": "Chemical Reactions of Organic Compounds",
    "chem-10-3": "Periodic Table & Electron Configuration",
    "chem-10-4": "Gas Laws and Mole Concept",
    "sslc-chemistry": "Class 10 Chemistry",
}


def _resolve_human_topic_name(tid: str, sessions: list, user_docs: list) -> str:
    if not tid:
        return "General Study Concepts"

    if tid in CHAPTER_TITLES:
        return CHAPTER_TITLES[tid]

    is_uuid = bool(UUID_REGEX.match(tid.strip()))

    if not is_uuid:
        clean = tid.replace("_", " ").replace("-", " ").strip()
        if clean and clean.lower() != "general":
            return clean.title()

    # Try resolving session title
    for s in sessions:
        if (s.get("id") == tid or s.get("topic_id") == tid) and s.get("title"):
            stitle = s["title"].strip()
            if stitle and not UUID_REGEX.match(stitle):
                return stitle.title()

    # Try resolving document title or key topic
    for d in user_docs:
        if d.get("topic_id") == tid or d.get("id") == tid:
            if d.get("key_topics") and isinstance(d["key_topics"], list) and len(d["key_topics"]) > 0:
                first_kt = d["key_topics"][0]
                if first_kt and not UUID_REGEX.match(first_kt):
                    return first_kt.title()
            if d.get("file_name"):
                fname = d["file_name"].rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
                if fname and not UUID_REGEX.match(fname):
                    return fname.title()

    return "General Study Concepts"


@router.get("/topics")
async def get_topic_progress(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    sessions = db.get_sessions_for_user(user_id)
    attempts = db.get_attempts_for_user(user_id)
    user_docs = db.get_documents_for_user(user_id)
    
    topics_map: Dict[str, dict] = {}

    for d in user_docs:
        tid = d.get("topic_id")
        if not tid:
            continue
        tname = _resolve_human_topic_name(tid, sessions, user_docs)
        if tid not in topics_map:
            topics_map[tid] = {
                "topic": tname,
                "topic_id": tid,
                "sessions_count": 0,
                "quizzes_taken": 0,
                "doc_count": 0,
                "scores": [],
            }
        topics_map[tid]["doc_count"] += 1
    
    for s in sessions:
        tid = s.get("topic_id") or s.get("id")
        if not tid:
            continue
        tname = _resolve_human_topic_name(tid, sessions, user_docs)
        if tid not in topics_map:
            topics_map[tid] = {
                "topic": tname,
                "topic_id": tid,
                "sessions_count": 0,
                "quizzes_taken": 0,
                "doc_count": 0,
                "scores": [],
            }
        topics_map[tid]["sessions_count"] += 1
        
    for a in attempts:
        quiz_id = a.get("quiz_id")
        quiz = db.get_quiz(quiz_id) if quiz_id else None
        tid = quiz["topic_id"] if quiz else None
        if not tid:
            continue
        tname = _resolve_human_topic_name(tid, sessions, user_docs)
        if tid not in topics_map:
            topics_map[tid] = {
                "topic": tname,
                "topic_id": tid,
                "sessions_count": 0,
                "quizzes_taken": 0,
                "doc_count": 0,
                "scores": [],
            }
        topics_map[tid]["quizzes_taken"] += 1
        topics_map[tid]["scores"].append(a["percentage"])
        
    result = []
    for tid, data in topics_map.items():
        scores = data["scores"]
        if scores:
            avg_s = round(sum(scores) / len(scores), 1)
        elif data["sessions_count"] > 0:
            avg_s = 65.0
        elif data.get("doc_count", 0) > 0:
            avg_s = 50.0
        else:
            avg_s = 0.0

        result.append({
            "subject": data["topic"],
            "topic": data["topic"],
            "topic_id": tid,
            "score": avg_s,
            "mastery": avg_s,
            "quizzes_taken": data["quizzes_taken"],
            "sessions_count": data["sessions_count"],
            "doc_count": data.get("doc_count", 0),
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


@router.get("/student-record")
async def get_student_record(user: dict = Depends(get_current_user)):
    """
    Comprehensive student performance monitoring endpoint:
    Returns full student profile, exam readiness rating, competency breakdowns,
    attempt-level logs with questions/answers review, and AI diagnostic reports.
    """
    return db.get_detailed_student_record(user["id"])



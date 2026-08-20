import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from app.core.config import get_settings
from app.core.models import Base, User, ChatSession, ChatMessage, Document, Quiz, QuizQuestion, QuizAttempt, Flashcard, StudyPlan, KnowledgeGraph, StudyNote

settings = get_settings()

# Initialize database engine (supports Cloud PostgreSQL & SQLite with automatic local fallback)
db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite://", "sqlite://")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

def _create_engine_with_fallback(primary_url: str):
    if primary_url.startswith("postgresql"):
        try:
            eng = create_engine(
                primary_url,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=30,
                pool_recycle=300,
                connect_args={"connect_timeout": 5},
            )
            # Test connection
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            return eng
        except Exception as e:
            print(f"[DATABASE] Warning: PostgreSQL unreachable ({e}). Falling back to local SQLite.")
            return create_engine("sqlite:///./deep_tutor.db", connect_args={"check_same_thread": False})
    else:
        return create_engine(primary_url, connect_args={"check_same_thread": False})

engine = _create_engine_with_fallback(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)

# Create tables automatically on startup
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[DATABASE] Base.metadata.create_all warning: {e}")

# Auto-migrate missing columns for existing SQLite database
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE documents ADD COLUMN key_topics TEXT DEFAULT '[]'"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_premium BOOLEAN DEFAULT 0"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'"))
        conn.commit()
    except Exception:
        pass


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


def new_id() -> str:
    return str(uuid.uuid4())



def now_iso() -> str:
    return datetime.utcnow().isoformat()


# ─── Context manager wrapper for db sessions ──────────────────────────────────
class DBContext:
    def __enter__(self):
        self.db = db_session()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.db.rollback()
        else:
            self.db.commit()
        db_session.remove()


# ─── User helpers ──────────────────────────────────────────────────────────────
def create_user(username: str, email: str, password_hash: str) -> dict:
    user_id = new_id()
    with DBContext() as db:
        user = User(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role="student",
            is_premium=False,
            plan="free",
            created_at=now_iso(),
        )
        db.add(user)
    return get_user_by_id(user_id)


def _user_dict(user) -> dict:
    is_prem = bool(getattr(user, "is_premium", False))
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role,
        "is_premium": is_prem,
        "plan": getattr(user, "plan", "free") or ("premium" if is_prem else "free"),
        "max_upload_size_mb": 100 if is_prem else 10,
        "created_at": user.created_at,
    }


def get_user_by_email(email: str) -> Optional[dict]:
    with DBContext() as db:
        user = db.query(User).filter(User.email == email).first()
        return _user_dict(user) if user else None


def get_user_by_username(username: str) -> Optional[dict]:
    with DBContext() as db:
        user = db.query(User).filter(User.username == username).first()
        return _user_dict(user) if user else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    with DBContext() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return _user_dict(user) if user else None


def update_user_tier(user_id: str, is_premium: bool) -> Optional[dict]:
    with DBContext() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_premium = is_premium
            user.plan = "premium" if is_premium else "free"
            db.commit()
    return get_user_by_id(user_id)


# ─── Session helpers ───────────────────────────────────────────────────────────
def create_session(user_id: str, topic_id: str, title: str) -> dict:
    sid = new_id()
    started = now_iso()
    with DBContext() as db:
        session = ChatSession(
            id=sid,
            user_id=user_id,
            topic_id=topic_id,
            session_title=title,
            started_at=started,
        )
        db.add(session)
    return {
        "id": sid,
        "user_id": user_id,
        "topic_id": topic_id,
        "session_title": title,
        "started_at": started,
        "ended_at": None,
    }


def get_sessions_for_user(user_id: str) -> List[dict]:
    with DBContext() as db:
        sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).all()
        return [
            {
                "id": s.id,
                "user_id": s.user_id,
                "topic_id": s.topic_id,
                "session_title": s.session_title,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in sessions
        ]


def get_session(session_id: str) -> Optional[dict]:
    with DBContext() as db:
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            return {
                "id": s.id,
                "user_id": s.user_id,
                "topic_id": s.topic_id,
                "session_title": s.session_title,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
    return None


def delete_session(session_id: str) -> bool:
    with DBContext() as db:
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            db.delete(s)
            return True
    return False


# ─── Message helpers ───────────────────────────────────────────────────────────
def add_message(session_id: str, role: str, content: str, metadata: dict = None) -> dict:
    msg_id = new_id()
    meta = metadata or {}
    created_at = now_iso()
    with DBContext() as db:
        msg = ChatMessage(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=created_at,
        )
        msg.meta = meta
        db.add(msg)
        db.commit()
    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "metadata": meta,
        "created_at": created_at,
    }


def get_messages(session_id: str, last_n: int = 20) -> List[dict]:
    with DBContext() as db:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        # return last_n items
        results = messages[-last_n:] if last_n > 0 else messages
        return [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "metadata": m.meta,
                "created_at": m.created_at,
            }
            for m in results
        ]


# ─── Document helpers ──────────────────────────────────────────────────────────
def create_document(user_id: str, topic_id: str, file_name: str, file_path: str, file_type: str) -> dict:
    doc_id = new_id()
    with DBContext() as db:
        doc = Document(
            id=doc_id,
            user_id=user_id,
            topic_id=topic_id,
            file_name=file_name,
            file_path=file_path,
            file_type=file_type,
            indexed=False,
            entity_count=0,
            chunk_count=0,
            created_at=now_iso(),
        )
        db.add(doc)
    
    with DBContext() as db:
        d = db.query(Document).filter(Document.id == doc_id).first()
        return {
            "id": d.id,
            "user_id": d.user_id,
            "topic_id": d.topic_id,
            "file_name": d.file_name,
            "file_path": d.file_path,
            "file_type": d.file_type,
            "indexed": d.indexed,
            "entity_count": d.entity_count,
            "chunk_count": d.chunk_count,
            "created_at": d.created_at,
        }


def get_documents_for_topic(topic_id: str) -> List[dict]:
    with DBContext() as db:
        docs = db.query(Document).filter(Document.topic_id == topic_id).all()
        return [
            {
                "id": d.id,
                "user_id": d.user_id,
                "topic_id": d.topic_id,
                "file_name": d.file_name,
                "file_path": d.file_path,
                "file_type": d.file_type,
                "indexed": d.indexed,
                "entity_count": d.entity_count,
                "chunk_count": d.chunk_count,
                "key_topics": getattr(d, "key_topics", []),
                "created_at": d.created_at,
            }
            for d in docs
        ]


def get_documents_for_user_and_topic(user_id: str, topic_id: str) -> List[dict]:
    with DBContext() as db:
        docs = (
            db.query(Document)
            .filter(Document.user_id == user_id)
            .filter(Document.topic_id == topic_id)
            .order_by(Document.created_at.desc())
            .all()
        )
        return [
            {
                "id": d.id,
                "user_id": d.user_id,
                "topic_id": d.topic_id,
                "file_name": d.file_name,
                "file_path": d.file_path,
                "file_type": d.file_type,
                "indexed": d.indexed,
                "entity_count": d.entity_count,
                "chunk_count": d.chunk_count,
                "key_topics": getattr(d, "key_topics", []),
                "created_at": d.created_at,
            }
            for d in docs
        ]


def get_documents_for_user(user_id: str) -> List[dict]:
    with DBContext() as db:
        docs = db.query(Document).filter(Document.user_id == user_id).order_by(Document.created_at.desc()).all()
        return [
            {
                "id": d.id,
                "user_id": d.user_id,
                "topic_id": d.topic_id,
                "file_name": d.file_name,
                "file_path": d.file_path,
                "file_type": d.file_type,
                "indexed": d.indexed,
                "entity_count": d.entity_count,
                "chunk_count": d.chunk_count,
                "key_topics": getattr(d, "key_topics", []),
                "created_at": d.created_at,
            }
            for d in docs
        ]


def update_document_stats(doc_id: str, indexed: bool, entity_count: int, chunk_count: int, key_topics: list = None) -> bool:
    with DBContext() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.indexed = indexed
            doc.entity_count = entity_count
            doc.chunk_count = chunk_count
            if key_topics is not None:
                doc.key_topics = key_topics
            return True
    return False


def delete_document(doc_id: str, user_id: str) -> Optional[dict]:
    with DBContext() as db:
        doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user_id).first()
        if not doc:
            return None
        doc_dict = {
            "id": doc.id,
            "user_id": doc.user_id,
            "topic_id": doc.topic_id,
            "file_name": doc.file_name,
            "file_path": doc.file_path,
        }
        db.delete(doc)
        return doc_dict


def delete_documents_for_section(user_id: str, topic_id: str) -> List[dict]:
    targets = {topic_id, topic_id.lower(), topic_id.upper(), topic_id.strip()}
    with DBContext() as db:
        docs = db.query(Document).filter(Document.user_id == user_id, Document.topic_id.in_(targets)).all()
        doc_dicts = [
            {
                "id": d.id,
                "user_id": d.user_id,
                "topic_id": d.topic_id,
                "file_name": d.file_name,
                "file_path": d.file_path,
            }
            for d in docs
        ]
        for d in docs:
            db.delete(d)
        return doc_dicts


def delete_section_all_data(user_id: str, topic_id: str) -> dict:
    """
    Comprehensively delete all database records for a section/topic:
    - Documents
    - Flashcards
    - Quizzes, QuizQuestions, QuizAttempts
    - StudyPlans
    - ChatSessions & ChatMessages
    """
    targets = {topic_id, topic_id.lower(), topic_id.upper(), topic_id.strip()}
    with DBContext() as db:
        # 1. Documents
        docs = db.query(Document).filter(
            Document.user_id == user_id,
            Document.topic_id.in_(targets)
        ).all()
        deleted_docs = [
            {"id": d.id, "file_name": d.file_name, "file_path": d.file_path, "topic_id": d.topic_id}
            for d in docs
        ]
        for d in docs:
            db.delete(d)

        # 2. Flashcards
        deleted_flashcards = db.query(Flashcard).filter(
            Flashcard.topic_id.in_(targets)
        ).delete(synchronize_session=False)

        # 3. Quizzes & Questions & Attempts
        quizzes = db.query(Quiz).filter(
            Quiz.topic_id.in_(targets)
        ).all()
        quiz_ids = [q.id for q in quizzes]
        if quiz_ids:
            db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            for q in quizzes:
                db.delete(q)

        # 4. Study Plans
        deleted_plans = db.query(StudyPlan).filter(
            StudyPlan.user_id == user_id,
            StudyPlan.topic_id.in_(targets)
        ).delete(synchronize_session=False)

        # 5. Chat Sessions & Messages (cascade deletes messages)
        sessions = db.query(ChatSession).filter(
            ChatSession.user_id == user_id,
            (ChatSession.topic_id.in_(targets) | ChatSession.id.in_(targets))
        ).all()
        session_ids = [s.id for s in sessions]
        if session_ids:
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            for s in sessions:
                db.delete(s)

        # 6. Cloud Knowledge Graphs (Neon PostgreSQL)
        db.query(KnowledgeGraph).filter(
            KnowledgeGraph.topic_id.in_(targets)
        ).delete(synchronize_session=False)

        return {
            "deleted_docs": deleted_docs,
            "deleted_flashcards_count": deleted_flashcards,
            "deleted_quizzes_count": len(quizzes),
            "deleted_plans_count": deleted_plans,
            "deleted_sessions_count": len(sessions),
        }



def get_key_topics_for_user_section(user_id: str, topic_id: str) -> List[str]:
    with DBContext() as db:
        query = db.query(Document).filter(Document.user_id == user_id)
        if topic_id and topic_id != "general":
            query = query.filter(Document.topic_id == topic_id)
        docs = query.all()
        extracted = []
        for d in docs:
            for t in getattr(d, "key_topics", []):
                if t and t not in extracted:
                    extracted.append(t)
        return extracted


# ─── Quiz helpers ──────────────────────────────────────────────────────────────
def create_quiz(topic_id: str, title: str, difficulty: str = "medium", time_limit: int = 10) -> dict:
    quiz_id = new_id()
    with DBContext() as db:
        quiz = Quiz(
            id=quiz_id,
            topic_id=topic_id,
            title=title,
            difficulty=difficulty,
            time_limit_mins=time_limit,
            created_at=now_iso(),
        )
        db.add(quiz)
    return {
        "id": quiz_id,
        "topic_id": topic_id,
        "title": title,
        "difficulty": difficulty,
        "time_limit_mins": time_limit,
        "created_at": quiz["created_at"] if isinstance(quiz, dict) else now_iso(),
    }


def add_question(quiz_id: str, question_text: str, question_type: str, options: List[str], correct_answer: str, explanation: str) -> dict:
    q_id = new_id()
    with DBContext() as db:
        question = QuizQuestion(
            id=q_id,
            quiz_id=quiz_id,
            question_text=question_text,
            question_type=question_type,
            correct_answer=correct_answer,
            explanation=explanation,
        )
        question.options = options
        db.add(question)
    return {
        "id": q_id,
        "quiz_id": quiz_id,
        "question_text": question_text,
        "question_type": question_type,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
    }


def get_quizzes_by_topic(topic_id: str) -> List[dict]:
    with DBContext() as db:
        quizzes = db.query(Quiz).filter(Quiz.topic_id == topic_id).all()
        return [
            {
                "id": q.id,
                "topic_id": q.topic_id,
                "title": q.title,
                "difficulty": q.difficulty,
                "time_limit_mins": q.time_limit_mins,
                "created_at": q.created_at,
            }
            for q in quizzes
        ]


def get_quiz(quiz_id: str) -> Optional[dict]:
    with DBContext() as db:
        q = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if q:
            questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz_id).all()
            return {
                "id": q.id,
                "topic_id": q.topic_id,
                "title": q.title,
                "difficulty": q.difficulty,
                "time_limit_mins": q.time_limit_mins,
                "created_at": q.created_at,
                "questions": [
                    {
                        "id": qu.id,
                        "quiz_id": qu.quiz_id,
                        "question_text": qu.question_text,
                        "question_type": qu.question_type,
                        "options": qu.options,
                        "correct_answer": qu.correct_answer,
                        "explanation": qu.explanation,
                    }
                    for qu in questions
                ]
            }
    return None


def create_attempt(user_id: str, quiz_id: str, score: int, total: int, percentage: float, answers: dict) -> dict:
    attempt_id = new_id()
    with DBContext() as db:
        attempt = QuizAttempt(
            id=attempt_id,
            user_id=user_id,
            quiz_id=quiz_id,
            score=score,
            total_questions=total,
            percentage=percentage,
            attempted_at=now_iso(),
        )
        attempt.answers = answers
        db.add(attempt)
    return {
        "id": attempt_id,
        "user_id": user_id,
        "quiz_id": quiz_id,
        "score": score,
        "total_questions": total,
        "percentage": percentage,
        "answers": answers,
        "attempted_at": now_iso(),
    }


def get_attempts_for_user(user_id: str) -> List[dict]:
    with DBContext() as db:
        attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id).all()
        return [
            {
                "id": a.id,
                "user_id": a.user_id,
                "quiz_id": a.quiz_id,
                "score": a.score,
                "total_questions": a.total_questions,
                "percentage": a.percentage,
                "answers": a.answers,
                "attempted_at": a.attempted_at,
            }
            for a in attempts
        ]


def get_attempts_for_quiz(quiz_id: str) -> List[dict]:
    with DBContext() as db:
        attempts = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz_id).all()
        return [
            {
                "id": a.id,
                "user_id": a.user_id,
                "quiz_id": a.quiz_id,
                "score": a.score,
                "total_questions": a.total_questions,
                "percentage": a.percentage,
                "answers": a.answers,
                "attempted_at": a.attempted_at,
            }
            for a in attempts
        ]


# ─── Flashcard helpers ──────────────────────────────────────────────────────────
def add_flashcard(topic_id: str, front: str, back: str) -> dict:
    fc_id = new_id()
    with DBContext() as db:
        card = Flashcard(
            id=fc_id,
            topic_id=topic_id,
            front=front,
            back=back,
            mastered=False,
            created_at=now_iso(),
        )
        db.add(card)
    return {
        "id": fc_id,
        "topic_id": topic_id,
        "front": front,
        "back": back,
        "mastered": False,
        "created_at": now_iso(),
    }


def get_flashcards_by_topic(topic_id: str) -> List[dict]:
    with DBContext() as db:
        cards = db.query(Flashcard).filter(Flashcard.topic_id == topic_id).all()
        return [
            {
                "id": c.id,
                "topic_id": c.topic_id,
                "front": c.front,
                "back": c.back,
                "mastered": c.mastered,
                "created_at": c.created_at,
            }
            for c in cards
        ]


def update_flashcard_status(topic_id: str, card_id: str, mastered: bool) -> bool:
    with DBContext() as db:
        card = db.query(Flashcard).filter(Flashcard.topic_id == topic_id, Flashcard.id == card_id).first()
        if card:
            card.mastered = mastered
            return True
    return False


def delete_flashcards_for_topic(topic_id: str) -> bool:
    with DBContext() as db:
        db.query(Flashcard).filter(Flashcard.topic_id == topic_id).delete()
        return True


# ─── Study Plan helpers ─────────────────────────────────────────────────────────
def create_study_plan(user_id: str, topic_id: str, title: str, target_date: str, total_days: int, hours_per_day: float, schedule: list) -> dict:
    plan_id = new_id()
    with DBContext() as db:
        plan = StudyPlan(
            id=plan_id,
            user_id=user_id,
            topic_id=topic_id,
            title=title,
            target_date=target_date,
            total_days=total_days,
            hours_per_day=hours_per_day,
            created_at=now_iso(),
        )
        plan.schedule = schedule
        plan.completed_days = []
        db.add(plan)
    return get_study_plan(plan_id)


def get_study_plans_for_user(user_id: str) -> List[dict]:
    with DBContext() as db:
        plans = db.query(StudyPlan).filter(StudyPlan.user_id == user_id).order_by(StudyPlan.created_at.desc()).all()
        return [
            {
                "id": p.id,
                "user_id": p.user_id,
                "topic_id": p.topic_id,
                "title": p.title,
                "target_date": p.target_date,
                "total_days": p.total_days,
                "hours_per_day": p.hours_per_day,
                "schedule": p.schedule,
                "completed_days": p.completed_days,
                "created_at": p.created_at,
            }
            for p in plans
        ]


def get_study_plan(plan_id: str) -> Optional[dict]:
    with DBContext() as db:
        p = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
        if p:
            return {
                "id": p.id,
                "user_id": p.user_id,
                "topic_id": p.topic_id,
                "title": p.title,
                "target_date": p.target_date,
                "total_days": p.total_days,
                "hours_per_day": p.hours_per_day,
                "schedule": p.schedule,
                "completed_days": p.completed_days,
                "created_at": p.created_at,
            }
    return None


def toggle_study_plan_day(plan_id: str, day_number: int) -> Optional[dict]:
    with DBContext() as db:
        p = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
        if p:
            current = list(p.completed_days)
            if day_number in current:
                current.remove(day_number)
            else:
                current.append(day_number)
            p.completed_days = current
    return get_study_plan(plan_id)


def save_study_plan_day_notes(plan_id: str, day_number: int, notes: str) -> Optional[dict]:
    """
    Persists AI study notes for a specific day directly via the app's own DB session.
    Uses a raw SQL UPDATE through SessionLocal to guarantee the write is committed
    on the correct connection without ORM property-tracking issues.
    """
    import sys
    session = SessionLocal()
    try:
        # 1. Read current schedule
        row = session.execute(
            text("SELECT schedule FROM study_plans WHERE id = :pid"),
            {"pid": plan_id}
        ).fetchone()

        if not row:
            print(f"[DB] save_study_plan_day_notes: plan {plan_id} not found", flush=True)
            return None

        try:
            sched = json.loads(row[0] or "[]")
        except Exception:
            sched = []

        # 2. Inject the notes into the matching day
        updated = False
        for item in sched:
            if item.get("day") == day_number:
                item["study_notes"] = notes
                updated = True
                break

        if not updated:
            print(f"[DB] save_study_plan_day_notes: day {day_number} not found in plan {plan_id}. Days: {[i.get('day') for i in sched]}", flush=True)
            return get_study_plan(plan_id)

        # 3. Commit the updated JSON back with a raw UPDATE
        new_sched_json = json.dumps(sched)
        result = session.execute(
            text("UPDATE study_plans SET schedule = :sched WHERE id = :pid"),
            {"sched": new_sched_json, "pid": plan_id}
        )
        session.commit()
        print(f"[DB] Saved study notes: plan={plan_id} day={day_number} len={len(notes)} rows={result.rowcount}", file=sys.stdout, flush=True)

    except Exception as e:
        session.rollback()
        import traceback
        print(f"[DB] save_study_plan_day_notes ERROR: {e}", flush=True)
        traceback.print_exc()
    finally:
        session.close()

    return get_study_plan(plan_id)


def delete_study_plan(plan_id: str) -> bool:
    with DBContext() as db:
        p = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
        if p:
            db.delete(p)
            return True
    return False


# ─── Leaderboard Helper ────────────────────────────────────────────────────────
def get_leaderboard_rankings(current_user_id: str) -> dict:
    with DBContext() as db:
        users = db.query(User).all()
        rankings = []

        for user in users:
            attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id).all()
            docs = db.query(Document).filter(Document.user_id == user.id).all()

            quizzes_taken = len(attempts)
            total_correct = sum(a.score for a in attempts)
            total_questions = sum(a.total_questions for a in attempts)
            avg_accuracy = round((total_correct / total_questions * 100), 1) if total_questions > 0 else 0.0
            docs_count = len(docs)

            # Calculate XP points
            total_xp = (total_correct * 100) + (quizzes_taken * 50) + (docs_count * 30)

            # Assign badges
            badges = []
            if total_xp >= 1000:
                badges.append("Grandmaster")
            elif total_xp >= 500:
                badges.append("Scholar")
            elif total_xp >= 200:
                badges.append("Apprentice")
            
            if quizzes_taken >= 5:
                badges.append("Quiz Whiz")
            if docs_count >= 2:
                badges.append("PDF Pioneer")

            rankings.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "total_xp": total_xp,
                "quizzes_taken": quizzes_taken,
                "avg_accuracy": avg_accuracy,
                "docs_uploaded": docs_count,
                "badges": badges,
                "is_current_user": (user.id == current_user_id)
            })

        # Sort by XP descending
        rankings.sort(key=lambda x: (x["total_xp"], x["avg_accuracy"]), reverse=True)

        # Assign rank numbers
        for idx, item in enumerate(rankings):
            item["rank"] = idx + 1

        top_3 = rankings[:3]
        user_rank_info = next((r for r in rankings if r["user_id"] == current_user_id), None)

        return {
            "rankings": rankings,
            "top_3": top_3,
            "current_user_rank": user_rank_info
        }


# ─── Cloud Knowledge Graph helpers ─────────────────────────────────────────────
def get_knowledge_graph(topic_id: str) -> Optional[dict]:
    with DBContext() as db:
        g = db.query(KnowledgeGraph).filter(KnowledgeGraph.topic_id == topic_id).first()
        if not g:
            return None
        return {
            "topic_id": g.topic_id,
            "user_id": g.user_id,
            "entities": g.entities,
            "relations": g.relations,
            "triplets": g.triplets,
            "updated_at": g.updated_at,
        }


def save_knowledge_graph(topic_id: str, entities: dict, relations: dict, triplets: list, user_id: Optional[str] = None) -> dict:
    with DBContext() as db:
        g = db.query(KnowledgeGraph).filter(KnowledgeGraph.topic_id == topic_id).first()
        if not g:
            g = KnowledgeGraph(
                topic_id=topic_id,
                user_id=user_id,
                updated_at=now_iso(),
            )
            g.entities = entities
            g.relations = relations
            g.triplets = triplets
            db.add(g)
        else:
            g.entities = entities
            g.relations = relations
            g.triplets = triplets
            g.updated_at = now_iso()
            if user_id:
                g.user_id = user_id
    return get_knowledge_graph(topic_id) or {"entities": entities, "relations": relations, "triplets": triplets}


def delete_knowledge_graph(topic_id: str):
    with DBContext() as db:
        db.query(KnowledgeGraph).filter(KnowledgeGraph.topic_id == topic_id).delete()


# ─── Study Notes & PYQ Helpers ────────────────────────────────────────────────
def _note_dict(n: StudyNote) -> dict:
    if not n:
        return {}
    return {
        "id": n.id,
        "user_id": n.user_id,
        "title": n.title,
        "topic_id": n.topic_id,
        "subject": n.subject,
        "note_type": n.note_type,
        "material_doc_name": n.material_doc_name,
        "pyq_doc_names": n.pyq_doc_names,
        "content_markdown": n.content_markdown,
        "high_yield_topics": n.high_yield_topics,
        "pyq_patterns": n.pyq_patterns,
        "key_formulas": n.key_formulas,
        "exam_tips": n.exam_tips,
        "solved_questions": n.solved_questions,
        "created_at": n.created_at,
    }


def create_study_note(
    user_id: str,
    title: str,
    topic_id: str,
    subject: str,
    note_type: str,
    material_doc_name: str,
    pyq_doc_names: list,
    content_markdown: str,
    high_yield_topics: list = None,
    pyq_patterns: list = None,
    key_formulas: list = None,
    exam_tips: list = None,
    solved_questions: list = None,
) -> dict:
    note_id = new_id()
    created_at = now_iso()
    with DBContext() as db:
        note = StudyNote(
            id=note_id,
            user_id=user_id,
            title=title,
            topic_id=topic_id or "general",
            subject=subject or "General",
            note_type=note_type or "high_yield_master",
            material_doc_name=material_doc_name,
            content_markdown=content_markdown,
            created_at=created_at,
        )
        note.pyq_doc_names = pyq_doc_names or []
        note.high_yield_topics = high_yield_topics or []
        note.pyq_patterns = pyq_patterns or []
        note.key_formulas = key_formulas or []
        note.exam_tips = exam_tips or []
        note.solved_questions = solved_questions or []
        db.add(note)
        db.commit()
    return get_study_note_by_id(note_id)


def get_study_notes_for_user(user_id: str) -> List[dict]:
    with DBContext() as db:
        notes = (
            db.query(StudyNote)
            .filter(StudyNote.user_id == user_id)
            .order_by(StudyNote.created_at.desc())
            .all()
        )
        return [_note_dict(n) for n in notes]


def get_study_note_by_id(note_id: str) -> Optional[dict]:
    with DBContext() as db:
        note = db.query(StudyNote).filter(StudyNote.id == note_id).first()
        return _note_dict(note) if note else None


def delete_study_note(note_id: str, user_id: str) -> bool:
    with DBContext() as db:
        note = db.query(StudyNote).filter(StudyNote.id == note_id, StudyNote.user_id == user_id).first()
        if note:
            db.delete(note)
            db.commit()
            return True
    return False


# ─── Comprehensive Student Performance Record Aggregator ──────────────────────
def get_detailed_student_record(user_id: str) -> dict:
    """
    Builds an end-to-end 360-degree performance record for monitoring student progress,
    including full attempts log with question reviews, subject competency radar,
    activity timeline, exam readiness score, and AI diagnostic summary.
    """
    with DBContext() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}

        sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).all()
        attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id).order_by(QuizAttempt.attempted_at.desc()).all()
        docs = db.query(Document).filter(Document.user_id == user_id).all()
        plans = db.query(StudyPlan).filter(StudyPlan.user_id == user_id).all()
        notes = db.query(StudyNote).filter(StudyNote.user_id == user_id).order_by(StudyNote.created_at.desc()).all()

        # Unique topic IDs
        topic_ids = set()
        for s in sessions:
            if s.topic_id:
                topic_ids.add(s.topic_id)
        for d in docs:
            if d.topic_id:
                topic_ids.add(d.topic_id)

        # Flashcards count & mastered
        flashcards_mastered = 0
        total_flashcards_in_topics = 0
        for tid in list(topic_ids) + ["general", "sslc-math", "sslc-physics", "sslc-chemistry"]:
            cards = db.query(Flashcard).filter(Flashcard.topic_id == tid).all()
            total_flashcards_in_topics += len(cards)
            flashcards_mastered += len([c for c in cards if c.mastered])

        # Study plans completion
        completed_plan_days = sum(len(p.completed_days or []) for p in plans)

        # Quiz attempts with detailed question breakdowns
        detailed_attempts = []
        quiz_ids = list(set([a.quiz_id for a in attempts]))
        quizzes_map = {}
        if quiz_ids:
            quiz_records = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
            for q in quiz_records:
                questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == q.id).all()
                quizzes_map[q.id] = {
                    "quiz": q,
                    "questions": [
                        {
                            "id": qu.id,
                            "question_text": qu.question_text,
                            "question_type": qu.question_type,
                            "options": qu.options,
                            "correct_answer": qu.correct_answer,
                            "explanation": qu.explanation,
                        }
                        for qu in questions
                    ]
                }

        for a in attempts:
            q_info = quizzes_map.get(a.quiz_id)
            quiz_obj = q_info["quiz"] if q_info else None
            q_list = q_info["questions"] if q_info else []
            answers_dict = a.answers or {}

            # Build review array
            reviewed_questions = []
            for qu in q_list:
                user_ans = answers_dict.get(qu["id"], "")
                is_correct = (user_ans == qu["correct_answer"])
                reviewed_questions.append({
                    "id": qu["id"],
                    "question_text": qu["question_text"],
                    "options": qu["options"],
                    "user_answer": user_ans,
                    "correct_answer": qu["correct_answer"],
                    "is_correct": is_correct,
                    "explanation": qu["explanation"],
                })

            detailed_attempts.append({
                "id": a.id,
                "quiz_id": a.quiz_id,
                "quiz_title": quiz_obj.title if quiz_obj else "AI Practice Quiz",
                "topic_id": quiz_obj.topic_id if quiz_obj else "general",
                "difficulty": quiz_obj.difficulty if quiz_obj else "medium",
                "score": a.score,
                "total_questions": a.total_questions,
                "percentage": round(a.percentage, 1),
                "attempted_at": a.attempted_at,
                "answers": answers_dict,
                "questions_review": reviewed_questions,
            })

        # Activity dates & streak
        activity_dates = set()
        for s in sessions:
            if s.started_at:
                try:
                    activity_dates.add(s.started_at.split("T")[0])
                except Exception:
                    pass
        for a in attempts:
            if a.attempted_at:
                try:
                    activity_dates.add(a.attempted_at.split("T")[0])
                except Exception:
                    pass
        for n in notes:
            if n.created_at:
                try:
                    activity_dates.add(n.created_at.split("T")[0])
                except Exception:
                    pass

        today = datetime.utcnow().date()
        streak_days = 0
        check_date = today
        while check_date.strftime("%Y-%m-%d") in activity_dates:
            streak_days += 1
            check_date -= timedelta(days=1)
        if streak_days == 0 and (len(sessions) > 0 or len(attempts) > 0 or flashcards_mastered > 0 or len(notes) > 0):
            streak_days = 1

        # Calculate XP & Scholar Level
        session_xp = len(sessions) * 50
        quiz_xp = sum(100 + int(a.percentage * 2) for a in attempts)
        flashcard_xp = flashcards_mastered * 30
        plan_xp = completed_plan_days * 40
        notes_xp = len(notes) * 75
        streak_xp = streak_days * 50

        total_xp = session_xp + quiz_xp + flashcard_xp + plan_xp + notes_xp + streak_xp
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

        # Calculate average quiz accuracy
        avg_score = round(sum(a.percentage for a in attempts) / len(attempts), 1) if attempts else 0.0

        # Exam Readiness Score calculation (0 - 100%)
        # Weighted factors: Quiz accuracy (45%), Study consistency/streak (20%), Coverage/Sessions (20%), Flashcard mastery (15%)
        quiz_factor = min(100.0, avg_score) * 0.45 if attempts else 20.0
        streak_factor = min(100.0, streak_days * 15.0) * 0.20
        coverage_factor = min(100.0, (len(sessions) * 10.0) + (len(docs) * 15.0) + (len(notes) * 20.0)) * 0.20
        flashcard_factor = (min(100.0, (flashcards_mastered / max(1, total_flashcards_in_topics)) * 100.0) if total_flashcards_in_topics > 0 else (min(100.0, flashcards_mastered * 20.0))) * 0.15

        exam_readiness = round(quiz_factor + streak_factor + coverage_factor + flashcard_factor, 1)
        exam_readiness = max(10.0, min(99.0, exam_readiness))

        if exam_readiness >= 85:
            readiness_label = "High Exam Readiness"
            readiness_status = "Excellent"
        elif exam_readiness >= 70:
            readiness_label = "Solid Exam Preparation"
            readiness_status = "Good"
        elif exam_readiness >= 50:
            readiness_label = "Developing Foundation"
            readiness_status = "Moderate"
        else:
            readiness_label = "Needs Systematic Revision"
            readiness_status = "Action Required"

        # Subject Competency Breakdown
        subject_map = {
            "Mathematics": {"scores": [], "sessions": 0, "quizzes": 0, "notes": 0},
            "Physics": {"scores": [], "sessions": 0, "quizzes": 0, "notes": 0},
            "Chemistry": {"scores": [], "sessions": 0, "quizzes": 0, "notes": 0},
            "Custom Materials": {"scores": [], "sessions": 0, "quizzes": 0, "notes": 0},
        }

        for s in sessions:
            t = (s.topic_id or "").lower()
            if "math" in t:
                subject_map["Mathematics"]["sessions"] += 1
            elif "phys" in t:
                subject_map["Physics"]["sessions"] += 1
            elif "chem" in t:
                subject_map["Chemistry"]["sessions"] += 1
            else:
                subject_map["Custom Materials"]["sessions"] += 1

        for a in attempts:
            q_info = quizzes_map.get(a.quiz_id)
            t = (q_info["quiz"].topic_id if q_info and q_info["quiz"] else "").lower()
            if "math" in t:
                subject_map["Mathematics"]["quizzes"] += 1
                subject_map["Mathematics"]["scores"].append(a.percentage)
            elif "phys" in t:
                subject_map["Physics"]["quizzes"] += 1
                subject_map["Physics"]["scores"].append(a.percentage)
            elif "chem" in t:
                subject_map["Chemistry"]["quizzes"] += 1
                subject_map["Chemistry"]["scores"].append(a.percentage)
            else:
                subject_map["Custom Materials"]["quizzes"] += 1
                subject_map["Custom Materials"]["scores"].append(a.percentage)

        for n in notes:
            sub = (n.subject or "").lower()
            if "math" in sub:
                subject_map["Mathematics"]["notes"] += 1
            elif "phys" in sub:
                subject_map["Physics"]["notes"] += 1
            elif "chem" in sub:
                subject_map["Chemistry"]["notes"] += 1
            else:
                subject_map["Custom Materials"]["notes"] += 1

        subject_competencies = []
        for sub_name, data in subject_map.items():
            if data["scores"]:
                sub_score = round(sum(data["scores"]) / len(data["scores"]), 1)
            elif data["sessions"] > 0 or data["notes"] > 0:
                sub_score = 70.0
            else:
                sub_score = 0.0

            subject_competencies.append({
                "subject": sub_name,
                "score": sub_score,
                "quizzes_taken": data["quizzes"],
                "sessions_count": data["sessions"],
                "notes_count": data["notes"],
            })

        # Detailed sessions summary
        sessions_summary = []
        for s in sessions[:15]:
            msg_count = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).count()
            sessions_summary.append({
                "id": s.id,
                "title": s.session_title or "AI Learning Session",
                "topic_id": s.topic_id or "general",
                "started_at": s.started_at,
                "messages_count": msg_count,
            })

        # AI Diagnostic Remarks
        weak_subjects = [sc["subject"] for sc in subject_competencies if sc["score"] > 0 and sc["score"] < 70]
        strong_subjects = [sc["subject"] for sc in subject_competencies if sc["score"] >= 75]

        if not attempts and not sessions:
            diagnostic_summary = "Student has newly joined DeepTutor. Start by chatting with an AI Tutor or uploading a chapter PDF with Previous Year Questions (PYQs) to establish performance benchmarks."
            recommended_action = "Upload your study material and take your first 5-question diagnostic quiz."
        elif weak_subjects:
            diagnostic_summary = f"Student shows good engagement with {len(sessions)} study sessions. Special reinforcement needed in {', '.join(weak_subjects)} where accuracy is below 70%."
            recommended_action = f"Generate a high-yield Smart Note on {weak_subjects[0]} and practice 10 targeted PYQ questions."
        else:
            strong_str = ', '.join(strong_subjects) if strong_subjects else "General Curriculum"
            diagnostic_summary = f"Strong conceptual foundation demonstrated across {strong_str}. Accuracy is steady at {avg_score}% with active {streak_days}-day streak."
            recommended_action = "Continue regular timed quizzes and review 5 flashcards daily to maintain peak recall."

        return {
            "student": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_premium": getattr(user, "is_premium", False),
                "plan": getattr(user, "plan", "free"),
                "member_since": user.created_at,
            },
            "scholar_rank": {
                "level": level,
                "level_title": level_title,
                "total_xp": total_xp,
                "xp_in_level": xp_in_level,
                "xp_for_next": xp_for_next,
                "streak_days": streak_days,
            },
            "metrics": {
                "avg_quiz_score": avg_score,
                "total_quizzes_taken": len(attempts),
                "total_sessions": len(sessions),
                "flashcards_mastered": flashcards_mastered,
                "total_flashcards": total_flashcards_in_topics,
                "study_plans_completed_days": completed_plan_days,
                "notes_generated": len(notes),
                "documents_uploaded": len(docs),
                "exam_readiness_score": exam_readiness,
                "readiness_label": readiness_label,
                "readiness_status": readiness_status,
            },
            "subject_competencies": subject_competencies,
            "quiz_attempts": detailed_attempts,
            "recent_sessions": sessions_summary,
            "saved_notes": [_note_dict(n) for n in notes[:10]],
            "diagnostic": {
                "summary": diagnostic_summary,
                "recommended_action": recommended_action,
                "weak_subjects": weak_subjects,
                "strong_subjects": strong_subjects,
                "last_evaluated": now_iso(),
            }
        }




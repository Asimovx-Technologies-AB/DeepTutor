from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.session import StudySession, ChatMessage, StudentProfile, StudentMastery
from app.models.document import Document


class ContextIntegrator:
    """
    Stage 2: Context Integration.
    Consolidates:
    - Previous Conversation turns
    - Active Document Metadata
    - Current Lesson / Topic
    - Student Knowledge Profile & Concept Mastery
    """

    @classmethod
    def assemble_context(
        cls,
        session: Session,
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        topic_id: Optional[str] = None,
        max_history_turns: int = 50
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "document_id": None,
            "document_title": None,
            "current_topic": None,
            "history": [],
            "student_profile": {"difficulty": "Intermediate", "goals": ["Understanding"]},
            "mastery_scores": {},
        }

        # 1. Fetch Session & Document Context
        if session_id:
            study_sess = session.query(StudySession).filter(StudySession.id == session_id).first()
            if study_sess:
                context["document_id"] = study_sess.document_id
                context["document_title"] = study_sess.title or study_sess.document_name
                
                # Fetch recent messages
                recent_msgs = (
                    session.query(ChatMessage)
                    .filter(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(max_history_turns)
                    .all()
                )
                # Reverse to chronological order
                for msg in reversed(recent_msgs):
                    context["history"].append({
                        "role": msg.role,
                        "content": msg.content,
                        "intent": msg.intent
                    })

        # Only fall back to ambient document if no session_id was provided (isolated workspaces preserve independence)
        if not session_id and not context["document_id"]:
            latest_doc = session.query(Document).filter(Document.status == "INDEXED").order_by(Document.created_at.desc()).first()
            if latest_doc:
                context["document_id"] = latest_doc.id
                context["document_title"] = latest_doc.title or latest_doc.filename

        # Sanitize document title if it contains path separators or source extensions
        doc_title = context.get("document_title")
        if doc_title and ("\\" in doc_title or "/" in doc_title or any(doc_title.lower().endswith(ext) for ext in [".pmd", ".pdf", ".indd", ".doc", ".docx"])):
            from pathlib import Path
            stem = Path(doc_title).stem
            context["document_title"] = stem.replace("-", " ").replace("_", " ").title() if stem else "Subject Document"

        # 2. Fetch Student Profile & Mastery
        profile = session.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        if profile:
            context["student_profile"] = {
                "difficulty": profile.preferred_difficulty,
                "goals": profile.learning_goals or ["Understanding"],
            }

        mastery_rows = session.query(StudentMastery).filter(StudentMastery.user_id == user_id).all()
        for m in mastery_rows:
            context["mastery_scores"][m.concept] = m.mastery_score

        return context

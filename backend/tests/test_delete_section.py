import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import (
    DBContext, create_user, create_session, add_message,
    create_document, create_quiz, add_question, add_flashcard, create_study_plan,
    get_session, get_messages, get_documents_for_user_and_topic,
    get_quizzes_by_topic, get_flashcards_by_topic, get_study_plans_for_user
)
import pytest
from app.api.chat import delete_session

@pytest.mark.asyncio
async def test_section_deletion():
    print("1. Creating test user and section/session data...")
    user = create_user("testuser_del", f"testdel_{int(asyncio.get_event_loop().time())}@test.com", "testpass123")
    user_id = user["id"]
    
    session = create_session(user_id=user_id, topic_id="", title="Machine Learning Section")
    session_id = session["id"]
    
    # Add messages
    add_message(session_id, "user", "What is gradient descent?")
    add_message(session_id, "assistant", "Gradient descent is an optimization algorithm...")
    
    # Add document linked to this session
    doc = create_document(user_id=user_id, topic_id=session_id, file_name="ml_notes.pdf", file_path="./uploads/fake.pdf", file_type="pdf")
    
    # Add flashcards
    add_flashcard(topic_id=session_id, front="Gradient Descent", back="Optimization method")
    
    # Add quiz
    quiz = create_quiz(topic_id=session_id, title="ML Quiz")
    add_question(quiz["id"], "What is LR?", "mcq", ["A", "B"], "A", "Learning Rate")
    
    # Add study plan
    create_study_plan(user_id=user_id, topic_id=session_id, title="ML 7-Day Plan", target_date="2026-09-01", total_days=7, hours_per_day=2.0, schedule=[])
    
    print("   Data inserted successfully.")
    
    # Verify records exist before deletion
    assert get_session(session_id) is not None, "Session should exist"
    assert len(get_messages(session_id)) == 2, "Messages should exist"
    assert len(get_documents_for_user_and_topic(user_id, session_id)) == 1, "Document should exist"
    assert len(get_flashcards_by_topic(session_id)) == 1, "Flashcards should exist"
    assert len(get_quizzes_by_topic(session_id)) == 1, "Quiz should exist"
    
    print("2. Calling delete_session endpoint handler...")
    res = await delete_session(session_id=session_id, user=user)
    print(f"   Delete response: {res}")
    
    print("3. Verifying all records are completely removed from database...")
    assert get_session(session_id) is None, "Session must be deleted from DB"
    assert len(get_messages(session_id)) == 0, "Messages must be deleted from DB"
    assert len(get_documents_for_user_and_topic(user_id, session_id)) == 0, "Documents must be deleted from DB"
    assert len(get_flashcards_by_topic(session_id)) == 0, "Flashcards must be deleted from DB"
    assert len(get_quizzes_by_topic(session_id)) == 0, "Quizzes must be deleted from DB"
    
    user_plans = [p for p in get_study_plans_for_user(user_id) if p["topic_id"] == session_id]
    assert len(user_plans) == 0, "Study plans must be deleted from DB"
    
    # Clean up test user
    from app.core.models import User
    with DBContext() as db:
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            db.delete(u)
            
    print("\n[SUCCESS] Section deletion completely removes all database records and associated data!")

if __name__ == "__main__":
    asyncio.run(test_section_deletion())

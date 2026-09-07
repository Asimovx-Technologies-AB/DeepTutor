import shutil
from pathlib import Path
import bcrypt
import uuid
from datetime import datetime

from app.core.database import DBContext, engine
from app.core.models import (
    Base, User, ChatSession, ChatMessage, Document, 
    Quiz, QuizQuestion, QuizAttempt, Flashcard, StudyPlan,
    UserActivity, UserProgress, LearningGoal, SessionDocument
)
# Legacy stores
try:
    from app.rag.vector_store import vector_store
except Exception:
    vector_store = None

try:
    from app.rag.graph_store import graph_store
except Exception:
    graph_store = None


def wipe_all_data(reseed_default_user: bool = True):
    print("==================================================")
    print("   DeepTutor - Full Dataset & Database Reset      ")
    print("==================================================")

    print("\n1. Wiping SQL database tables...")
    try:
        with DBContext() as db:
            db.query(ChatMessage).delete()
            db.query(ChatSession).delete()
            db.query(QuizQuestion).delete()
            db.query(QuizAttempt).delete()
            db.query(Quiz).delete()
            db.query(Flashcard).delete()
            db.query(StudyPlan).delete()
            db.query(SessionDocument).delete()
            db.query(Document).delete()
            db.query(UserActivity).delete()
            db.query(UserProgress).delete()
            db.query(LearningGoal).delete()
            db.query(User).delete()
        print("   [OK] Cleared all SQL tables (Chats, Documents, Quizzes, Flashcards, Study Plans, Activities, Progress, Users, Session Documents).")
    except Exception as e:
        print(f"   [WARN] SQL clear warning: {e}")
        # Fallback drop and recreate
        try:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            print("   [OK] Re-created clean schema tables.")
        except Exception as e2:
            print(f"   [ERROR] Could not recreate tables: {e2}")

    # Force create new tables if they don't exist yet!
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass

    print("\n2. Resetting Active Vector Store & Knowledge Graph...")
    try:
        # Fallback for old active_vector_store if it was injected
        pass
    except Exception as e:
        print(f"   [INFO] Vector store reset note: {e}")

    try:
        # Fallback for old active_graph_store if it was injected
        pass
    except Exception as e:
        print(f"   [INFO] Graph store reset note: {e}")

    if vector_store and hasattr(vector_store, "reset"):
        try:
            vector_store.reset()
        except Exception:
            pass

    print("\n3. Clearing all data directories on disk...")
    folders_to_clear = [
        Path("./uploads"),
        Path("./graph_data"),
        Path("./faiss_data"),
        Path("./lightrag_data"),
        Path("./chroma_data"),
        Path("./data"),
        Path("./vlm_cache"),
        Path("./image_search_cache"),
    ]

    for path in folders_to_clear:
        if path.exists():
            for item in path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass
            print(f"   [OK] Cleared contents of {path}")
        else:
            path.mkdir(parents=True, exist_ok=True)
            print(f"   [OK] Initialized empty directory {path}")

    if reseed_default_user:
        print("\n4. Re-seeding default user accounts...")
        default_email = "sreeharips385@gmail.com"
        default_username = "i"
        default_pass = "mypassword123"
        hashed = bcrypt.hashpw(default_pass.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        
        with DBContext() as db:
            # Main dev user
            user = User(
                id=str(uuid.uuid4()),
                username=default_username,
                email=default_email,
                password_hash=hashed,
                role="student",
                is_premium=True,
                plan="premium",
                created_at=datetime.utcnow().isoformat(),
            )
            db.add(user)

            # Guest learner for frontend PrivateRoute
            guest = User(
                id="guest-user",
                username="Student Learner",
                email="student@deeptutor.ai",
                password_hash=hashed,
                role="student",
                is_premium=True,
                plan="premium",
                created_at=datetime.utcnow().isoformat(),
            )
            db.add(guest)

        print(f"   [OK] Created default users: {default_email} and guest-user (student@deeptutor.ai)")

    print("\n==================================================")
    print(" [SUCCESS] All dataset & database state reset!")
    print("==================================================")


if __name__ == "__main__":
    wipe_all_data(reseed_default_user=True)


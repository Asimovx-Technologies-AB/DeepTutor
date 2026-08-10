import shutil
from pathlib import Path
from app.core.database import DBContext
from app.core.models import (
    User, ChatSession, ChatMessage, Document, 
    Quiz, QuizQuestion, QuizAttempt, Flashcard, StudyPlan
)
from app.rag.vector_store import vector_store

def wipe_all_data():
    print("1. Wiping SQL database tables...")
    with DBContext() as db:
        db.query(ChatMessage).delete()
        db.query(ChatSession).delete()
        db.query(QuizQuestion).delete()
        db.query(QuizAttempt).delete()
        db.query(Quiz).delete()
        db.query(Flashcard).delete()
        db.query(StudyPlan).delete()
        db.query(Document).delete()
        db.query(User).delete()

    print("2. Resetting ChromaDB vector collections...")
    try:
        vector_store.reset()
    except Exception as e:
        print(f"Vector store reset note: {e}")

    print("3. Deleting uploaded files and graph data...")
    folders_to_clear = ["./uploads", "./graph_data"]
    for folder in folders_to_clear:
        path = Path(folder)
        if path.exists():
            for item in path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass
            print(f"   Cleared contents of {folder}")

    print("✅ All data successfully deleted! You can start fresh.")

if __name__ == "__main__":
    wipe_all_data()

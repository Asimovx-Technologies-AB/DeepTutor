"""
Utility script to wipe all stored database entries, ChromaDB collections, graph files, and uploads so you can start completely fresh.
"""
import os
import shutil
from pathlib import Path
from app.core.database import DBContext
from app.core.models import User, ChatSession, ChatMessage, Document, Quiz, QuizQuestion, QuizAttempt, Flashcard, StudyPlan
from app.rag.vector_store import vector_store

def reset_all_data():
    print("Cleaning database tables...")
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

    print("Resetting ChromaDB collections...")
    try:
        vector_store.reset()
    except Exception as e:
        print(f"Vector store reset note: {e}")

    # Remove upload directories and graph data
    dirs_to_clean = ["./uploads", "./graph_data"]
    for dir_path in dirs_to_clean:
        p = Path(dir_path)
        if p.exists():
            for item in p.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass
            print(f"Cleared contents of {dir_path}")

    print("All database records and files cleared successfully! Starting fresh.")

if __name__ == "__main__":
    reset_all_data()

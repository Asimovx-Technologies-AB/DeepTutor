import os
import shutil
import sqlite3
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REGISTRY_PATH = DATA_DIR / "sessions_registry.json"
USER_MEMORY_PATH = DATA_DIR / "user_memory.json"
STUDY_STORE_PATH = DATA_DIR / "study_store.db"
DEEP_TUTOR_DB = BACKEND_DIR / "deep_tutor.db"
UPLOADS_DIR = BACKEND_DIR / "uploads"

def reset_dataset():
    print("==================================================")
    print("   Resetting Learn Page Dataset (Preserving Users)")
    print("==================================================")

    # 1. Clear session SQLite database files
    if SESSIONS_DIR.exists():
        for file in SESSIONS_DIR.glob("*.db"):
            try:
                file.unlink()
                print(f"Deleted session DB: {file.name}")
            except Exception as e:
                print(f"Error deleting {file.name}: {e}")

    # 2. Reset sessions_registry.json to empty list
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
    print("Reset sessions_registry.json to []")

    # 3. Reset user_memory.json to empty dict
    with open(USER_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2)
    print("Reset user_memory.json to {}")

    # 4. Remove study_store.db
    if STUDY_STORE_PATH.exists():
        try:
            STUDY_STORE_PATH.unlink()
            print("Deleted study_store.db")
        except Exception as e:
            print(f"Could not delete study_store.db: {e}")

    # 5. Clear uploads folder
    if UPLOADS_DIR.exists():
        for item in UPLOADS_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                print(f"Removed upload: {item.name}")
            except Exception as e:
                print(f"Error removing {item.name}: {e}")

    # 6. Clear SQL tables in deep_tutor.db, but keep USERS intact!
    if DEEP_TUTOR_DB.exists():
        try:
            conn = sqlite3.connect(str(DEEP_TUTOR_DB))
            cur = conn.cursor()

            # Verify existing users
            users = cur.execute("SELECT id, email, username FROM users").fetchall()
            print(f"Found {len(users)} user(s) to preserve: {[u[1] for u in users]}")

            # Clear learning & session tables
            tables_to_clear = [
                "chat_messages",
                "chat_sessions",
                "quiz_questions",
                "quiz_attempts",
                "quizzes",
                "flashcards",
                "study_plans",
                "documents",
                "user_activities",
                "user_progress",
                "learning_goals"
            ]

            for table in tables_to_clear:
                try:
                    cur.execute(f"DELETE FROM {table}")
                    print(f"Cleared table: {table}")
                except Exception as te:
                    pass

            conn.commit()

            # Verify users still exist
            remaining_users = cur.execute("SELECT id, email, username FROM users").fetchall()
            print(f"Preserved {len(remaining_users)} user(s): {[u[1] for u in remaining_users]}")
            conn.close()
        except Exception as dbe:
            print(f"Database table clear error: {dbe}")

    print("\n[SUCCESS] Learn page dataset successfully reset! All users preserved.")

if __name__ == "__main__":
    reset_dataset()

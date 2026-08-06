"""
a user directly to the deep_tutor.db database.
Edit the USER_DATA section below, then run:
  .venv\Scripts\python.exe add_user.py
"""
import sqlite3
import uuid
from datetime import datetime
import bcrypt

# ─── EDIT THESE ──────────────────────────────────────────────────────────────
USER_DATA = [
    {
        "username": "i",
        "email":    "sreeharips385@gmail.com",
        "password": "mypassword123",
        "role":     "student",   # or "admin"
    },
    # more users here if needed:
    # {
    #     "username": "admin",
    #     "email":    "admin@deeptutor.ai",
    #     "password": "adminpass",
    #     "role":     "admin",
    # },
]
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = "deep_tutor.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

inserted = 0
skipped  = 0

for u in USER_DATA:
    # Check if email already exists
    existing = cur.execute("SELECT id FROM users WHERE email = ?", (u["email"],)).fetchone()
    if existing:
        password_hash = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "UPDATE users SET password_hash = ?, username = ?, role = ? WHERE email = ?",
            (password_hash, u["username"], u["role"], u["email"])
        )
        print(f"  [UPDATED]  {u['email']} (updated password/profile, id={existing[0]})")
        inserted += 1
        continue

    uid          = str(uuid.uuid4())
    password_hash = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()
    created_at   = datetime.utcnow().isoformat()

    cur.execute(
        "INSERT INTO users (id, username, email, password_hash, role, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uid, u["username"], u["email"], password_hash, u["role"], created_at),
    )
    print(f"  [INSERTED] {u['email']}  (id={uid})")
    inserted += 1

conn.commit()
conn.close()

print()
print(f"Done — {inserted} inserted, {skipped} skipped.")

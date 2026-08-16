from app.core import database as db
from sqlalchemy import text

with db.DBContext() as ctx:
    ctx.execute(text("DELETE FROM users WHERE email='sreeharips386@gmail.com'"))
    ctx.commit()
    print("USER DELETED CLEANLY")

from app.core.database import DBContext, ChatSession
with DBContext() as db:
    for s in db.query(ChatSession).all():
        print(f'ID: {s.id}, Topic: {s.topic_id}, Title: {s.session_title}')

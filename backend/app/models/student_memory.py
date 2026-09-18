import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StudentMemoryFact(Base):
    """
    Persistent student memory facts to replace process-global in-memory storage.
    Enforces user isolation and data longevity across server restarts.
    """
    __tablename__ = "student_memory_facts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), index=True, nullable=False)
    fact = Column(Text, nullable=False)
    meta = Column(JSON, default=dict, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

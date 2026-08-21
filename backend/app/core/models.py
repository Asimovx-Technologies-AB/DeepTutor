import json
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default='student')
    is_premium = Column(Boolean, default=False)
    plan = Column(String, default='free')  # 'free' or 'premium'
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    
    # Dynamic Dashboard Stats
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    total_learning_hours = Column(Float, default=0.0)
    last_active_date = Column(String, nullable=True)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    activities = relationship("UserActivity", back_populates="user", cascade="all, delete-orphan")
    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    learning_goals = relationship("LearningGoal", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    topic_id = Column(String, nullable=True)
    session_title = Column(String, nullable=False)
    started_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    ended_at = Column(String, nullable=True)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey('chat_sessions.id'), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    _metadata = Column("metadata", Text, default="{}")  # Stored as stringified JSON
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    session = relationship("ChatSession", back_populates="messages")

    @property
    def meta(self):
        try:
            return json.loads(self._metadata)
        except Exception:
            return {}

    @meta.setter
    def meta(self, value):
        self._metadata = json.dumps(value or {})


class Document(Base):
    __tablename__ = 'documents'

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    topic_id = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    indexed = Column(Boolean, default=False)
    entity_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    _key_topics = Column("key_topics", Text, default="[]")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    @property
    def key_topics(self):
        try:
            return json.loads(self._key_topics)
        except Exception:
            return []

    @key_topics.setter
    def key_topics(self, value):
        self._key_topics = json.dumps(value or [])


class Quiz(Base):
    __tablename__ = 'quizzes'

    id = Column(String, primary_key=True)
    topic_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    difficulty = Column(String, default='medium')
    time_limit_mins = Column(Integer, default=10)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = 'quiz_questions'

    id = Column(String, primary_key=True)
    quiz_id = Column(String, ForeignKey('quizzes.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String, default='multiple_choice')
    _options = Column("options", Text, default="[]")  # Stored as stringified JSON list
    correct_answer = Column(String, nullable=False)  # 'A', 'B', 'C', 'D'
    explanation = Column(Text, nullable=True)

    quiz = relationship("Quiz", back_populates="questions")

    @property
    def options(self):
        try:
            return json.loads(self._options)
        except Exception:
            return []

    @options.setter
    def options(self, value):
        self._options = json.dumps(value or [])


class QuizAttempt(Base):
    __tablename__ = 'quiz_attempts'

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    quiz_id = Column(String, ForeignKey('quizzes.id'), nullable=False)
    score = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    _answers = Column("answers", Text, default="{}")  # Stored as stringified JSON dict
    attempted_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    @property
    def answers(self):
        try:
            return json.loads(self._answers)
        except Exception:
            return {}

    @answers.setter
    def answers(self, value):
        self._answers = json.dumps(value or {})


class Flashcard(Base):
    __tablename__ = 'flashcards'

    id = Column(String, primary_key=True)
    topic_id = Column(String, nullable=False)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    mastered = Column(Boolean, default=False)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class StudyPlan(Base):
    __tablename__ = 'study_plans'

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    topic_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    target_date = Column(String, nullable=False)
    total_days = Column(Integer, default=7)
    hours_per_day = Column(Float, default=2.0)
    _schedule = Column("schedule", Text, default="[]")
    _completed_days = Column("completed_days", Text, default="[]")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    @property
    def schedule(self):
        try:
            return json.loads(self._schedule)
        except Exception:
            return []

    @schedule.setter
    def schedule(self, value):
        self._schedule = json.dumps(value or [])

    @property
    def completed_days(self):
        try:
            return json.loads(self._completed_days)
        except Exception:
            return []

    @completed_days.setter
    def completed_days(self, value):
        self._completed_days = json.dumps(value or [])


class KnowledgeGraph(Base):
    __tablename__ = 'knowledge_graphs'

    topic_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    _entities = Column("entities", Text, default="{}")
    _relations = Column("relations", Text, default="{}")
    _triplets = Column("triplets", Text, default="[]")
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    @property
    def entities(self):
        try:
            return json.loads(self._entities)
        except Exception:
            return {}

    @entities.setter
    def entities(self, value):
        self._entities = json.dumps(value or {})

    @property
    def relations(self):
        try:
            return json.loads(self._relations)
        except Exception:
            return {}

    @relations.setter
    def relations(self, value):
        self._relations = json.dumps(value or {})

    @property
    def triplets(self):
        try:
            return json.loads(self._triplets)
        except Exception:
            return []

    @triplets.setter
    def triplets(self, value):
        self._triplets = json.dumps(value or [])


class StudyNote(Base):
    __tablename__ = 'study_notes'

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    title = Column(String, nullable=False)
    topic_id = Column(String, nullable=False, default="general")
    subject = Column(String, nullable=False, default="General")
    note_type = Column(String, nullable=False, default="high_yield_master")  # 'high_yield_master', 'pyq_analysis', 'quick_cheat_sheet', 'solved_qa'
    material_doc_name = Column(String, nullable=True)
    _pyq_doc_names = Column("pyq_doc_names", Text, default="[]")
    content_markdown = Column(Text, nullable=False)
    _high_yield_topics = Column("high_yield_topics", Text, default="[]")
    _pyq_patterns = Column("pyq_patterns", Text, default="[]")
    _key_formulas = Column("key_formulas", Text, default="[]")
    _exam_tips = Column("exam_tips", Text, default="[]")
    _solved_questions = Column("solved_questions", Text, default="[]")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    user = relationship("User")

    @property
    def pyq_doc_names(self):
        try:
            return json.loads(self._pyq_doc_names)
        except Exception:
            return []

    @pyq_doc_names.setter
    def pyq_doc_names(self, value):
        self._pyq_doc_names = json.dumps(value or [])

    @property
    def high_yield_topics(self):
        try:
            return json.loads(self._high_yield_topics)
        except Exception:
            return []

    @high_yield_topics.setter
    def high_yield_topics(self, value):
        self._high_yield_topics = json.dumps(value or [])

    @property
    def pyq_patterns(self):
        try:
            return json.loads(self._pyq_patterns)
        except Exception:
            return []

    @pyq_patterns.setter
    def pyq_patterns(self, value):
        self._pyq_patterns = json.dumps(value or [])

    @property
    def key_formulas(self):
        try:
            return json.loads(self._key_formulas)
        except Exception:
            return []

    @key_formulas.setter
    def key_formulas(self, value):
        self._key_formulas = json.dumps(value or [])

    @property
    def exam_tips(self):
        try:
            return json.loads(self._exam_tips)
        except Exception:
            return []

    @exam_tips.setter
    def exam_tips(self, value):
        self._exam_tips = json.dumps(value or [])

    @property
    def solved_questions(self):
        try:
            return json.loads(self._solved_questions)
        except Exception:
            return []

    @solved_questions.setter
    def solved_questions(self, value):
        self._solved_questions = json.dumps(value or [])



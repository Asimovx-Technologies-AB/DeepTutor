from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset


class QueryMetadata(BaseModel):
    """
    Structured representation of the analyzed user query
    following Query Preprocessing, Reference Resolution, and Understanding.
    """
    raw_query: str
    language: str = "english"
    normalized_query: str
    resolved_query: str # Post pronoun and follow-up resolution
    
    # Query Understanding
    intent: Literal[
        "DOCUMENT_QA",
        "EXPLANATION",
        "COMPARISON",
        "FOLLOW_UP",
        "CASUAL",
        "SUMMARY",
        "QUIZ",
        "PROBLEM_SOLVING",
        "PRACTICE_QUESTIONS"
    ] = "DOCUMENT_QA"
    
    target_topic: Optional[str] = None
    question_count: Optional[int] = None
    referenced_page: Optional[int] = None
    referenced_table: Optional[str] = None
    format_directives: Optional[Dict[str, Any]] = None
    extracted_entities: List[str] = Field(default_factory=list)
    learning_objective: str = "understand" # recall, understand, apply, analyze, evaluate
    difficulty_level: str = "Intermediate" # Beginner, Intermediate, Advanced
    response_requirements: Dict[str, bool] = Field(
        default_factory=lambda: {"needs_latex": False, "needs_table": False, "needs_steps": False, "needs_socratic": True}
    )
    question_complexity: Literal["simple", "multi_hop", "comparative", "evaluative"] = "simple"


class CitationItem(BaseModel):
    chunk_id: str
    page_number: int
    chapter_section: Optional[str] = None
    snippet: str
    source_uri: Optional[str] = None
    confidence: float = 1.0


class ContextBundle(BaseModel):
    """
    Synthesized Context Bundle provided to the Teaching Agent.
    Contains retrieved evidence, session history, and student profile.
    """
    document_id: Optional[str] = None
    topic_id: Optional[str] = None
    topic_title: Optional[str] = None
    resolved_query: str
    
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    student_mastery_context: Dict[str, float] = Field(default_factory=dict)
    
    retrieved_chunks: List[KnowledgeChunkRead] = Field(default_factory=list)
    curriculum_topics: List[str] = Field(default_factory=list)
    related_formulas: List[str] = Field(default_factory=list)
    related_tables: List[str] = Field(default_factory=list)
    citations: List[CitationItem] = Field(default_factory=list)


class AnswerValidationResult(BaseModel):
    """
    Result of the Answer Validation Gate:
    Grounding, Cross-reference, Pedagogy, and Safety checks.
    """
    is_valid: bool
    grounding_score: float = Field(..., ge=0.0, le=1.0)
    cross_reference_valid: bool = True
    pedagogy_score: float = Field(..., ge=0.0, le=1.0)
    safety_valid: bool = True
    validation_status: Literal["PASS", "FAIL"] = "PASS"
    feedback_notes: str = ""
    refined_response: Optional[str] = None


class TeachingResponse(BaseModel):
    content: str
    intent: str
    citations: List[CitationItem] = Field(default_factory=list)
    grounding_score: float = 1.0
    socratic_follow_up: Optional[str] = None
    suggested_questions: List[str] = Field(default_factory=list)


# ─── API & Session Schemas ───────────────────────────────────────────────────

class StudySessionCreate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = "General Studies"
    document_id: Optional[str] = None


class CurriculumTopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    document_id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    difficulty: str
    estimated_study_time: str
    order_index: int
    key_concepts: List[str] = Field(default_factory=list)
    structural_path: Optional[str] = None
    page_start: int
    page_end: int
    mastered: bool = False


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    intent: Optional[str] = None
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    grounding_score: float = 1.0
    created_at: datetime


class StudySessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    document_id: Optional[str] = None
    subject: str
    title: str
    document_name: Optional[str] = None
    status: str
    topic_count: int
    message_count: int
    created_at: datetime
    last_active: datetime
    curriculum_topics: List[CurriculumTopicRead] = Field(default_factory=list)

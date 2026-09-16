from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset


class PreGenerationPlan(BaseModel):
    """
    Pre-Generation Classification Plan determining response shape, depth, format,
    visual need, and follow-up question behavior before generation begins.
    """
    depth: Literal["answer_only", "short", "detailed", "default"] = "default"
    format: Literal["bullets", "table", "stepwise", "prose"] = "prose"
    visual: Literal["none", "required", "conditional"] = "conditional"
    skip_followup_question: bool = False
    reasoning: str = "Default balanced teaching response strategy."


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
        "STUDY_NOTES",
        "QUIZ",
        "PROBLEM_SOLVING",
        "PRACTICE_QUESTIONS"
    ] = "DOCUMENT_QA"
    
    context_source: Literal[
        "dialogue_history",   # Query targets recent chat history turns or previous assistant explanations
        "study_material",     # Query targets document textbook content, formulas, concepts, or practice problems
    ] = "study_material"
    
    target_topic: Optional[str] = None
    question_count: Optional[int] = None
    referenced_page: Optional[int] = None
    referenced_table: Optional[str] = None
    referenced_figure: Optional[str] = None
    format_directives: Optional[Dict[str, Any]] = None
    extracted_entities: List[str] = Field(default_factory=list)
    learning_objective: str = "understand" # recall, understand, apply, analyze, evaluate
    difficulty_level: str = "Intermediate" # Beginner, Intermediate, Advanced
    response_requirements: Dict[str, bool] = Field(
        default_factory=lambda: {"needs_latex": False, "needs_table": False, "needs_steps": False, "needs_socratic": True}
    )
    visual_modality: Literal["none", "mermaid", "svg"] = "none"
    visual_diagram_type: Literal[
        "none",
        "flowchart_lr",      # Horizontal chronological progressions, evolutions, phases, pipelines, timelines
        "flowchart_td",      # Vertical logic, decision trees, algorithmic workflows, classifications
        "concept_graph",     # Concept relationship network for important questions & topic mastery
        "sequence",          # Multi-actor communication, network protocols, client-server exchanges
        "state_diagram",     # Finite state machines and state transitions
        "mindmap",           # Unordered radial brainstorming / multi-pillar syllabus overviews
        "svg"                # Spatial, physical, anatomical, geometric, vector diagrams
    ] = "none"
    visual_prompt_focus: Optional[str] = None
    question_complexity: Literal["simple", "multi_hop", "comparative", "evaluative"] = "simple"
    is_pasted_mcq: bool = False
    is_batch_questions: bool = False
    batch_question_count: Optional[int] = None
    query_scope: Literal[
        "global_material",   # Explicitly covers whole document / all topics (e.g. "from this material", "cover all the topics")
        "current_topic",     # Explicitly follow-up on chat topic (e.g. "tell me more about bagging", "why is step 2 needed?")
        "specific_topic",    # Explicitly names a concept (e.g. "what is SVM?", "questions on Random Forest")
        "ambiguous_scope",   # Ambiguous: could be previous chat topic OR whole material (e.g. "give me 5 questions", "quiz me")
    ] = "specific_topic"
    scope_clarification_prompt: Optional[str] = None
    pre_gen_plan: PreGenerationPlan = Field(default_factory=PreGenerationPlan)


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
    resolved_query: str = ""
    
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    student_mastery_context: Dict[str, float] = Field(default_factory=dict)
    
    retrieved_chunks: List[KnowledgeChunkRead] = Field(default_factory=list)
    curriculum_topics: List[str] = Field(default_factory=list)
    related_formulas: List[str] = Field(default_factory=list)
    related_tables: List[str] = Field(default_factory=list)
    related_figures: List[str] = Field(default_factory=list)
    citations: List[CitationItem] = Field(default_factory=list)
    missing_table_requested: bool = False
    missing_figure_requested: bool = False
    requested_table_name: Optional[str] = None
    requested_figure_name: Optional[str] = None


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

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset


from enum import Enum


class ReferenceTypeEnum(str, Enum):
    NONE = "NONE"
    CONVERSATION = "CONVERSATION"
    GENERATED_QUESTION = "GENERATED_QUESTION"
    GENERATED_QUIZ = "GENERATED_QUIZ"
    GENERATED_FLASHCARD = "GENERATED_FLASHCARD"
    GENERATED_NOTES = "GENERATED_NOTES"
    GENERATED_STUDY_PLAN = "GENERATED_STUDY_PLAN"
    DOCUMENT = "DOCUMENT"
    CHAPTER = "CHAPTER"
    SECTION = "SECTION"


class AmbiguityStatusEnum(str, Enum):
    CLEAR = "CLEAR"
    RESOLVED_FROM_CONTEXT = "RESOLVED_FROM_CONTEXT"
    AMBIGUOUS = "AMBIGUOUS"


class AmbiguityTypeEnum(str, Enum):
    INTENT = "INTENT"
    REFERENCE = "REFERENCE"
    ENTITY = "ENTITY"
    TOPIC = "TOPIC"
    DOCUMENT = "DOCUMENT"
    SCOPE = "SCOPE"
    OUTPUT = "OUTPUT"
    NONE = "NONE"


class DecisionStateEnum(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    RETRIEVE = "RETRIEVE"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    GENERATE = "GENERATE"
    FOLLOW_UP = "FOLLOW_UP"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class AnswerabilityStatusEnum(str, Enum):
    ANSWERABLE = "ANSWERABLE"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AnswerabilityCheck(BaseModel):
    status: AnswerabilityStatusEnum = AnswerabilityStatusEnum.ANSWERABLE
    confidence: float = 1.0
    evidence_available: bool = True


class UserIntent(str, Enum):
    ANSWER_QUESTION = "ANSWER_QUESTION"
    EXPLAIN_TOPIC = "EXPLAIN_TOPIC"
    TEACH_TOPIC = "TEACH_TOPIC"
    SUMMARIZE = "SUMMARIZE"
    SIMPLIFY = "SIMPLIFY"
    GENERATE_EXAMPLES = "GENERATE_EXAMPLES"
    GENERATE_QUESTIONS = "GENERATE_QUESTIONS"
    GENERATE_QUIZ = "GENERATE_QUIZ"
    GENERATE_FLASHCARDS = "GENERATE_FLASHCARDS"
    CREATE_STUDY_PLAN = "CREATE_STUDY_PLAN"
    MODIFY_STUDY_PLAN = "MODIFY_STUDY_PLAN"
    SEARCH_MATERIAL = "SEARCH_MATERIAL"
    ASK_FROM_MATERIAL = "ASK_FROM_MATERIAL"
    COMPARE_CONCEPTS = "COMPARE_CONCEPTS"
    SOLVE_PROBLEM = "SOLVE_PROBLEM"
    CHECK_ANSWER = "CHECK_ANSWER"
    GENERATE_NOTES = "GENERATE_NOTES"
    CONTINUE_LEARNING = "CONTINUE_LEARNING"
    CLARIFY_CONCEPT = "CLARIFY_CONCEPT"
    FOLLOW_UP = "FOLLOW_UP"
    GREETING = "GREETING"
    CONFIRMATION = "CONFIRMATION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    ANSWER_CHALLENGE = "ANSWER_CHALLENGE"
    # Exam lifecycle intents
    EXAM_START = "EXAM_START"
    EXAM_ANSWER = "EXAM_ANSWER"
    EXAM_NEXT = "EXAM_NEXT"
    EXAM_COMPLETE = "EXAM_COMPLETE"
    EXAM_REPORT = "EXAM_REPORT"
    # Legacy / alias compat
    CASUAL = "CASUAL"
    DOCUMENT_QA = "DOCUMENT_QA"
    PRACTICE_QUESTIONS = "PRACTICE_QUESTIONS"
    SUMMARY = "SUMMARY"
    STUDY_NOTES = "STUDY_NOTES"
    QUIZ = "QUIZ"
    PROBLEM_SOLVING = "PROBLEM_SOLVING"
    COMPARISON = "COMPARISON"
    EXPLANATION = "EXPLANATION"
    DOCUMENT_TOPIC_ANALYSIS = "DOCUMENT_TOPIC_ANALYSIS"



class RetrievalDecisionEnum(str, Enum):
    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class RetrievalScopeEnum(str, Enum):
    NONE = "NONE"
    USER_MATERIAL = "USER_MATERIAL"
    CURRENT_SUBJECT = "CURRENT_SUBJECT"
    CURRENT_TOPIC = "CURRENT_TOPIC"
    SPECIFIC_DOCUMENT = "SPECIFIC_DOCUMENT"
    SPECIFIC_CHAPTER = "SPECIFIC_CHAPTER"
    GLOBAL_KNOWLEDGE = "GLOBAL_KNOWLEDGE"


class ResponseTypeEnum(str, Enum):
    DIRECT_ANSWER = "DIRECT_ANSWER"
    DETAILED_EXPLANATION = "DETAILED_EXPLANATION"
    STEP_BY_STEP = "STEP_BY_STEP"
    SUMMARY = "SUMMARY"
    BULLET_POINTS = "BULLET_POINTS"
    TABLE = "TABLE"
    QUIZ = "QUIZ"
    FLASHCARDS = "FLASHCARDS"
    EXAMPLES = "EXAMPLES"
    COMPARISON = "COMPARISON"
    STUDY_PLAN = "STUDY_PLAN"
    NOTES = "NOTES"
    SIMPLE_EXPLANATION = "SIMPLE_EXPLANATION"


class ActionTypeEnum(str, Enum):
    ANSWER_QUESTION = "ANSWER_QUESTION"
    EXPLAIN_TOPIC = "EXPLAIN_TOPIC"
    TEACH_TOPIC = "TEACH_TOPIC"
    GENERATE_QUIZ = "GENERATE_QUIZ"
    GENERATE_FLASHCARDS = "GENERATE_FLASHCARDS"
    CREATE_STUDY_PLAN = "CREATE_STUDY_PLAN"
    MODIFY_STUDY_PLAN = "MODIFY_STUDY_PLAN"
    GENERATE_SUMMARY = "GENERATE_SUMMARY"
    SOLVE_PROBLEM = "SOLVE_PROBLEM"
    SEARCH_MATERIAL = "SEARCH_MATERIAL"
    CLARIFY_QUERY = "CLARIFY_QUERY"
    CASUAL_REPLY = "CASUAL_REPLY"
    DIRECT_ANSWER = "DIRECT_ANSWER"
    EXPLAIN_GENERATED_QUESTION = "EXPLAIN_GENERATED_QUESTION"
    DOCUMENT_TOPIC_ANALYSIS = "DOCUMENT_TOPIC_ANALYSIS"
    ANALYZE_IMPORTANT_TOPICS = "ANALYZE_IMPORTANT_TOPICS"


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


class ActionPlan(BaseModel):
    """
    Action Plan generated by Query Understanding Layer indicating what execution
    path, tools, retrieval parameters, and response styling should be used.
    """
    action: str = "ANSWER_QUESTION"
    decision: DecisionStateEnum = DecisionStateEnum.ANSWER
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    retrieval_required: bool = False
    retrieval_scope: str = "NONE"
    retrieval_query: Optional[str] = None
    response_type: str = "DETAILED_EXPLANATION"
    requires_tool: bool = False
    tool_name: Optional[str] = None
    requires_user_context: bool = False
    confidence: float = 1.0
    execution_strategy: Optional[str] = None
    clarification_prompt: Optional[str] = None


class OutputRequirements(BaseModel):
    format: str = "DEFAULT" # ANSWER_ONLY, EXPLANATION, STEP_BY_STEP, KEY_POINTS, SHORT_ANSWER, DETAILED_ANSWER, EXPLANATION_WITH_EXAMPLE, QUESTION_LIST, QUESTION_AND_ANSWER_LIST, BULLET_POINTS
    length: str = "DEFAULT" # SHORT, DEFAULT, DETAILED
    include_explanation: bool = True
    include_examples: bool = False
    include_steps: bool = False
    include_sources: bool = False
    include_question: bool = False

class QueryUnderstandingResult(BaseModel):
    """
    Strongly typed, unified output produced by the Query Understanding Layer.
    Adheres strictly to the Query Understanding -> Decision -> Action -> Response architecture.
    """
    original_query: str
    normalized_query: str
    resolved_query: str
    language: str = "en"

    intent: str
    sub_intent: Optional[str] = None

    subject: Optional[str] = None
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    topics: List[str] = Field(default_factory=list)

    entities: List[str] = Field(default_factory=list)
    
    reference_type: str = "NONE"
    reference_target: Optional[str] = None
    reference_index: Optional[int] = None
    artifact_id: Optional[str] = None
    artifact_item_id: Optional[str] = None
    ambiguity_status: str = "CLEAR"

    difficulty: str = "beginner"
    response_type: str = "DETAILED_EXPLANATION"

    requires_context: bool = False
    requires_retrieval: bool = False
    retrieval_scope: str = "NONE"
    retrieval_query: Optional[str] = None
    requires_document_analysis: bool = False
    analysis_scope: Optional[str] = None

    action: str = "ANSWER_QUESTION"
    decision: DecisionStateEnum = DecisionStateEnum.ANSWER
    answerability: AnswerabilityCheck = Field(default_factory=AnswerabilityCheck)
    action_plan: Optional[ActionPlan] = None
    requires_tool: bool = False
    tool_name: Optional[str] = None

    # Multi-dimensional Confidences
    intent_confidence: float = 1.0
    topic_confidence: float = 1.0
    reference_confidence: float = 1.0
    material_support_confidence: float = 1.0
    evidence_confidence: float = 1.0
    confidence: float = 1.0  # Overall combined confidence

    requires_example: bool = False
    ambiguity_type: str = "NONE"
    clarification_prompt: Optional[str] = None
    is_fast_path: bool = False

    missing_information: List[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    requested_count: Optional[int] = None
    include_answers: bool = False
    source_scope: Optional[str] = None
    conversation_reference: Optional[str] = None
    resolved_reference: Optional[str] = None
    
    output_requirements: OutputRequirements = Field(default_factory=OutputRequirements)


class QueryMetadata(BaseModel):
    """
    Structured representation of the analyzed user query
    following Query Preprocessing, Reference Resolution, and Understanding.
    Maintains full backward compatibility across all pipelines.
    """
    raw_query: str
    language: str = "english"
    normalized_query: str
    resolved_query: str  # Post pronoun and follow-up resolution

    # Query Understanding
    intent: str = "DOCUMENT_QA"

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
    learning_objective: str = "understand"  # recall, understand, apply, analyze, evaluate
    difficulty_level: str = "Intermediate"  # Beginner, Intermediate, Advanced
    response_requirements: Dict[str, bool] = Field(
        default_factory=lambda: {"needs_latex": False, "needs_table": False, "needs_steps": False, "needs_socratic": True}
    )
    visual_modality: Literal["none", "svg", "mermaid"] = "none"
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

    output_requirements: Optional[OutputRequirements] = None

    pre_gen_plan: Optional[PreGenerationPlan] = None
    understanding_result: Optional[QueryUnderstandingResult] = None
    
    # Confidence and Ambiguity dimensions
    intent_confidence: float = 1.0
    topic_confidence: float = 1.0
    reference_confidence: float = 1.0
    ambiguity_type: str = "NONE"


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


# ─── Interactive Teacher Mode State Schemas ──────────────────────────────────

class TeacherStageEnum(str, Enum):
    """Structured stages for interactive Teacher Mode state machine."""
    INTRO = "INTRO"
    TEACHING = "TEACHING"
    TEACHING_SUBTOPIC = "TEACHING_SUBTOPIC"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    ANSWERING_QUESTION = "ANSWERING_QUESTION"
    FIGURE_EXPLANATION = "FIGURE_EXPLANATION"
    CHECKPOINT = "CHECKPOINT"
    CHECKPOINT_EXAM = "CHECKPOINT_EXAM"
    WAITING_FOR_STUDENT = "WAITING_FOR_STUDENT"
    EVALUATING = "EVALUATING"
    REEXPLAINING = "REEXPLAINING"
    PREREQUISITE_REVIEW = "PREREQUISITE_REVIEW"
    DOUBT = "DOUBT"
    SYNTHESIS = "SYNTHESIS"
    COMPLETE_FIGURE = "COMPLETE_FIGURE"
    FINAL_ASSESSMENT = "FINAL_ASSESSMENT"
    FINAL_EXAM = "FINAL_EXAM"
    EXAM_EVALUATION = "EXAM_EVALUATION"
    COMPLETED = "COMPLETED"


class PauseContext(BaseModel):
    """Lightweight snapshot of teaching position when paused for doubts or side-tracks."""
    current_unit_id: str
    current_stage: str
    current_question_id: Optional[str] = None
    current_figure_id: Optional[str] = None
    previous_action: Optional[str] = None


class VisualLearningState(BaseModel):
    """Tracks progressive visual/diagram explanation across learning units."""
    visual_id: Optional[str] = None
    analysis: Optional[str] = None
    components: List[str] = Field(default_factory=list)
    explained_components: List[str] = Field(default_factory=list)
    current_component: Optional[str] = None
    understanding: Optional[str] = None
    previous_visual_description: Optional[str] = None
    diagram_elements: List[str] = Field(default_factory=list)
    diagram_relationships: List[str] = Field(default_factory=list)


class LearningUnit(BaseModel):
    """A granular, teachable learning unit dynamically created from study material."""
    id: str
    concept: str
    objective: str
    prerequisites: List[str] = Field(default_factory=list)
    source_references: List[str] = Field(default_factory=list)
    relevant_visual_references: List[str] = Field(default_factory=list)
    source_pages: List[int] = Field(default_factory=list)
    relevant_figures: List[str] = Field(default_factory=list)
    relevant_tables: List[str] = Field(default_factory=list)
    relevant_formulas: List[str] = Field(default_factory=list)
    relationships: List[str] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    difficulty: str = "Intermediate"
    expected_understanding: Optional[str] = None
    status: Literal["pending", "in_progress", "completed", "skipped", "weak"] = "pending"


class TeachingPlan(BaseModel):
    """Dynamic, topic-agnostic teaching plan decomposed from study material."""
    topic: str
    overall_goal: str
    learning_units: List[LearningUnit] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StudentUnderstandingLevelEnum(str, Enum):
    UNDERSTOOD = "UNDERSTOOD"
    PARTIAL = "PARTIAL"
    MISCONCEPTION = "MISCONCEPTION"
    PREREQUISITE_GAP = "PREREQUISITE_GAP"
    NOT_UNDERSTOOD = "NOT_UNDERSTOOD"
    UNCLEAR = "UNCLEAR"


class TeacherTurnActionEnum(str, Enum):
    START_LESSON = "START_LESSON"
    EXPLAIN_CONCEPT = "EXPLAIN_CONCEPT"
    EXPLAIN_SUBTOPIC = "EXPLAIN_SUBTOPIC"
    CHECK_UNDERSTANDING = "CHECK_UNDERSTANDING"
    EVALUATE_ANSWER = "EVALUATE_ANSWER"
    ANSWER_DOUBT = "ANSWER_DOUBT"
    ANSWER_QUESTION = "ANSWER_QUESTION"
    RESUME_LESSON = "RESUME_LESSON"
    ADAPTIVE_REEXPLAIN = "ADAPTIVE_REEXPLAIN"
    REEXPLAIN_SUBTOPIC = "REEXPLAIN_SUBTOPIC"
    PREREQUISITE_REVIEW = "PREREQUISITE_REVIEW"
    NEXT_LEARNING_UNIT = "NEXT_LEARNING_UNIT"
    CONFIRM_NEXT = "CONFIRM_NEXT"
    DECLINE_NEXT = "DECLINE_NEXT"
    CONFIRM_CHECKPOINT_EXAM = "CONFIRM_CHECKPOINT_EXAM"
    SUBMIT_CHECKPOINT_EXAM = "SUBMIT_CHECKPOINT_EXAM"
    CONFIRM_EXAM = "CONFIRM_EXAM"
    SUBMIT_EXAM = "SUBMIT_EXAM"
    EVALUATE_EXAM = "EVALUATE_EXAM"
    SKIP_UNIT = "SKIP_UNIT"
    BACKTRACK_UNIT = "BACKTRACK_UNIT"
    TOPIC_SYNTHESIS = "TOPIC_SYNTHESIS"
    FINAL_ASSESSMENT = "FINAL_ASSESSMENT"
    LEARNING_REPORT = "LEARNING_REPORT"
    TOPIC_NOT_FOUND = "TOPIC_NOT_FOUND"
    UNRELATED_QUERY = "UNRELATED_QUERY"
    FEEDBACK_CORRECTION = "FEEDBACK_CORRECTION"
    STATEMENT_EVALUATION = "STATEMENT_EVALUATION"


class UserMessageClassificationEnum(str, Enum):
    FEEDBACK_CORRECTION = "FEEDBACK_CORRECTION"
    GENERAL_FACTUAL = "GENERAL_FACTUAL"
    STUDY_MATERIAL_QUESTION = "STUDY_MATERIAL_QUESTION"
    UNRELATED_CHAT = "UNRELATED_CHAT"
    NEW_QUESTION_REQUEST = "NEW_QUESTION_REQUEST"
    STATEMENT_EVALUATION = "STATEMENT_EVALUATION"
    CLARIFICATION_CONTINUATION = "CLARIFICATION_CONTINUATION"
    TEACH_TOPIC_REQUEST = "TEACH_TOPIC_REQUEST"


class UserMessageClassificationResult(BaseModel):
    category: UserMessageClassificationEnum
    confidence: float = 1.0
    reasoning: Optional[str] = None
    target_statement: Optional[str] = None
    corrected_aspect: Optional[str] = None
    is_ambiguous: bool = False
    ambiguity_clarification: Optional[str] = None
    suggested_interpretation: Optional[str] = None
    is_exam_report: bool = False


class TeacherSessionState(BaseModel):
    """
    Persistent state for an interactive, multi-turn Teacher Mode session.
    Preserves progression, subtopic order, cumulative progressive diagram state,
    confirmation checkpoints, doubts, adaptive checkpoint exams, and final exam state.
    """
    session_id: str
    mode: Literal["teacher"] = "teacher"
    topic: str = ""
    main_topic: str = ""
    topic_id: Optional[str] = None
    subtopics: List[str] = Field(default_factory=list)
    current_subtopic_index: int = 0
    current_unit_id: Optional[str] = None
    current_subtopic: Optional[str] = None
    current_concept: Optional[str] = None
    current_stage: str = TeacherStageEnum.INTRO.value
    current_objective: Optional[str] = None
    teaching_plan: Optional[TeachingPlan] = None
    current_unit_index: int = 0
    completed_learning_units: List[str] = Field(default_factory=list)
    completed_subtopics: List[str] = Field(default_factory=list)
    completed_concepts: List[str] = Field(default_factory=list)
    remaining_subtopics: List[str] = Field(default_factory=list)
    pending_concepts: List[str] = Field(default_factory=list)
    diagram_state: Optional[str] = None
    previous_visual_description: Optional[str] = None
    diagram_elements: List[str] = Field(default_factory=list)
    diagram_relationships: List[str] = Field(default_factory=list)
    used_subtopic_headings: List[str] = Field(default_factory=list)
    awaiting_user_confirmation: bool = True
    checkpoint_exam_completed: bool = False
    checkpoint_exam_available: bool = False
    checkpoint_exam_started: bool = False
    checkpoint_exam_score: Optional[str] = None
    exam_available: bool = False
    exam_started: bool = False
    exam_score: Optional[str] = None
    weak_subtopics: List[str] = Field(default_factory=list)
    specific_portion: Optional[str] = None
    current_figure: Optional[str] = None
    visual_state: Optional[VisualLearningState] = None
    current_question: Optional[Dict[str, Any]] = None
    student_doubts: List[Dict[str, Any]] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    understanding_state: str = "not_started"
    paused: bool = False
    pause_reason: Optional[str] = None
    pause_context: Optional[PauseContext] = None
    previous_state: Optional[Dict[str, Any]] = None
    next_step: Optional[str] = None
    assessment_history: List[Dict[str, Any]] = Field(default_factory=list)
    last_explanation: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        """Keep legacy and enhanced state attributes bidirectionally synchronized."""
        if not self.main_topic and self.topic:
            self.main_topic = self.topic
        elif not self.topic and self.main_topic:
            self.topic = self.main_topic

        if not self.current_subtopic and self.current_concept:
            self.current_subtopic = self.current_concept
        elif not self.current_concept and self.current_subtopic:
            self.current_concept = self.current_subtopic

        if self.teaching_plan and self.teaching_plan.learning_units and not self.subtopics:
            self.subtopics = [u.concept for u in self.teaching_plan.learning_units]

        if self.current_subtopic_index == 0 and self.current_unit_index != 0:
            self.current_subtopic_index = self.current_unit_index
        elif self.current_subtopic_index != 0 and self.current_unit_index == 0:
            self.current_unit_index = self.current_subtopic_index
        else:
            self.current_unit_index = self.current_subtopic_index

        if not self.completed_subtopics and self.completed_concepts:
            self.completed_subtopics = list(self.completed_concepts)
        elif not self.completed_concepts and self.completed_subtopics:
            self.completed_concepts = list(self.completed_subtopics)



from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class ExtractedTopicBase(BaseModel):
    topic: str
    chapter: Optional[str] = None
    importance_score: float = 0.0
    importance_level: str = "LOW"
    
    definitions_present: bool = False
    formula_present: bool = False
    examples_present: bool = False
    questions_present: bool = False
    summary_present: bool = False
    learning_objective_present: bool = False
    
    evidence: List[str] = []
    source_pages: List[int] = []
    
    prerequisites: List[str] = []
    related_topics: List[str] = []
    subtopics: List[str] = []

class ExtractedTopicRead(ExtractedTopicBase):
    id: str
    analysis_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DocumentTopicAnalysisRead(BaseModel):
    id: str
    document_id: str
    analysis_version: str
    status: str
    total_topics: int
    created_at: datetime
    updated_at: datetime
    topics: List[ExtractedTopicRead] = []

    class Config:
        from_attributes = True

class TopicAnalysisStatus(BaseModel):
    id: str
    document_id: str
    status: str
    total_topics: int
    created_at: datetime

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class TextSpan(BaseModel):
    text: str
    font_name: str
    font_size: float
    flags: int = 0
    color: int = 0
    bbox: List[float]


class LayoutBlock(BaseModel):
    block_index: int
    block_type: str = "text" # "text", "heading", "table", "formula", "image"
    reading_order: int
    bbox: List[float]
    text: str
    spans: List[TextSpan] = Field(default_factory=list)
    confidence: float = 1.0


class TableAsset(BaseModel):
    table_index: int
    page_number: int
    bbox: List[float]
    markdown: str
    html: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    caption: Optional[str] = None
    confidence: float = 1.0


class FormulaAsset(BaseModel):
    formula_index: int
    page_number: int
    bbox: List[float]
    latex: str
    is_display_mode: bool = True # True if $$...$$, False if inline $...$
    confidence: float = 1.0

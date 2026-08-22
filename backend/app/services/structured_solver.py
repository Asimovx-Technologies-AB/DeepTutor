"""
Structured Academic Question Solver & Verifier Service.

Handles:
1. Detection of structure types: Tables with blanks, Flowcharts, Fill-in-the-blanks, Matching pairs, Diagrams with labels.
2. Structure Preservation: Faithfully extracts and maintains the exact rows/columns/nodes layout.
3. Student-friendly Pedagogy: Provides a 1-line plain English definition + relatable real-world analogy.
4. Two-Pass Self-Verification: Independently checks each filled answer for chemical, mathematical, and logical correctness,
   flagging any uncertainty rather than guessing with false confidence.
5. Edge-Case Handling: Flags ambiguous or blurry inputs and notes multiple valid textbook alternatives.
"""

import re
from typing import Dict, Optional, Tuple
from enum import Enum


class StructureType(str, Enum):
    TABLE = "table"
    FLOWCHART = "flowchart"
    FILL_IN_BLANKS = "fill_in_blanks"
    MATCHING = "matching"
    DIAGRAM_LABELS = "diagram_labels"
    GENERAL_EXERCISE = "general_exercise"


def detect_structure_type(text: str) -> Optional[StructureType]:
    """
    Detect if the student's question/upload contains or requests solving a structured exercise.
    Returns the detected StructureType or None.
    """
    t_lower = text.lower()

    # 1. Tables with blanks / Table solving requests
    if any(w in t_lower for w in [
        "solve table", "fill table", "complete table", "fill the table", "complete the table",
        "solve the table", "fill in the table", "table with blanks", "table 1.", "table 2.",
        "table 3.", "table 4.", "table 5.", "activity table", "tabular column", "fill in table"
    ]):
        return StructureType.TABLE

    # Check for Markdown table containing missing blanks/symbols
    if "|" in text and ("---" in text or "-|-" in text):
        if any(marker in text for marker in ["...", "___", " ? ", "|?|", "| ? |", "[blank]", "[ ]", "(a)", "(b)", "____", "missing"]):
            return StructureType.TABLE

    # 2. Flowchart with blanks / steps
    if any(w in t_lower for w in [
        "complete flowchart", "fill flowchart", "solve flowchart", "complete the flowchart",
        "fill the flowchart", "flow chart with blanks", "complete the flow chart", "flowchart blanks",
        "missing steps in flow", "flowchart missing"
    ]):
        return StructureType.FLOWCHART

    # 3. Matching exercises / Column Matching
    if any(w in t_lower for w in [
        "match the following", "match column", "matching pairs", "match the pairs",
        "match column a", "match column 1", "match items", "match the terms"
    ]):
        return StructureType.MATCHING

    # 4. Fill in the blanks
    if any(w in t_lower for w in [
        "fill in the blanks", "fill in the blank", "fill the blanks", "complete the blanks",
        "missing words", "fill blanks", "fill the blank", "complete the sentences with blanks"
    ]):
        return StructureType.FILL_IN_BLANKS

    # 5. Diagram with missing labels / parts
    if any(w in t_lower for w in [
        "label the diagram", "label the figure", "missing labels", "identify the parts",
        "name the parts", "label parts", "diagram blanks"
    ]):
        return StructureType.DIAGRAM_LABELS

    # 6. General textbook activity solving
    if any(w in t_lower for w in [
        "solve activity", "complete activity", "activity 1.", "activity 2.", "activity 3.",
        "activity 4.", "activity 5.", "solve problem 1", "solve exercise", "complete exercise"
    ]):
        return StructureType.GENERAL_EXERCISE

    return None


def get_structured_solver_instruction(structure_type: StructureType, question: str) -> str:
    """
    Generate student-friendly, rigorously self-verified instruction prompt tailored to the structure type.
    """
    return (
        f"The student specifically asked to SOLVE & VERIFY A STRUCTURED ACADEMIC QUESTION ({structure_type.value.upper()}).\n\n"
        f"═══════════════════════════════════════════════════════\n"
        f"MANDATORY 5-STEP SOLVE & VERIFY PIPELINE\n"
        f"═══════════════════════════════════════════════════════\n"
        f"1. STRUCTURE PRESERVATION (STRICT):\n"
        f"   - Recreate the EXACT original structure (same rows, columns, headers, flowchart nodes, or matching layout).\n"
        f"   - Do NOT collapse, truncate, or omit any row/column. Present the completed structure in full.\n"
        f"   - Highlight all newly solved/filled items in bold (e.g. `**Filled Answer**`).\n\n"
        f"2. STUDENT-FACING SIMPLICITY & PEDAGOGY:\n"
        f"   - Start with a clear 1-2 sentence definition of the core concept in plain, friendly English (classmate-like tone, zero unnecessary jargon).\n"
        f"   - Include an intuitive, relatable everyday real-life analogy (`> ☀️ **Everyday Analogy:** ...`) so the concept clicks immediately.\n\n"
        f"3. INDEPENDENT TWO-PASS SELF-VERIFICATION:\n"
        f"   - Before presenting the final answer, conduct an independent verification pass on EVERY filled blank/node.\n"
        f"   - Verify chemical equations for atom balance and charge conservation.\n"
        f"   - Verify mathematical expressions and numerical steps with exact arithmetic.\n"
        f"   - Verify biological/physical definitions against the textbook context.\n"
        f"   - If an answer has uncertainty or multiple valid textbook variants, explicitly flag it (`⚠️ Note: Standard textbook answer is X; alternative Y is also valid`).\n"
        f"   - NEVER silently guess or present uncertain answers with false confidence.\n\n"
        f"4. MANDATORY OUTPUT FORMAT (Follow this EXACT structure):\n\n"
        f"# 📘 Solved & Verified: [Topic / Exercise Name]\n\n"
        f"### 💡 Simple Concept Definition\n"
        f"[Clear 1-2 sentence plain-English explanation of the topic behind this exercise]\n\n"
        f"> ☀️ **Everyday Analogy:**  \n"
        f"> [Relatable real-world story or analogy that makes this concept effortless to understand]\n\n"
        f"---\n\n"
        f"### 📝 Solved {structure_type.value.replace('_', ' ').title()} (Complete & Verified)\n"
        f"[Display the complete, beautifully formatted Markdown Table / Mermaid Flowchart / Matching Pairs with every blank filled in bold]\n\n"
        f"---\n\n"
        f"### 🔍 Step-by-Step Working & Reasoning for Each Blank\n"
        f"1. **[Blank / Position 1]:** **[Filled Value]**  \n"
        f"   - **Reason / Formula:** [Clear derivation, rule, or textbook principle used]\n"
        f"2. **[Blank / Position 2]:** **[Filled Value]**  \n"
        f"   - **Reason / Formula:** [Clear derivation, rule, or textbook principle used]\n\n"
        f"---\n\n"
        f"### ✅ Verification & Quality Notes\n"
        f"- [Confirmation that all equations balance, units match, and values align strictly with syllabus standards. Mention any common student pitfalls to avoid.]\n"
    )

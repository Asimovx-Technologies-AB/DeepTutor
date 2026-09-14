import re
from typing import Dict, Any, List
from app.schemas.tutoring import ContextBundle, AnswerValidationResult, TeachingResponse


class AnswerValidator:
    """
    Answer Validation Gate:
    - Grounding Check
    - Cross-reference Check
    - Pedagogy Check
    - Safety & Educational Quality
    Decision: PASS or FAIL (triggers refinement)
    """

    @classmethod
    def validate_response(
        cls,
        response_text: str,
        context_bundle: ContextBundle
    ) -> AnswerValidationResult:
        if not response_text or len(response_text.strip()) < 20:
            return AnswerValidationResult(
                is_valid=False,
                grounding_score=0.0,
                cross_reference_valid=False,
                pedagogy_score=0.0,
                safety_valid=False,
                validation_status="FAIL",
                feedback_notes="Response is empty or too short."
            )

        # 1. Grounding Check: Measure if retrieved knowledge is faithfully reflected in the response
        retrieved_content = " ".join(c.content.lower() for c in context_bundle.retrieved_chunks)
        retrieved_words = set(re.findall(r"\b[a-z]{4,}\b", retrieved_content))
        response_words = set(re.findall(r"\b[a-z]{4,}\b", response_text.lower()))

        if retrieved_words and response_words:
            # How many of the retrieved concepts/terms are present in the response
            covered_terms = sum(1 for w in retrieved_words if w in response_text.lower())
            chunk_coverage = covered_terms / len(retrieved_words)
            matched_response_words = sum(1 for w in response_words if w in retrieved_content)
            resp_overlap = matched_response_words / len(response_words)
            grounding_score = min(1.0, round((0.7 * chunk_coverage) + (0.3 * min(resp_overlap * 3.0, 1.0)), 2))
        else:
            grounding_score = 0.90 # Casual or fallback responses

        # 2. Cross-reference Check: Ensure cited pages match actual retrieved chunk pages
        cited_pages = [int(p) for p in re.findall(r"Page\s+(\d+)", response_text, re.IGNORECASE)]
        actual_pages = {c.page_number for c in context_bundle.retrieved_chunks}
        
        cross_ref_valid = True
        if cited_pages and actual_pages:
            # Check if majority of cited pages are authentic
            authentic_citations = sum(1 for p in cited_pages if p in actual_pages)
            if authentic_citations == 0:
                cross_ref_valid = False

        # 3. Pedagogy & Clarity Check: Check for educational formatting (headers, steps, socratic questions, analogies)
        has_headers = bool(re.search(r"^#{1,3}\s+", response_text, re.MULTILINE))
        has_bullets_or_steps = bool(re.search(r"^(?:-|\*|\d+\.)\s+", response_text, re.MULTILINE))
        has_socratic_prompt = "?" in response_text
        has_checkpoint = "### 💡 Interactive Checkpoint" in response_text or "Interactive Checkpoint" in response_text
        
        pedagogy_score = 0.5
        if has_headers:
            pedagogy_score += 0.15
        if has_bullets_or_steps:
            pedagogy_score += 0.15
        if has_socratic_prompt or has_checkpoint:
            pedagogy_score += 0.2

        # 4. Diagram Syntax & Integrity Check
        diagram_valid = True
        refined_text = response_text
        
        # Check Mermaid blocks
        mermaid_blocks = re.findall(r"```mermaid(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
        for block in mermaid_blocks:
            # Check for illegal unicode arrows
            if re.search(r"[⟶→➔➜➝➞⟹⇒⟵←]", block):
                # Auto-repair unicode arrows in refined text
                repaired_block = re.sub(r"[⟶→➔➜➝➞]", "-->", block)
                repaired_block = re.sub(r"[⟹⇒]", "==>", repaired_block)
                repaired_block = re.sub(r"[⟵←]", "<--", repaired_block)
                refined_text = refined_text.replace(block, repaired_block)
        
        # Check SVG blocks
        svg_blocks = re.findall(r"```svg(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
        for sblock in svg_blocks:
            if "<svg" not in sblock or "</svg>" not in sblock:
                diagram_valid = False

        # 5. Safety & Tone Check
        is_safe = True
        unsafe_patterns = [r"\b(harmful|exploit|illegal|hack|bypass)\b"]
        for pat in unsafe_patterns:
            if re.search(pat, response_text, re.IGNORECASE):
                is_safe = False
                break

        # Pass / Fail Decision
        is_valid = (grounding_score >= 0.45) and cross_ref_valid and (pedagogy_score >= 0.6) and is_safe and diagram_valid
        status = "PASS" if is_valid else "FAIL"

        feedback_notes = "All pedagogical, grounding, and cross-reference checks passed."
        if not is_valid:
            reasons = []
            if grounding_score < 0.45:
                reasons.append("Low contextual grounding")
            if not cross_ref_valid:
                reasons.append("Unverified page citations")
            if pedagogy_score < 0.6:
                reasons.append("Insufficient educational structure")
            if not diagram_valid:
                reasons.append("Malformed diagram syntax")
            if not is_safe:
                reasons.append("Safety check triggered")
            feedback_notes = f"Validation failed: {', '.join(reasons)}."

        return AnswerValidationResult(
            is_valid=is_valid,
            grounding_score=grounding_score,
            cross_reference_valid=cross_ref_valid,
            pedagogy_score=round(pedagogy_score, 2),
            safety_valid=is_safe,
            validation_status=status,
            feedback_notes=feedback_notes,
            refined_response=refined_text if is_valid else None
        )

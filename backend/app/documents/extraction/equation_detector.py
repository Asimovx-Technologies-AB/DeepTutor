"""
Equation Detector — Mathematical formula and equation detection.

Detects inline and display math via regex patterns, and uses VLM
for image-based equation-to-LaTeX conversion.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.documents.models import EquationData

logger = logging.getLogger(__name__)

# ─── Equation detection patterns ─────────────────────────────────────────────

# Display math: $$ ... $$ (possibly multiline)
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)

# LaTeX environments
_LATEX_ENVS = re.compile(
    r"\\begin\{(equation|align|gather|displaymath|eqnarray)\*?\}(.+?)\\end\{\1\*?\}",
    re.DOTALL | re.IGNORECASE,
)

# Inline math: $ ... $ (single line, not empty)
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)([^$\n]{2,80})\$(?!\$)")

# Common equation-like patterns in text (e.g., "E = mc²", "F = ma")
_TEXT_EQUATIONS = re.compile(
    r"(?:^|\s)([A-Za-z]\s*=\s*[A-Za-z0-9\s\+\-\*/\^\(\)]{3,50})(?:\s|$|[,.])",
    re.MULTILINE,
)

# VLM prompt for equation-to-LaTeX conversion
_EQUATION_VLM_PROMPT = (
    "This image contains a mathematical equation, formula, or expression. "
    "Convert it to LaTeX notation. Return ONLY the LaTeX code wrapped in "
    "dollar signs ($...$ for inline or $$...$$ for display). "
    "If you see multiple equations, separate them with newlines."
)


class EquationDetector:
    """Detects mathematical equations in text and images."""

    # ── Regex-based detection from text ───────────────────────────────────

    def detect_equations(
        self,
        text: str,
        page_num: int,
    ) -> List[EquationData]:
        """Detects equations in extracted page text using regex patterns.

        Args:
            text: Extracted text from a page.
            page_num: 1-based page number.

        Returns:
            List of EquationData with LaTeX representations.
        """
        if not text or len(text) < 5:
            return []

        equations: List[EquationData] = []
        seen_positions: set = set()

        # 1. Display math: $$ ... $$
        for match in _DISPLAY_MATH.finditer(text):
            pos = match.start()
            if pos not in seen_positions:
                seen_positions.add(pos)
                latex = match.group(1).strip()
                context = self._get_context(text, pos, 100)
                equations.append(EquationData(
                    page_num=page_num,
                    raw_text=match.group(0),
                    latex=f"$${latex}$$",
                    is_display=True,
                    context_text=context,
                ))

        # 2. LaTeX environments
        for match in _LATEX_ENVS.finditer(text):
            pos = match.start()
            if pos not in seen_positions:
                seen_positions.add(pos)
                env_name = match.group(1)
                content = match.group(2).strip()
                context = self._get_context(text, pos, 100)
                equations.append(EquationData(
                    page_num=page_num,
                    raw_text=match.group(0),
                    latex=f"\\begin{{{env_name}}}{content}\\end{{{env_name}}}",
                    is_display=True,
                    context_text=context,
                ))

        # 3. Inline math: $ ... $
        for match in _INLINE_MATH.finditer(text):
            pos = match.start()
            if pos not in seen_positions:
                seen_positions.add(pos)
                latex = match.group(1).strip()
                equations.append(EquationData(
                    page_num=page_num,
                    raw_text=match.group(0),
                    latex=f"${latex}$",
                    is_display=False,
                    context_text=self._get_context(text, pos, 60),
                ))

        return equations

    # ── VLM-based equation-to-LaTeX conversion ────────────────────────────

    async def interpret_formula_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> Optional[str]:
        """Converts an image-based equation to LaTeX using VLM.

        Args:
            image_bytes: Raw bytes of the equation image.
            mime_type: MIME type of the image.

        Returns:
            LaTeX string or None if conversion fails.
        """
        try:
            from app.rag.vlm_client import vlm_client

            # Use the VLM with a formula-specific prompt
            result = await vlm_client.extract_text_from_image(
                image_bytes,
                mime_type=mime_type,
                context_hint=_EQUATION_VLM_PROMPT,
            )
            if result and result.strip():
                return result.strip()
        except Exception as exc:
            logger.warning("[EquationDetector] VLM formula interpretation error: %s", exc)

        return None

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _get_context(text: str, position: int, window: int = 100) -> str:
        """Extracts surrounding context text for an equation."""
        start = max(0, position - window)
        end = min(len(text), position + window)
        return text[start:end].strip()

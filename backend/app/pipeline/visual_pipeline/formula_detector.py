import re
from typing import List, Tuple
from app.schemas.layout import LayoutBlock, FormulaAsset


class FormulaDetector:
    """
    Branch B: Formula & Equation Detection -> Formula Recognizer (LaTeX).
    Detects inline and display mathematical formulas in text and visual blocks,
    and formats them into standardized LaTeX ($...$ and $$...$$).
    """

    MATH_PATTERNS = [
        # Display equations like "E = mc^2", "f(x) = ...", integrals, sums
        r"(?:(?:[a-zA-Z]\s*=\s*[^,\n]+)|(?:\b(?:sin|cos|tan|log|ln|lim|det)\b)|(?:[∑∫∏√∂∇≤≥≠≈±]))",
        # LaTeX fragments like \frac, \sqrt, \alpha, etc.
        r"\\[a-zA-Z]+(?:\{[^}]*\})*",
        # Superscript / subscript patterns like x_{i+1} or x^2
        r"[a-zA-Z0-9]_\{?[a-zA-Z0-9+\-]+\}?|[a-zA-Z0-9]\^\{?[a-zA-Z0-9+\-]+\}?",
    ]

    GREEK_AND_SYMBOLS = {
        "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "θ": r"\theta",
        "λ": r"\lambda", "μ": r"\mu", "π": r"\pi", "σ": r"\sigma", "ω": r"\omega",
        "Σ": r"\sum", "Π": r"\prod", "∫": r"\int", "√": r"\sqrt", "∂": r"\partial",
        "≤": r"\le", "≥": r"\ge", "≠": r"\neq", "≈": r"\approx", "±": r"\pm",
        "×": r"\times", "÷": r"\div", "∞": r"\infty"
    }

    @classmethod
    def detect_formulas(cls, blocks: List[LayoutBlock], page_number: int) -> Tuple[List[FormulaAsset], List[LayoutBlock]]:
        """
        Scans layout blocks for standalone display formulas and extracts them as FormulaAssets.
        Returns (extracted_formulas, modified_blocks).
        """
        formulas: List[FormulaAsset] = []
        formula_idx = 0

        for block in blocks:
            text = block.text.strip()
            
            # Check if entire block is a mathematical equation
            is_display_eq = False
            if len(text.split("\n")) <= 3:
                # Contains equality or inequality sign with math symbols
                if any(sym in text for sym in ["=", "<", ">", "≤", "≥", "≈", "∫", "∑"]):
                    # High density of math tokens
                    math_chars = sum(1 for c in text if c in cls.GREEK_AND_SYMBOLS or c in "^_{}[]()=+-/*")
                    if math_chars >= 3 or ("=" in text and any(re.search(pat, text) for pat in cls.MATH_PATTERNS)):
                        is_display_eq = True

            if is_display_eq:
                latex_expr = cls.convert_to_latex(text)
                formula_asset = FormulaAsset(
                    formula_index=formula_idx,
                    page_number=page_number,
                    bbox=block.bbox,
                    latex=latex_expr,
                    is_display_mode=True,
                    confidence=0.92,
                )
                formulas.append(formula_asset)
                formula_idx += 1
                block.block_type = "formula"
                block.text = f"$${latex_expr}$$"

        return formulas, blocks

    @classmethod
    def convert_to_latex(cls, expr: str) -> str:
        """Converts raw mathematical text to standard LaTeX."""
        cleaned = expr.strip()
        # If already enclosed in LaTeX delimiters, strip them
        if cleaned.startswith("$$") and cleaned.endswith("$$"):
            cleaned = cleaned[2:-2].strip()
        elif cleaned.startswith("$") and cleaned.endswith("$"):
            cleaned = cleaned[1:-1].strip()

        # Replace Greek and math symbols with LaTeX commands
        for sym, lat in cls.GREEK_AND_SYMBOLS.items():
            cleaned = cleaned.replace(sym, lat + " ")

        # Format fractions if like a/b
        cleaned = re.sub(r"\b([a-zA-Z0-9]+)\s*/\s*([a-zA-Z0-9]+)\b", r"\\frac{\1}{\2}", cleaned)
        
        # Cleanup extra spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

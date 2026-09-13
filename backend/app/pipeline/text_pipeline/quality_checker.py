import re
import string
from typing import Dict, Any, Tuple
from app.core.config import settings


class TextQualityChecker:
    """
    Branch A: Text Quality Check (Decision Diamond).
    Evaluates extracted page text to decide if native digital text is 'GOOD'
    or if it is 'POOR/SCANNED' requiring VLM OCR Fallback.
    """

    @classmethod
    def evaluate_quality(cls, text: str) -> Tuple[float, str]:
        """
        Returns (quality_score: float, decision: 'GOOD' | 'POOR').
        Score is 0.0 (unusable/corrupted/empty) to 1.0 (flawless digital text).
        """
        if not text or not text.strip():
            return 0.0, "POOR"

        cleaned = text.strip()
        total_chars = len(cleaned)
        if total_chars < 50:
            return 0.2, "POOR"

        # 1. Printable characters ratio
        printable_count = sum(1 for c in cleaned if c in string.printable)
        printable_ratio = printable_count / total_chars

        # 2. Alphabetic ratio (natural language should have healthy letter ratio)
        alpha_count = sum(1 for c in cleaned if c.isalpha())
        alpha_ratio = alpha_count / total_chars

        # 3. OCR noise detection: isolated symbols, weird repeated punctuation
        noise_pattern = re.compile(r"([~`|_\^\\/]{2,}|[^\w\s]{4,})")
        noise_matches = len(noise_pattern.findall(cleaned))
        noise_penalty = min(noise_matches * 0.05, 0.4)

        # 4. Average word length check (too long or too short indicates garbled text)
        words = cleaned.split()
        if words:
            avg_word_len = sum(len(w) for w in words) / len(words)
            word_len_penalty = 0.0
            if avg_word_len < 2.0 or avg_word_len > 15.0:
                word_len_penalty = 0.25
        else:
            word_len_penalty = 0.5

        raw_score = (printable_ratio * 0.4) + (alpha_ratio * 0.6) - noise_penalty - word_len_penalty
        score = max(0.0, min(1.0, raw_score))

        decision = "GOOD" if score >= settings.TEXT_QUALITY_OCR_THRESHOLD else "POOR"
        return round(score, 3), decision

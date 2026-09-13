import re
import string
from typing import Tuple, Dict, Any


class QueryPreprocessor:
    """
    Stage 1: Query Preprocessing.
    - Language Detection
    - Text Normalization
    - Spelling & Typo Handling
    - Token & Input Validation
    """

    COMMON_MATH_TERMS = {
        "derivative", "integral", "matrix", "vector", "gradient", "algorithm",
        "regression", "classification", "probability", "statistics", "calculus",
        "optimization", "equation", "function", "hypothesis", "variance", "tensor"
    }

    TYPO_CORRECTIONS = {
        "algoritm": "algorithm",
        "derivitave": "derivative",
        "integrel": "integral",
        "optmization": "optimization",
        "regresion": "regression",
        "vecter": "vector",
        "matrx": "matrix",
        "fomula": "formula",
        "theorum": "theorem",
        "difinition": "definition",
        "exmple": "example",
    }

    @classmethod
    def preprocess(cls, raw_query: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Processes raw user input.
        Returns: (normalized_query, language, validation_metadata)
        """
        if not raw_query or not raw_query.strip():
            raise ValueError("Query cannot be empty.")

        cleaned = raw_query.strip()
        
        # 1. Input Validation
        if len(cleaned) < 2:
            raise ValueError("Query is too short.")
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000]

        # 2. Language Detection (simple heuristic)
        language = cls._detect_language(cleaned)

        # 3. Normalization: strip consecutive spaces, normalize quotes
        normalized = re.sub(r"[ \t]+", " ", cleaned)
        normalized = normalized.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

        # 4. Spelling / Typo Handling
        words = normalized.split()
        corrected_words = []
        has_typos_fixed = False

        for word in words:
            # Strip trailing punctuation for checking
            stripped = word.strip(string.punctuation).lower()
            if stripped in cls.TYPO_CORRECTIONS:
                fixed = cls.TYPO_CORRECTIONS[stripped]
                # Preserve capitalization
                if word[0].isupper():
                    fixed = fixed.capitalize()
                corrected_words.append(fixed)
                has_typos_fixed = True
            else:
                corrected_words.append(word)

        final_normalized = " ".join(corrected_words)

        validation_meta = {
            "raw_length": len(raw_query),
            "normalized_length": len(final_normalized),
            "has_typos_fixed": has_typos_fixed,
            "language": language,
            "token_count_approx": len(final_normalized.split()),
        }

        return final_normalized, language, validation_meta

    @staticmethod
    def _detect_language(text: str) -> str:
        # Check non-ASCII characters ratio
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        ratio = ascii_chars / len(text)
        if ratio > 0.8:
            return "english"
        return "multilingual"

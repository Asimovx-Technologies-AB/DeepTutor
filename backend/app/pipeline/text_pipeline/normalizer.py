import re
import unicodedata


class TextNormalizer:
    """
    Branch A: Text Normalization.
    Performs Unicode NFKC normalization, hyphenation unwrapping across lines,
    ligature resolution, and header/footer cleanup.
    """

    LIGATURES = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬆ": "st",
        "ﬅ": "ft",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
    }

    @classmethod
    def normalize(cls, text: str) -> str:
        if not text:
            return ""

        # 1. Unicode NFKC normalization
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Ligature replacements
        for lig, repl in cls.LIGATURES.items():
            normalized = normalized.replace(lig, repl)

        # 3. De-hyphenate words broken across linebreaks: e.g. "compon-\nent" -> "component"
        normalized = re.sub(r"(\w+)-\n(\w+)", r"\1\2", normalized)

        # 4. Remove isolated line breaks within sentences (preserving paragraph breaks)
        # Convert double newlines to temporary marker
        paragraphs = normalized.split("\n\n")
        cleaned_paragraphs = []
        for p in paragraphs:
            # Replace single newlines inside a paragraph with a space
            single_line = re.sub(r"(?<!\n)\n(?!\n)", " ", p)
            # Normalize multiple spaces
            clean_p = re.sub(r"[ \t]+", " ", single_line).strip()
            if clean_p:
                cleaned_paragraphs.append(clean_p)

        result = "\n\n".join(cleaned_paragraphs)

        # 5. Remove trailing standalone page numbers (e.g. "\n 12 \n" or "Page 12 of 40")
        result = re.sub(r"\n\s*(?:Page\s+)?\d+(?:\s+of\s+\d+)?\s*\n", "\n", result, flags=re.IGNORECASE)

        return result.strip()

"""
Table Detector — Structured table extraction from PDF pages.

Uses pdfplumber for table detection, extracts headers/rows, and
formats as Markdown.  Matches table titles from surrounding text.
"""
from __future__ import annotations

import logging
import re
from typing import Any, List

from app.documents.models import TableData

logger = logging.getLogger(__name__)


class TableDetector:
    """Detects and extracts tables from PDF pages using pdfplumber."""

    def detect_tables(
        self,
        file_path: str,
        page_num: int,
    ) -> List[TableData]:
        """Extracts all tables from a single PDF page.

        Args:
            file_path: Path to PDF file.
            page_num: 1-based page number.

        Returns:
            List of TableData with markdown formatting.
        """
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                if page_num - 1 >= len(pdf.pages):
                    return []

                page = pdf.pages[page_num - 1]
                tables = page.extract_tables()
                if not tables:
                    return []

                # Extract page text for table title matching
                page_text = page.extract_text() or ""
                table_titles = re.findall(
                    r"\b(Table\s*\d+(?:\.\d+)?(?::[^\n]+)?)\b",
                    page_text,
                    re.IGNORECASE,
                )

                results: List[TableData] = []
                for t_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue

                    headers = self._clean_row(table[0])
                    rows = [self._clean_row(row) for row in table[1:] if any(row)]
                    markdown = self._format_markdown(headers, rows)

                    if not markdown.strip():
                        continue

                    title = (
                        table_titles[t_idx].strip()
                        if t_idx < len(table_titles)
                        else f"Table {t_idx + 1}"
                    )

                    results.append(TableData(
                        page_num=page_num,
                        table_index=t_idx + 1,
                        title=title,
                        headers=headers,
                        rows=rows,
                        markdown=markdown,
                        row_count=len(rows),
                        col_count=len(headers),
                    ))

                return results

        except Exception as exc:
            logger.warning("[TableDetector] Table extraction error p%d: %s", page_num, exc)
            return []

    # ── Row cleaning ──────────────────────────────────────────────────────

    @staticmethod
    def _clean_row(row: List[Any]) -> List[str]:
        """Cleans a table row: strips whitespace, replaces None, normalises newlines."""
        return [
            str(cell).replace("\n", " ").strip() if cell is not None else ""
            for cell in row
        ]

    # ── Markdown formatting ───────────────────────────────────────────────

    @staticmethod
    def _format_markdown(
        headers: List[str],
        rows: List[List[str]],
    ) -> str:
        """Converts headers + rows into a clean Markdown table string."""
        if not headers:
            return ""

        col_count = len(headers)

        # If headers are all empty, generate generic labels
        if not any(headers):
            headers = [f"Col {i + 1}" for i in range(col_count)]

        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * col_count) + " |")

        for row in rows:
            # Pad or trim row to match header count
            padded = row + [""] * (col_count - len(row)) if len(row) < col_count else row[:col_count]
            lines.append("| " + " | ".join(padded) + " |")

        return "\n".join(lines)

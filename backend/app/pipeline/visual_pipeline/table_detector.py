import re
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.layout import LayoutBlock, TableAsset


class TableDetector:
    """
    Branch B: Table Detection & Structured Extraction.
    Identifies tabular blocks, parses rows and columns,
    and converts them into Markdown and HTML tabular representations.
    """

    @classmethod
    def detect_tables(
        cls,
        blocks: List[LayoutBlock],
        page_number: int,
        native_tables: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[TableAsset], List[LayoutBlock]]:
        """
        Detects tables from native vector PDF table structures and layout text blocks.
        Returns (extracted_tables, remaining_non_table_blocks).
        """
        tables: List[TableAsset] = []
        regular_blocks: List[LayoutBlock] = []
        table_idx = 0

        # 1. Incorporate native vector tables extracted directly by PyMuPDF
        if native_tables:
            for nt in native_tables:
                tables.append(TableAsset(
                    table_index=table_idx,
                    page_number=page_number,
                    bbox=nt.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                    markdown=nt.get("markdown", ""),
                    html=nt.get("html", ""),
                    headers=nt.get("headers", []),
                    rows=nt.get("rows", []),
                    confidence=nt.get("confidence", 1.0),
                ))
                table_idx += 1

        for block in blocks:
            text = block.text.strip()
            lines = text.split("\n")

            # Check if text looks like a tabular structure:
            # 1. Has multiple columns separated by 2+ spaces or tabs
            # 2. Or has pipe '|' characters
            # 3. Has at least 2 lines and multiple columns per line
            is_table = False
            parsed_rows: List[List[str]] = []

            if len(lines) >= 2:
                row_candidates = []
                for line in lines:
                    line = line.strip()
                    if "|" in line:
                        parts = [p.strip() for p in line.split("|") if p.strip()]
                    else:
                        parts = [p.strip() for p in re.split(r"\s{2,}|\t+", line) if p.strip()]

                    if len(parts) >= 2:
                        row_candidates.append(parts)

                if len(row_candidates) >= 2 and len(row_candidates) >= len(lines) * 0.7:
                    # Check column count consistency
                    col_counts = [len(r) for r in row_candidates]
                    if max(col_counts) - min(col_counts) <= 1:
                        is_table = True
                        parsed_rows = row_candidates

            if is_table:
                # Build Markdown representation
                headers = parsed_rows[0]
                rows = parsed_rows[1:]
                
                md_lines = [
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join(["---"] * len(headers)) + " |",
                ]
                for r in rows:
                    # Pad row if missing columns
                    padded = r + [""] * (len(headers) - len(r))
                    md_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")

                markdown_str = "\n".join(md_lines)
                
                # Build HTML representation
                html_rows = [f"<tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"]
                for r in rows:
                    padded = r + [""] * (len(headers) - len(r))
                    html_rows.append(f"<tr>{''.join(f'<td>{c}</td>' for c in padded[:len(headers)])}</tr>")
                html_str = f"<table>\n<thead>{html_rows[0]}</thead>\n<tbody>{''.join(html_rows[1:])}</tbody>\n</table>"

                table_asset = TableAsset(
                    table_index=table_idx,
                    page_number=page_number,
                    bbox=block.bbox,
                    markdown=markdown_str,
                    html=html_str,
                    headers=headers,
                    rows=rows,
                    confidence=0.95,
                )
                tables.append(table_asset)
                table_idx += 1
            else:
                regular_blocks.append(block)

        return tables, regular_blocks

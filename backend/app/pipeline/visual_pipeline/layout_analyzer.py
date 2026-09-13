from typing import List, Dict, Any
from app.schemas.layout import LayoutBlock


class LayoutAnalyzer:
    """
    Branch B: Layout Analysis.
    Detects page geometry, column layouts (single vs two-column),
    and reconstructs true natural reading order.
    """

    @classmethod
    def analyze_page_layout(cls, blocks: List[LayoutBlock], page_width: float, page_height: float) -> List[LayoutBlock]:
        if not blocks:
            return []

        # 1. Detect if the page has a two-column structure
        mid_x = page_width / 2.0
        left_col_blocks: List[LayoutBlock] = []
        right_col_blocks: List[LayoutBlock] = []
        span_both_blocks: List[LayoutBlock] = []

        for b in blocks:
            x0, y0, x1, y1 = b.bbox
            # Header or footer across full page width
            if (x1 - x0) > 0.7 * page_width:
                span_both_blocks.append(b)
            elif x1 <= mid_x + 20:
                left_col_blocks.append(b)
            elif x0 >= mid_x - 20:
                right_col_blocks.append(b)
            else:
                span_both_blocks.append(b)

        # If there are distinct left and right columns, sort reading order accordingly
        is_two_column = len(left_col_blocks) >= 2 and len(right_col_blocks) >= 2

        if is_two_column:
            # Top spanning blocks (e.g. titles), then left column top-to-bottom, then right column, then bottom spanning
            top_spanning = [b for b in span_both_blocks if b.bbox[1] < page_height * 0.25]
            bottom_spanning = [b for b in span_both_blocks if b.bbox[1] >= page_height * 0.25]

            top_spanning.sort(key=lambda b: b.bbox[1])
            left_col_blocks.sort(key=lambda b: b.bbox[1])
            right_col_blocks.sort(key=lambda b: b.bbox[1])
            bottom_spanning.sort(key=lambda b: b.bbox[1])

            ordered_blocks = top_spanning + left_col_blocks + right_col_blocks + bottom_spanning
        else:
            # Single-column: sort primarily by vertical y0 coordinate
            ordered_blocks = sorted(blocks, key=lambda b: (round(b.bbox[1] / 10.0) * 10, b.bbox[0]))

        # Re-assign reading order indices
        for idx, block in enumerate(ordered_blocks):
            block.reading_order = idx

        return ordered_blocks

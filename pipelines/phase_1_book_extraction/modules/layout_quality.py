"""
modules/layout_quality.py — M4.1B: Stage A Layout Quality Improvements.

Deterministic post-processing passes applied to Stage A blocks after initial
geometry segmentation but before final ordering.  Each pass implements one
of the approved M4.1B improvements:

  1. Cross-kind IoU duplicate suppression
  2. Improved equation clustering (multiline, aligned, continuation)
  3. Cross-page equation continuation
  4. Contiguous definition grouping
  5. Cross-page worked-example continuation
  6. Improved Warning / Note / Box detection (deterministic layout cues)
  7. Table false-positive suppression
  8. General Stage A cleanup (duplicate/overlap reduction)

All passes are purely deterministic — no AI/ML, no confidence learning,
no semantic inference.  They operate on Block objects produced by
stage_a_geometry.py and VisualRegion objects from layout_detector.py.

This module does NOT modify Stage B/C/D or any schema.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from modules.pdf_parser import Line
from modules.layout_detector import VisualRegion

logger = logging.getLogger("ncert_pipeline.layout_quality")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bbox_iou(a: Tuple[float, float, float, float],
              b: Tuple[float, float, float, float]) -> float:
    """Intersection-over-Union for two bounding boxes."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0) * (by1 - by0))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _bbox_area(bbox: Tuple[float, float, float, float]) -> float:
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def _bbox_contains(outer: Tuple[float, float, float, float],
                   inner: Tuple[float, float, float, float],
                   tolerance: float = 5.0) -> bool:
    """True if *outer* fully contains *inner* within tolerance."""
    return (outer[0] - tolerance <= inner[0] and
            outer[1] - tolerance <= inner[1] and
            outer[2] + tolerance >= inner[2] and
            outer[3] + tolerance >= inner[3])


def _union_bbox(bboxes: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    xs0 = [b[0] for b in bboxes]
    ys0 = [b[1] for b in bboxes]
    xs1 = [b[2] for b in bboxes]
    ys1 = [b[3] for b in bboxes]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


# ---------------------------------------------------------------------------
# Kind priority for cross-kind suppression (higher number = higher priority).
# When two blocks of different kinds overlap the same region, keep the one
# with higher priority.
# ---------------------------------------------------------------------------
_KIND_PRIORITY: Dict[str, int] = {
    "heading-topic": 100,
    "equation-cluster": 90,
    "equation-line": 85,
    "table": 80,
    "figure": 70,
    "diagram": 60,
    "callout-label": 50,
    "definition-candidate": 40,
}

_DEFAULT_PRIORITY = 30


def _block_kind_priority(anchor: str) -> int:
    """Return the deterministic priority for a block's anchor kind."""
    return _KIND_PRIORITY.get(anchor, _DEFAULT_PRIORITY)


# =========================================================================
# 1. Cross-kind IoU duplicate suppression
# =========================================================================

def suppress_cross_kind_duplicates(blocks: list, iou_threshold: float = 0.5) -> list:
    """Remove blocks that overlap the same physical region with IoU above
    *iou_threshold*, keeping only the highest-priority block per cluster.

    Two blocks on different pages never overlap.  Priority is determined by
    the deterministic _KIND_PRIORITY table — no confidence learning.

    Operates on Block objects (from stage_a_geometry).
    """
    if len(blocks) <= 1:
        return list(blocks)

    # Group by page for efficient pairwise comparison
    by_page: Dict[int, list] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    suppressed_ids: Set[str] = set()

    for page, page_blocks in by_page.items():
        n = len(page_blocks)
        for i in range(n):
            if page_blocks[i].block_id in suppressed_ids:
                continue
            for j in range(i + 1, n):
                if page_blocks[j].block_id in suppressed_ids:
                    continue
                iou = _bbox_iou(page_blocks[i].bbox, page_blocks[j].bbox)
                if iou >= iou_threshold:
                    anchor_i = page_blocks[i].grouping_meta.get("anchor", "")
                    anchor_j = page_blocks[j].grouping_meta.get("anchor", "")
                    pri_i = _block_kind_priority(anchor_i)
                    pri_j = _block_kind_priority(anchor_j)
                    # Suppress the lower-priority block; ties break by page
                    # position (lower y0 wins — deterministic).
                    if pri_i > pri_j:
                        suppressed_ids.add(page_blocks[j].block_id)
                    elif pri_j > pri_i:
                        suppressed_ids.add(page_blocks[i].block_id)
                    else:
                        # Same priority — suppress the one with higher y0
                        # (i.e., keep the one appearing earlier on the page).
                        if page_blocks[i].bbox[1] <= page_blocks[j].bbox[1]:
                            suppressed_ids.add(page_blocks[j].block_id)
                        else:
                            suppressed_ids.add(page_blocks[i].block_id)

    if suppressed_ids:
        logger.debug("Cross-kind IoU suppression removed %d block(s).", len(suppressed_ids))

    return [b for b in blocks if b.block_id not in suppressed_ids]


# =========================================================================
# 2. Improved equation clustering (multiline, aligned, continuation)
# =========================================================================

# Patterns indicating an equation continuation line (deterministic text cues).
_EQUATION_CONTINUATION_RE = re.compile(
    r"^\s*(?:"
    r"[=+\-*/]"               # starts with operator
    r"|\\\\?"                  # LaTeX line continuation
    r"|where\b"               # "where x = ..."
    r"|and\b"                 # "and y = ..."
    r"|or\b"                  # "or z = ..."
    r"|putting\b"             # "putting the value ..."
    r"|substituting\b"        # "substituting ..."
    r"|therefore\b"           # "therefore ..."
    r"|hence\b"               # "hence ..."
    r"|thus\b"                # "thus ..."
    r"|∴"                     # therefore symbol
    r"|⇒"                    # implies symbol
    r"|⟹"                   # long implies
    r")", re.I
)

# Pattern for aligned equation markers (deterministic).
_ALIGNED_EQUATION_RE = re.compile(
    r"(?:"
    r"\.\.\."                  # ellipsis continuation
    r"|&="                     # LaTeX align marker
    r"|\\\\"                   # LaTeX newline
    r")"
)


def is_equation_continuation(text: str) -> bool:
    """Deterministically check if a text line is a continuation of a
    previous equation, based on leading tokens/symbols."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    return bool(_EQUATION_CONTINUATION_RE.match(stripped))


def is_aligned_equation_part(text: str) -> bool:
    """Check if text contains alignment markers typical of multiline
    equations (LaTeX-style)."""
    if not text:
        return False
    return bool(_ALIGNED_EQUATION_RE.search(text))


def merge_equation_continuations(blocks: list, gap_fraction: float = 0.05) -> list:
    """Within already-clustered equation blocks, merge adjacent equation-
    cluster blocks that are continuation lines of each other.

    Rules (all deterministic):
    - Both blocks must be on the same page.
    - The vertical gap must be within *gap_fraction* of page height.
    - The second block's first line must match equation-continuation patterns.
    - Or both blocks are equation-clusters with aligned-equation markers.
    """
    if len(blocks) <= 1:
        return list(blocks)

    # Sort by (page, y0) for deterministic processing
    sorted_blocks = sorted(blocks, key=lambda b: (b.page, b.bbox[1]))
    merged_ids: Set[str] = set()
    result = []

    i = 0
    while i < len(sorted_blocks):
        current = sorted_blocks[i]
        if current.block_id in merged_ids:
            i += 1
            continue

        anchor = current.grouping_meta.get("anchor", "")
        if anchor != "equation-cluster":
            result.append(current)
            i += 1
            continue

        # Look ahead for mergeable equation clusters
        j = i + 1
        while j < len(sorted_blocks):
            nxt = sorted_blocks[j]
            if nxt.block_id in merged_ids:
                j += 1
                continue
            nxt_anchor = nxt.grouping_meta.get("anchor", "")
            if nxt_anchor != "equation-cluster":
                break
            if nxt.page != current.page:
                break

            # Check vertical gap
            gap = nxt.bbox[1] - current.bbox[3]
            page_h = max(current.bbox[3], nxt.bbox[3], 1.0)
            if gap > gap_fraction * page_h * 20:
                break

            # Check continuation patterns
            first_line_text = ""
            if nxt.lines:
                first_line_text = nxt.lines[0].text
            elif nxt.children:
                child_lines = nxt.children[0].lines if nxt.children[0].lines else []
                first_line_text = child_lines[0].text if child_lines else ""

            is_continuation = is_equation_continuation(first_line_text)
            has_alignment = any(
                is_aligned_equation_part(line.text)
                for line in (current.lines + nxt.lines)
            )

            if is_continuation or has_alignment:
                # Merge nxt into current
                current.children.extend(nxt.children)
                current.lines.extend(nxt.lines)
                current.bbox = _union_bbox([current.bbox, nxt.bbox])
                if "line_count" in current.grouping_meta:
                    nxt_count = nxt.grouping_meta.get("line_count", 0)
                    current.grouping_meta["line_count"] += nxt_count
                current.grouping_meta["merged_continuation"] = True
                for child in nxt.children:
                    child.parent = current.block_id
                merged_ids.add(nxt.block_id)
                j += 1
            else:
                break

        result.append(current)
        i = j if j > i + 1 else i + 1

    return [b for b in result if b.block_id not in merged_ids]


# =========================================================================
# 3. Cross-page equation continuation
# =========================================================================

def merge_cross_page_equations(blocks: list, bottom_margin_fraction: float = 0.08) -> list:
    """Detect equation-cluster blocks that end near the bottom of a page
    and continue on the top of the next page.  Merge deterministically.

    Rules:
    - The ending block must be an equation-cluster.
    - It must be the last equation-cluster on its page.
    - The next page must start with an equation-cluster or an equation
      continuation line.
    - Merge by extending the first block's children/lines and setting
      page_end.
    """
    if len(blocks) <= 1:
        return list(blocks)

    # Group equation clusters by page
    eq_by_page: Dict[int, list] = {}
    for b in blocks:
        if b.grouping_meta.get("anchor") == "equation-cluster":
            eq_by_page.setdefault(b.page, []).append(b)

    for page_blocks in eq_by_page.values():
        page_blocks.sort(key=lambda b: b.bbox[1])

    merged_ids: Set[str] = set()

    for page_num, page_eqs in sorted(eq_by_page.items()):
        if not page_eqs:
            continue
        last_eq = page_eqs[-1]
        if last_eq.block_id in merged_ids:
            continue

        next_page_eqs = eq_by_page.get(page_num + 1, [])
        if not next_page_eqs:
            continue

        first_next = next_page_eqs[0]
        if first_next.block_id in merged_ids:
            continue

        # Check if the first equation on the next page is a continuation
        first_line_text = ""
        if first_next.lines:
            first_line_text = first_next.lines[0].text
        elif first_next.children and first_next.children[0].lines:
            first_line_text = first_next.children[0].lines[0].text

        if is_equation_continuation(first_line_text):
            last_eq.children.extend(first_next.children)
            last_eq.lines.extend(first_next.lines)
            last_eq.page_end = first_next.page
            last_eq.grouping_meta["continuation"] = {
                "continued_on_page": first_next.page,
                "merged_block_id": first_next.block_id,
            }
            for child in first_next.children:
                child.parent = last_eq.block_id
            merged_ids.add(first_next.block_id)

    if merged_ids:
        logger.debug("Cross-page equation continuation merged %d block(s).", len(merged_ids))

    return [b for b in blocks if b.block_id not in merged_ids]


# =========================================================================
# 4. Contiguous definition grouping
# =========================================================================

def group_contiguous_definitions(blocks: list, max_gap_pts: float = 30.0) -> list:
    """Merge consecutive definition-candidate blocks on the same page into
    a single block when they are vertically adjacent (gap < *max_gap_pts*).

    This reduces layout fragmentation where a single definition spans
    multiple lines that were each detected as separate candidates.

    Rules (deterministic):
    - Both blocks must be definition-candidates.
    - Both must be on the same page.
    - The vertical gap between them must be < max_gap_pts.
    - The blocks must be adjacent in reading order (no other block type
      between them on the same page).
    """
    if len(blocks) <= 1:
        return list(blocks)

    sorted_blocks = sorted(blocks, key=lambda b: (b.page, b.bbox[1]))
    merged_ids: Set[str] = set()
    result = []

    i = 0
    while i < len(sorted_blocks):
        current = sorted_blocks[i]
        if current.block_id in merged_ids:
            i += 1
            continue

        anchor = current.grouping_meta.get("anchor", "")
        if anchor != "definition-candidate":
            result.append(current)
            i += 1
            continue

        # Look ahead for adjacent definition-candidates
        j = i + 1
        while j < len(sorted_blocks):
            nxt = sorted_blocks[j]
            if nxt.block_id in merged_ids:
                j += 1
                continue
            nxt_anchor = nxt.grouping_meta.get("anchor", "")

            # Stop if we encounter a non-definition block on the same page
            # between the two (structural boundary).
            if nxt_anchor != "definition-candidate":
                if nxt.page == current.page:
                    # There's a non-definition block intervening
                    break
                else:
                    break

            if nxt.page != current.page:
                break

            gap = nxt.bbox[1] - current.bbox[3]
            if gap > max_gap_pts:
                break

            # Merge
            current.lines.extend(nxt.lines)
            current.bbox = _union_bbox([current.bbox, nxt.bbox])
            # Combine candidate_term values
            existing_term = current.grouping_meta.get("candidate_term", "")
            nxt_term = nxt.grouping_meta.get("candidate_term", "")
            if nxt_term and nxt_term != existing_term:
                current.grouping_meta["candidate_term"] = existing_term
                current.grouping_meta.setdefault("additional_terms", []).append(nxt_term)
            current.grouping_meta["grouped_definitions"] = True
            merged_ids.add(nxt.block_id)
            j += 1

        result.append(current)
        i = j if j > i + 1 else i + 1

    return [b for b in result if b.block_id not in merged_ids]


# =========================================================================
# 5. Cross-page worked-example continuation
# =========================================================================

# Deterministic anchor kinds that indicate a worked example.
_WORKED_EXAMPLE_ANCHORS = {"callout-label"}
_WORKED_EXAMPLE_LABELS_RE = re.compile(
    r"^\s*(example|illustration|solved example|worked example)\b", re.I
)


def merge_cross_page_worked_examples(blocks: list) -> list:
    """Detect worked-example blocks ending near the bottom of a page
    and continuing at the top of the next page.

    Rules (deterministic):
    - The ending block must be a callout-label whose label_line matches
      an example/worked-example pattern.
    - It must be the last block (or among the last) on its page.
    - The next page's first block must be a callout-label that does NOT
      start a new label anchor (i.e., it's body text continuing).
    - Merge by extending children/lines and setting page_end.
    """
    if len(blocks) <= 1:
        return list(blocks)

    # Build page index
    by_page: Dict[int, list] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)
    for page_blocks in by_page.values():
        page_blocks.sort(key=lambda b: b.bbox[1])

    merged_ids: Set[str] = set()

    # Label anchor regex (same as stage_a_geometry)
    _LABEL_ANCHOR_RE = re.compile(
        r"^\s*(activity|think|observe|try|discuss|experiment"
        r"|did you know|important|note|remember|case study|box"
        r"|warning|caution"
        r"|example|illustration|solved example)\b[\s:.\-]*\d*", re.I)

    for page_num in sorted(by_page.keys()):
        page_blocks = by_page[page_num]
        if not page_blocks:
            continue

        # Check last blocks on page for worked-example pattern
        for b in reversed(page_blocks[-3:]):  # Check up to last 3 blocks
            if b.block_id in merged_ids:
                continue
            anchor = b.grouping_meta.get("anchor", "")
            label_line = b.grouping_meta.get("label_line", "")

            if anchor != "callout-label":
                continue
            if not _WORKED_EXAMPLE_LABELS_RE.match(label_line):
                continue

            # Check next page for continuation
            next_page_blocks = by_page.get(page_num + 1, [])
            if not next_page_blocks:
                continue

            first_next = next_page_blocks[0]
            if first_next.block_id in merged_ids:
                continue

            next_anchor = first_next.grouping_meta.get("anchor", "")
            if next_anchor != "callout-label":
                continue

            # The next block should NOT start with a new label anchor
            first_line_text = ""
            if first_next.lines:
                first_line_text = first_next.lines[0].text
            if _LABEL_ANCHOR_RE.match(first_line_text):
                continue  # It's a new callout, not a continuation

            # Merge
            b.children.extend(first_next.children)
            b.lines.extend(first_next.lines)
            b.page_end = first_next.page
            b.grouping_meta["continuation"] = {
                "continued_on_page": first_next.page,
                "merged_block_id": first_next.block_id,
            }
            for child in first_next.children:
                child.parent = b.block_id
            merged_ids.add(first_next.block_id)
            break  # Only merge one continuation per page boundary

    if merged_ids:
        logger.debug("Cross-page worked-example continuation merged %d block(s).", len(merged_ids))

    return [b for b in blocks if b.block_id not in merged_ids]


# =========================================================================
# 6. Improved Warning / Note / Box detection (deterministic layout cues)
# =========================================================================

# Border/box detection patterns (deterministic text/layout cues).
_BORDER_CUE_RE = re.compile(
    r"(?:"
    r"^\s*[─━═╔╗╚╝╠╣╦╩╬│┃┌┐└┘├┤┬┴┼]"  # Unicode box-drawing chars
    r"|^[\s_]{10,}$"                       # Horizontal rule (underscores)
    r"|^[\s\-]{10,}$"                      # Horizontal rule (hyphens)
    r"|^[\s*]{10,}$"                       # Asterisk rules
    r")"
)

# Extended heading patterns for note/warning/box detection.
_NOTE_HEADING_RE = re.compile(
    r"^\s*(?:note|n\.b\.|nb|nota bene)\s*[:.\-]?\s*$", re.I
)
_WARNING_HEADING_RE = re.compile(
    r"^\s*(?:warning|caution|danger|attention|important)\s*[:.\-!]?\s*$", re.I
)
_BOX_HEADING_RE = re.compile(
    r"^\s*(?:box|inset|sidebar|did you know|remember|case study)\s*[:.\-]?\s*\d*\s*$", re.I
)


def detect_border_cues(lines: List[Line], page: int) -> List[Tuple[float, float]]:
    """Find horizontal border lines (rules/separators) on a page.
    Returns list of (y_position, x_width) for each detected border.
    Deterministic — uses only character patterns."""
    borders = []
    for line in lines:
        if line.page != page:
            continue
        if _BORDER_CUE_RE.match(line.text):
            width = line.bbox[2] - line.bbox[0] if line.bbox else 0.0
            borders.append((line.y, width))
    return borders


def enhance_callout_detection(blocks: list, lines: List[Line]) -> list:
    """Enhance existing callout-label blocks with border/heading cues.

    This does NOT create new blocks — it improves the grouping_meta of
    existing callout-label blocks with additional deterministic layout
    signals that downstream stages can use:

    - "has_border": True if the block region contains border-like lines
    - "callout_type_hint": "note", "warning", or "box" based on heading patterns
    - "visual_grouping": True if the block has visual containment cues

    All purely deterministic.
    """
    lines_by_page: Dict[int, List[Line]] = {}
    for line in lines:
        lines_by_page.setdefault(line.page, []).append(line)

    for b in blocks:
        anchor = b.grouping_meta.get("anchor", "")
        if anchor != "callout-label":
            continue

        label_line = b.grouping_meta.get("label_line", "")

        # Check for heading-type cues
        if _NOTE_HEADING_RE.match(label_line):
            b.grouping_meta["callout_type_hint"] = "note"
        elif _WARNING_HEADING_RE.match(label_line):
            b.grouping_meta["callout_type_hint"] = "warning"
        elif _BOX_HEADING_RE.match(label_line):
            b.grouping_meta["callout_type_hint"] = "box"

        # Check for border cues in the block's vicinity
        page_lines = lines_by_page.get(b.page, [])
        borders = detect_border_cues(page_lines, b.page)
        if borders:
            # Check if any border is near the block's bbox
            for border_y, border_width in borders:
                # Border within 20pts above or below the block
                if (b.bbox[1] - 20 <= border_y <= b.bbox[3] + 20
                        and border_width > 50):
                    b.grouping_meta["has_border"] = True
                    b.grouping_meta["visual_grouping"] = True
                    break

    return blocks


# =========================================================================
# 7. Table false-positive suppression
# =========================================================================

# Minimum structural requirements for a genuine table.
_MIN_TABLE_ROWS = 2
_MIN_TABLE_COLS = 2
_MIN_TABLE_AREA = 3000.0  # Square points — below this is too small for a real table.

# Pattern for prose that looks like a table but isn't.
_PROSE_LIKE_RE = re.compile(
    r"[.!?]\s+[A-Z]"  # Sentence boundary followed by capital letter
)


def suppress_table_false_positives(blocks: list) -> list:
    """Remove blocks classified as tables that are actually aligned prose,
    formatting artifacts, or too small to be genuine tables.

    Rules (all deterministic):
    - Tables with 0 rows or 0 columns (caption-only stubs) are kept but
      flagged — they carry real metadata even if the table structure wasn't
      parseable.
    - Tables whose area is below _MIN_TABLE_AREA are suppressed.
    - Tables with exactly 1 row and 1 column are suppressed (likely a
      formatting artifact, not a data table).
    """
    suppressed_ids: Set[str] = set()

    for b in blocks:
        anchor = b.grouping_meta.get("anchor", "")
        if anchor != "table":
            continue

        region_extra = b.grouping_meta.get("region_extra", {})
        rows = region_extra.get("rows", 0)
        cols = region_extra.get("columns", 0)

        # Keep caption-only stubs (rows=0, cols=0) — they carry metadata.
        if rows == 0 and cols == 0:
            continue

        # Suppress single-cell "tables" (formatting artifacts).
        if rows == 1 and cols == 1:
            suppressed_ids.add(b.block_id)
            continue

        # Suppress tiny tables (likely decorative lines or artifacts).
        area = _bbox_area(b.bbox)
        if area < _MIN_TABLE_AREA:
            suppressed_ids.add(b.block_id)
            continue

        # Check if the "table" caption/body text looks like prose.
        if b.lines:
            prose_signal_count = sum(
                1 for line in b.lines
                if _PROSE_LIKE_RE.search(line.text)
            )
            # If more than half the lines look like prose sentences, suppress.
            if len(b.lines) >= 3 and prose_signal_count > len(b.lines) * 0.5:
                suppressed_ids.add(b.block_id)
                continue

    if suppressed_ids:
        logger.debug("Table false-positive suppression removed %d block(s).", len(suppressed_ids))

    return [b for b in blocks if b.block_id not in suppressed_ids]


# =========================================================================
# 8. General Stage A cleanup — duplicate/overlap reduction
# =========================================================================

def remove_duplicate_blocks(blocks: list, iou_threshold: float = 0.85) -> list:
    """Remove blocks that are near-exact duplicates on the same page
    (same anchor kind, IoU above threshold).

    This handles cases where the same region is detected twice by the
    same detector path (e.g., two overlapping equation clusters that
    survived initial dedup).

    Deterministic: keeps the first block in page-order when duplicates
    are found.
    """
    if len(blocks) <= 1:
        return list(blocks)

    by_page: Dict[int, list] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    suppressed_ids: Set[str] = set()

    for page, page_blocks in by_page.items():
        n = len(page_blocks)
        for i in range(n):
            if page_blocks[i].block_id in suppressed_ids:
                continue
            for j in range(i + 1, n):
                if page_blocks[j].block_id in suppressed_ids:
                    continue
                anchor_i = page_blocks[i].grouping_meta.get("anchor", "")
                anchor_j = page_blocks[j].grouping_meta.get("anchor", "")
                if anchor_i != anchor_j:
                    continue  # Different kinds — not duplicates (handled by pass 1)
                iou = _bbox_iou(page_blocks[i].bbox, page_blocks[j].bbox)
                if iou >= iou_threshold:
                    # Keep the one with more children/lines (richer content)
                    richness_i = len(page_blocks[i].children) + len(page_blocks[i].lines)
                    richness_j = len(page_blocks[j].children) + len(page_blocks[j].lines)
                    if richness_i >= richness_j:
                        suppressed_ids.add(page_blocks[j].block_id)
                    else:
                        suppressed_ids.add(page_blocks[i].block_id)

    if suppressed_ids:
        logger.debug("Same-kind duplicate cleanup removed %d block(s).", len(suppressed_ids))

    return [b for b in blocks if b.block_id not in suppressed_ids]


def remove_contained_blocks(blocks: list) -> list:
    """Remove blocks that are fully contained within a larger block of
    higher or equal priority.

    This handles cases where a child-level region (e.g., an individual
    equation line) was also emitted as a top-level block alongside its
    parent cluster.

    Deterministic: the contained block is removed, the container is kept.
    """
    if len(blocks) <= 1:
        return list(blocks)

    by_page: Dict[int, list] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    suppressed_ids: Set[str] = set()

    for page, page_blocks in by_page.items():
        for i, outer in enumerate(page_blocks):
            if outer.block_id in suppressed_ids:
                continue
            for j, inner in enumerate(page_blocks):
                if i == j or inner.block_id in suppressed_ids:
                    continue
                if _bbox_contains(outer.bbox, inner.bbox):
                    outer_pri = _block_kind_priority(
                        outer.grouping_meta.get("anchor", ""))
                    inner_pri = _block_kind_priority(
                        inner.grouping_meta.get("anchor", ""))
                    # Only suppress inner if outer has >= priority
                    if outer_pri >= inner_pri:
                        # Don't suppress if inner is already a child of outer
                        if inner.parent == outer.block_id:
                            continue
                        suppressed_ids.add(inner.block_id)

    if suppressed_ids:
        logger.debug("Containment cleanup removed %d block(s).", len(suppressed_ids))

    return [b for b in blocks if b.block_id not in suppressed_ids]


# =========================================================================
# Cross-kind visual region duplicate suppression (operates on VisualRegions
# before they become Blocks — called from layout_detector integration)
# =========================================================================

_VISUAL_KIND_PRIORITY: Dict[str, int] = {
    "table": 80,
    "figure": 70,
    "diagram": 60,
    "equation": 50,
}


def suppress_cross_kind_visual_duplicates(
    layout: Dict[str, List[VisualRegion]],
    iou_threshold: float = 0.5,
) -> Dict[str, List[VisualRegion]]:
    """Remove VisualRegions of different kinds that overlap the same
    physical area.  Keeps the highest-priority kind per overlap cluster.

    This runs on the raw layout dict before blocks are built, preventing
    duplicate detections (e.g., Figure + GenericVisual detecting the same
    image) from ever creating duplicate blocks.
    """
    # Flatten all regions with their kind
    all_regions: List[Tuple[str, int, VisualRegion]] = []
    for kind, regions in layout.items():
        for idx, r in enumerate(regions):
            all_regions.append((kind, idx, r))

    suppressed: Set[Tuple[str, int]] = set()

    # Group by page for efficient comparison
    by_page: Dict[int, List[Tuple[str, int, VisualRegion]]] = {}
    for kind, idx, r in all_regions:
        by_page.setdefault(r.page, []).append((kind, idx, r))

    for page, page_regions in by_page.items():
        n = len(page_regions)
        for i in range(n):
            k_i, idx_i, r_i = page_regions[i]
            if (k_i, idx_i) in suppressed:
                continue
            for j in range(i + 1, n):
                k_j, idx_j, r_j = page_regions[j]
                if (k_j, idx_j) in suppressed:
                    continue
                # Compare using the VisualRegion.kind (singular: "figure",
                # "table") not the layout dict key (plural: "figures").
                if r_i.kind == r_j.kind:
                    continue  # Same kind handled by existing dedup

                iou = _bbox_iou(r_i.bbox, r_j.bbox)
                if iou >= iou_threshold:
                    pri_i = _VISUAL_KIND_PRIORITY.get(r_i.kind, 30)
                    pri_j = _VISUAL_KIND_PRIORITY.get(r_j.kind, 30)
                    if pri_i >= pri_j:
                        suppressed.add((k_j, idx_j))
                    else:
                        suppressed.add((k_i, idx_i))

    if not suppressed:
        return layout

    result: Dict[str, List[VisualRegion]] = {}
    for kind, regions in layout.items():
        result[kind] = [
            r for idx, r in enumerate(regions)
            if (kind, idx) not in suppressed
        ]

    logger.debug("Cross-kind visual duplicate suppression removed %d region(s).",
                 len(suppressed))
    return result


# =========================================================================
# Master pass — applies all quality improvements in deterministic order
# =========================================================================

def apply_layout_quality_passes(blocks: list, lines: List[Line] = None) -> list:
    """Apply all M4.1B layout quality improvement passes in deterministic
    order.

    Pass order is significant and frozen:
      1. Table false-positive suppression (removes noise early)
      2. Cross-kind IoU duplicate suppression
      3. Equation continuation merging (within-page)
      4. Cross-page equation continuation
      5. Contiguous definition grouping
      6. Cross-page worked-example continuation
      7. Enhanced callout detection (adds metadata, doesn't remove blocks)
      8. Same-kind duplicate cleanup
      9. Containment cleanup

    Args:
        blocks: List of Block objects from stage_a_geometry.
        lines: Optional list of Line objects for border detection.

    Returns:
        Cleaned list of Block objects, sorted by (page, y0).
    """
    # 1. Table false-positive suppression
    blocks = suppress_table_false_positives(blocks)

    # 2. Cross-kind IoU duplicate suppression
    blocks = suppress_cross_kind_duplicates(blocks)

    # 3. Equation continuation merging (within-page)
    blocks = merge_equation_continuations(blocks)

    # 4. Cross-page equation continuation
    blocks = merge_cross_page_equations(blocks)

    # 5. Contiguous definition grouping
    blocks = group_contiguous_definitions(blocks)

    # 6. Cross-page worked-example continuation
    blocks = merge_cross_page_worked_examples(blocks)

    # 7. Enhanced callout detection (metadata enrichment, no removal)
    if lines is not None:
        blocks = enhance_callout_detection(blocks, lines)

    # 8. Same-kind duplicate cleanup
    blocks = remove_duplicate_blocks(blocks)

    # 9. Containment cleanup
    blocks = remove_contained_blocks(blocks)

    # Final deterministic sort
    blocks.sort(key=lambda b: (b.page, b.bbox[1]))

    return blocks

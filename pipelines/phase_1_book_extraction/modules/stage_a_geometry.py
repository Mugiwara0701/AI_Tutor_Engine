"""
stage_a_geometry.py — Stage A: Geometry Segmentation.

Responsibility (and ONLY this responsibility): WHERE are the blocks?

Input
    - structure.lines            (text layer,  modules/pdf_parser.py)
    - layout["figures"/"tables"/"equations"/"diagrams"]
                                  (visual layer, modules/layout_detector.py)

Output
    A flat list of top-level `Block` objects. Each Block may contain child
    Blocks (e.g. a worked example's Formula/Calculation/Calculation/Answer
    lines are children of ONE Worked-Example-shaped block, not four separate
    top-level blocks).

Stage A does NOT:
    - decide what a block IS (Heading / Definition / Worked Example / ...)
      -- that is stage_b_classify.classify()
    - decide how important a block is                  -- stage_c_priority
    - call the VLM

Grouping rules implemented here:
    1. Equation-cluster grouping: consecutive equation-like lines (as
       located by layout_detector's per-line detector) that are vertically
       close and left-aligned are merged into ONE block with each source
       line as a child. This is what turns
           F = ma / F = 20 x 5 / 100 = ma / a = 5
       from 4 independent VisualRegions into a single hierarchical block --
       the single largest win from the architecture review. Whether that
       merged block is later labeled "Worked Example" or "Formula Box" is a
       Stage B decision; Stage A only knows that these lines physically
       belong together.
    2. Figure/diagram + caption grouping: a visual region plus the caption
       line layout_detector already located next to it become one block
       with two children (visual, caption).
    3. Table + explanation grouping: a table region plus an adjacent
       explanatory text line (the line immediately above/below that is not
       itself the caption) becomes one block.
    4. Generic callout-label grouping: a "label-like" line (see
       _LABEL_ANCHOR_RE below) plus the contiguous body lines that follow it
       becomes one block. NOTE on scope: today the only cheap, deterministic
       way to find "where a pedagogical callout starts" is the same keyword
       set content_blocks.py used to classify it with. Using it here is a
       geometric/typographic proxy (these words reliably coincide with a
       distinct visual label in NCERT layout: bold run-in, indent change,
       rule/box), not a classification decision -- Stage B still owns the
       actual label_type -> block_type mapping, and a future purely
       typographic/geometric anchor detector can replace
       `_looks_like_label_line()` without changing Stage B's interface.
    5. Cross-page continuation: if a block runs to the bottom of a page
       with no blank-line/heading boundary, and the next page starts with
       plain body lines before any new label/heading, the two are merged
       into one block spanning both pages (page_end != page, plus a
       `continuation` note in grouping_meta).

Every Block keeps enough lineage (block_id, page, bbox, lines) that
stage_e_validation can trace a validated Educational Object back to its
exact source location.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from modules.pdf_parser import Line, ChapterStructure, make_id
from modules.layout_detector import VisualRegion
from modules.text_utils import (
    DEFINITION_TERM_FIRST_RE as _DEFINITION_TERM_FIRST_RE,
    DEFINITION_TERM_AFTER_RE as _DEFINITION_TERM_AFTER_RE,
    TERM_STOPWORDS as _DEFINITION_TERM_STOPWORDS,
)

logger = logging.getLogger("ncert_pipeline.stage_a")

# Same anchor words content_blocks.py used to use for classification; here
# they only mark "a new physical block probably starts on this line" (see
# docstring point 4 above). Stage B is what turns the matched word into an
# actual block_type.
_LABEL_ANCHOR_RE = re.compile(
    r"^\s*(activity|think|observe|try|discuss|experiment"
    r"|did you know|important|note|remember|case study|box"
    r"|warning|caution"
    r"|example|illustration|solved example)\b[\s:.\-]*\d*", re.I)

# _DEFINITION_TERM_FIRST_RE, _DEFINITION_TERM_AFTER_RE, and
# _DEFINITION_TERM_STOPWORDS are imported from modules.text_utils
# (M4.1A: pattern centralisation). Names are preserved via import aliases
# so all existing call sites within this module continue to work unchanged.

# Vertical gap (as a fraction of page height) within which two equation-like
# lines are considered part of the same physical cluster rather than two
# unrelated equations that happen to both be on the page.
_EQUATION_CLUSTER_GAP_FRACTION = 0.035
# Horizontal alignment tolerance (points) for "left-aligned enough to be the
# same block" between consecutive equation lines.
_EQUATION_X_ALIGN_TOLERANCE = 40.0


@dataclass
class Block:
    block_id: str
    page: int
    bbox: Tuple[float, float, float, float]
    lines: List[Line] = field(default_factory=list)
    children: List["Block"] = field(default_factory=list)
    parent: Optional[str] = None
    grouping_meta: Dict[str, Any] = field(default_factory=dict)
    page_end: Optional[int] = None  # set only when a block spans multiple pages
    # Filled in later by Stage B / Stage C / Stage D — kept here (rather than
    # in a separate parallel structure) so the whole pipeline can pass around
    # one object per block instead of re-joining several dicts by block_id.
    block_type: Optional[str] = None
    confidence: float = 0.0
    priority: Optional[str] = None


def _union_bbox(bboxes: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    xs0 = [b[0] for b in bboxes]
    ys0 = [b[1] for b in bboxes]
    xs1 = [b[2] for b in bboxes]
    ys1 = [b[3] for b in bboxes]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _make_block(chapter_title: str, kind: str, page: int, bbox, lines: List[Line],
                 children: List[Block] = None, grouping_meta: Dict[str, Any] = None) -> Block:
    idx_key = f"{page}-{bbox[1]:.1f}"
    return Block(
        block_id=make_id(chapter_title, "block", kind, idx_key),
        page=page, bbox=tuple(bbox), lines=list(lines),
        children=children or [], grouping_meta=grouping_meta or {"anchor": kind},
    )


# --------------------------------------------------------------------------
# 1. Equation clustering
# --------------------------------------------------------------------------
def _cluster_equation_regions(chapter_title: str, equations: List[VisualRegion]) -> List[Block]:
    by_page: Dict[int, List[VisualRegion]] = {}
    for r in equations:
        by_page.setdefault(r.page, []).append(r)

    blocks: List[Block] = []
    for page, regions in by_page.items():
        regions = sorted(regions, key=lambda r: r.bbox[1])
        cluster: List[VisualRegion] = []

        def _flush():
            if not cluster:
                return
            lines = [Line(text=(c.extra or {}).get("raw_text", ""), size=0.0, max_size=0.0,
                           bold=False, font="", page=c.page, y=c.bbox[1],
                           page_height=0.0, bbox=c.bbox) for c in cluster]
            block = _make_block(chapter_title, "equation-cluster", page,
                                 _union_bbox([c.bbox for c in cluster]), lines,
                                 grouping_meta={"anchor": "equation-cluster",
                                                "line_count": len(cluster)})
            block.children = [
                _make_block(chapter_title, "equation-line", page, c.bbox, [lines[i]],
                             grouping_meta={"anchor": "equation-line", "raw_text": lines[i].text})
                for i, c in enumerate(cluster)
            ]
            for child in block.children:
                child.parent = block.block_id
            blocks.append(block)

        for r in regions:
            if not cluster:
                cluster.append(r)
                continue
            prev = cluster[-1]
            gap = r.bbox[1] - prev.bbox[3]
            x_aligned = abs(r.bbox[0] - prev.bbox[0]) <= _EQUATION_X_ALIGN_TOLERANCE
            page_h = max(prev.bbox[3], r.bbox[3], 1.0)
            if gap <= _EQUATION_CLUSTER_GAP_FRACTION * page_h * 20 and x_aligned:
                # gap measured in absolute points here since VisualRegion
                # doesn't carry page_height; the *20 keeps the tolerance in
                # the same ballpark as a fraction-of-page-height check would
                # give for a typical ~800pt-tall page.
                cluster.append(r)
            else:
                _flush()
                cluster = [r]
        _flush()

    return blocks


# --------------------------------------------------------------------------
# 2 & 3. Figure/diagram + caption, table + explanation
# --------------------------------------------------------------------------
def _nearest_line(lines_by_page: Dict[int, List[Line]], page: int, bbox, max_gap: float = 60.0) -> Optional[Line]:
    candidates = lines_by_page.get(page, [])
    best, best_gap = None, max_gap
    for l in candidates:
        gap_below = l.bbox[1] - bbox[3]
        gap_above = bbox[1] - l.bbox[3]
        valid_gaps = [g for g in (gap_below, gap_above) if g >= -2]  # allow tiny overlap
        if not valid_gaps:
            # Line overlaps the region by more than the tiny-overlap tolerance
            # on both sides (e.g. text wrapping tightly around a figure/table);
            # it isn't a plausible caption candidate, so skip it instead of
            # crashing on min() of an empty sequence.
            continue
        gap = min(valid_gaps)
        if 0 <= gap < best_gap:
            best, best_gap = l, gap
    return best


def _visual_plus_caption_blocks(chapter_title: str, regions: List[VisualRegion], kind: str,
                                 lines_by_page: Dict[int, List[Line]]) -> List[Block]:
    blocks = []
    for r in regions:
        children_lines = []
        caption_line = _nearest_line(lines_by_page, r.page, r.bbox) if not r.caption else None
        if caption_line:
            children_lines.append(caption_line)
        block = _make_block(chapter_title, kind, r.page, r.bbox, children_lines,
                             grouping_meta={"anchor": kind, "caption": r.caption, "region_extra": r.extra or {}})
        block.children = [
            _make_block(chapter_title, f"{kind}-caption", r.page, cl.bbox, [cl])
            for cl in children_lines
        ]
        for child in block.children:
            child.parent = block.block_id
        blocks.append(block)
    return blocks


# --------------------------------------------------------------------------
# 4. Generic callout-label grouping
# --------------------------------------------------------------------------
def _label_body_blocks(chapter_title: str, lines: List[Line], repeated: set) -> List[Block]:
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        l = lines[i]
        if l.text in repeated or not _LABEL_ANCHOR_RE.match(l.text):
            i += 1
            continue
        start_page = l.page
        body_lines = [l]
        j = i + 1
        while j < n and len(body_lines) < 13:
            nxt = lines[j]
            if nxt.page != start_page:
                break
            if nxt.text in repeated:
                j += 1
                continue
            if _LABEL_ANCHOR_RE.match(nxt.text):
                break
            body_lines.append(nxt)
            j += 1
        block = _make_block(chapter_title, "callout-label", start_page,
                             _union_bbox([bl.bbox for bl in body_lines]), body_lines,
                             grouping_meta={"anchor": "callout-label", "label_line": l.text})
        block.children = [
            _make_block(chapter_title, "callout-body-line", bl.page, bl.bbox, [bl])
            for bl in body_lines
        ]
        for child in block.children:
            child.parent = block.block_id
        blocks.append(block)
        i = j if j > i else i + 1
    return blocks


# --------------------------------------------------------------------------
# 4b. Definition-candidate sentence locating
# --------------------------------------------------------------------------
def _definition_candidate_blocks(chapter_title: str, lines: List[Line], repeated: set) -> List[Block]:
    blocks = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        m = _DEFINITION_TERM_FIRST_RE.match(l.text)
        term = m.group("term").strip() if m else None
        if not term:
            m = _DEFINITION_TERM_AFTER_RE.search(l.text)
            term = m.group("term").strip() if m else None
        if not term or term.lower() in _DEFINITION_TERM_STOPWORDS or len(term.split()) > 6:
            continue
        block = _make_block(chapter_title, "definition-candidate", l.page, l.bbox, [l],
                             grouping_meta={"anchor": "definition-candidate", "candidate_term": term})
        blocks.append(block)
    return blocks


# --------------------------------------------------------------------------
# 4c. Headings — pdf_parser.parse_chapter_pdf already deterministically
# detects headings (font-size/numbering based) with real parent/child
# hierarchy (TopicRecord.parent/children), far more reliably than a
# generic anchor regex could. Stage A doesn't re-derive that; it just wraps
# each already-detected TopicRecord as a Block so headings flow through the
# same model (and the same Stage B/C pipeline) as every other block type
# instead of living in a separate parallel structure. `topic_id` is kept in
# grouping_meta so a later phase can still join back to the original
# TopicRecord if needed.
# --------------------------------------------------------------------------
def _topic_heading_blocks(chapter_title: str, topics) -> List[Block]:
    blocks = []
    topic_id_to_block_id = {}
    for t in topics:
        b = _make_block(chapter_title, "heading-topic", t.page_start, t.bbox, [],
                         grouping_meta={"anchor": "heading-topic", "topic_id": t.id,
                                        "numbering": t.numbering, "level": t.level})
        b.page_end = t.page_end if t.page_end != t.page_start else None
        blocks.append(b)
        topic_id_to_block_id[t.id] = b.block_id
    for t, b in zip(topics, blocks):
        if t.parent and t.parent in topic_id_to_block_id:
            b.parent = topic_id_to_block_id[t.parent]
    return blocks


# --------------------------------------------------------------------------
# 5. Cross-page continuation
# --------------------------------------------------------------------------
def _merge_cross_page_continuations(blocks: List[Block], num_pages: int,
                                     bottom_margin_fraction: float = 0.08) -> List[Block]:
    """A block that ends within `bottom_margin_fraction` of its page's
    bottom, with no other block starting after it on that page, is a
    candidate to continue onto the next page. It is merged with the next
    page's earliest block IF that next block is itself an unlabeled
    callout-body/paragraph continuation (i.e. not a fresh label/heading/
    figure/table anchor) — merging only kinds that are plausibly "body text
    that kept going", never merging two independent structural anchors
    (e.g. two different tables) into one.
    """
    by_page: Dict[int, List[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)
    for page_blocks in by_page.values():
        page_blocks.sort(key=lambda b: b.bbox[1])

    merged_ids = set()
    out: List[Block] = []
    for b in blocks:
        if b.block_id in merged_ids:
            continue
        page_blocks = by_page.get(b.page, [])
        is_last_on_page = page_blocks and page_blocks[-1].block_id == b.block_id
        next_page_blocks = by_page.get(b.page + 1, [])
        can_continue = (
            is_last_on_page
            and b.grouping_meta.get("anchor") == "callout-label"
            and next_page_blocks
            and next_page_blocks[0].grouping_meta.get("anchor") == "callout-label"
            and not _LABEL_ANCHOR_RE.match(next_page_blocks[0].lines[0].text if next_page_blocks[0].lines else "")
        )
        if can_continue:
            cont = next_page_blocks[0]
            b.children.extend(cont.children)
            b.lines.extend(cont.lines)
            b.page_end = cont.page
            b.grouping_meta["continuation"] = {"continued_on_page": cont.page, "merged_block_id": cont.block_id}
            merged_ids.add(cont.block_id)
        out.append(b)
    return [b for b in out if b.block_id not in merged_ids]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def build_hierarchical_blocks(structure: ChapterStructure, layout: Dict[str, List[VisualRegion]]) -> List[Block]:
    """Consumes structure.lines (text layer) + layout's visual regions
    (visual layer) and returns a flat list of top-level hierarchical
    Blocks, per Stage A's contract. Order is page, then y0."""
    chapter_title = structure.chapter_title

    lines_by_page: Dict[int, List[Line]] = {}
    for l in structure.lines:
        lines_by_page.setdefault(l.page, []).append(l)
    for pg_lines in lines_by_page.values():
        pg_lines.sort(key=lambda l: l.y)

    blocks: List[Block] = []
    blocks.extend(_cluster_equation_regions(chapter_title, layout.get("equations", [])))
    blocks.extend(_visual_plus_caption_blocks(chapter_title, layout.get("figures", []), "figure", lines_by_page))
    blocks.extend(_visual_plus_caption_blocks(chapter_title, layout.get("diagrams", []), "diagram", lines_by_page))
    blocks.extend(_visual_plus_caption_blocks(chapter_title, layout.get("tables", []), "table", lines_by_page))
    blocks.extend(_label_body_blocks(chapter_title, structure.lines, structure.repeated))
    blocks.extend(_definition_candidate_blocks(chapter_title, structure.lines, structure.repeated))
    blocks.extend(_topic_heading_blocks(chapter_title, structure.topics))

    blocks = _merge_cross_page_continuations(blocks, structure.num_pages)
    blocks.sort(key=lambda b: (b.page, b.bbox[1]))

    logger.info("Stage A: built %d hierarchical block(s) for chapter '%s'.", len(blocks), chapter_title)
    return blocks
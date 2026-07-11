"""
layout_detector.py — deterministic visual-element DETECTION.

Finds figures, tables, equations, and generic diagram-like regions and
returns bounding boxes + basic type + nearby caption text. It never saves
image bytes (per spec: metadata only) and it never classifies *meaning* —
that's semantic_processor.py's job, using this module's bboxes to know
*where* to crop a page image for the VLM to look at.

PERFORMANCE NOTE (implementation-level only, no detection-logic change):
run_layout_detection() used to call detect_figures(), detect_tables(),
detect_diagram_like_boxes(), and detect_equations() as four independent
passes, each opening its own fitz.Document (5 total fitz.open() calls
counting the page-count probe at the top of run_layout_detection), and
three of those four passes (figures/tables/equations) each re-ran
page.get_text("dict") — the single most expensive call in this module —
over every page in the chapter, so a chapter's pages were fully
re-parsed 3x. run_layout_detection now opens the document once and
computes get_text("dict") once per page, sharing that result (and the
derived `lines_text` caption-lookup list, which was also being rebuilt
identically in both detect_figures and detect_tables) across all four
detectors. The per-kind detect_*() functions are kept, unchanged in
behavior and signature, for standalone/test use — they just each still
open their own doc when called directly, same as before.
"""
import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

import fitz  # PyMuPDF

from modules.pdf_parser import clean_extracted_text

CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?\.?|table|chart|graph|map|box)\s*[\d.]*\s*[:.\-]?\s*(.*)$", re.I)
TABLE_TYPE_HINT_RE = re.compile(r"\btable\b", re.I)
EQUATION_HINT_RE = re.compile(r"[=∑∫√±≤≥≠∆π×÷]|\b[A-Za-z]\s*=\s*[A-Za-z0-9]")


@dataclass
class VisualRegion:
    kind: str  # "figure" | "table" | "equation" | "diagram"
    page: int
    bbox: Tuple[float, float, float, float]
    caption: str = ""
    title: str = ""
    extra: Dict[str, Any] = None


def _nearby_caption(page_lines_text: List[Tuple[float, str]], region_bbox, page_height) -> str:
    """Caption text is usually the line immediately below (or above) the
    region within a small vertical window."""
    y0, y1 = region_bbox[1], region_bbox[3]
    best = ""
    for y, text in page_lines_text:
        if y1 <= y <= y1 + 0.08 * page_height or y0 - 0.05 * page_height <= y <= y0:
            m = CAPTION_RE.match(text)
            if m:
                return text.strip()
            if not best and abs(y - y1) < 0.08 * page_height:
                best = text.strip()
    return best


def _lines_text_from_dict(text_dict: Dict[str, Any]) -> List[Tuple[float, str]]:
    """Derived once per page from an already-computed page.get_text("dict")
    result; shared by every detector that needs (y-position, line-text)
    pairs for caption lookup, instead of each detector re-deriving it from
    a freshly re-parsed page.

    Normalization parity fix: this joins the exact same kind of raw
    span text pdf_parser.extract_lines() does (page.get_text("dict") ->
    "".join(span texts)), but is a second, independent extraction pass
    that used to skip pdf_parser's clean_extracted_text() step entirely --
    so a figure/table caption pulled from here could carry an
    un-normalized Unicode form (or a stray invisible character) that the
    same text would NOT have if it had instead been picked up as a
    regular body line. Applying the identical NFC-normalization/
    invisible-char-strip here (never OCR cleanup -- this is born-digital
    text, same as pdf_parser's own lines) keeps every born-digital text
    field in the pipeline on the same normalization footing regardless of
    which detector happened to read it."""
    return [(l["bbox"][1], clean_extracted_text("".join(s["text"] for s in l["spans"])))
            for b in text_dict["blocks"] for l in b.get("lines", [])]


# --------------------------------------------------------------------------
# Per-page region extraction — the actual detection logic, unchanged from
# the previous per-function implementations. Each takes already-available
# page/text_dict/lines_text rather than a pdf_path, so callers control
# whether the doc/text_dict is opened/parsed once (run_layout_detection)
# or once per standalone call (detect_figures(), etc., below).
# --------------------------------------------------------------------------
def _figures_on_page(page: fitz.Page, pno: int, lines_text: List[Tuple[float, str]]) -> List[VisualRegion]:
    ph = page.rect.height
    regions: List[VisualRegion] = []
    for img in page.get_image_info(xrefs=True):
        bbox = tuple(img["bbox"])
        if (bbox[2] - bbox[0]) < 20 or (bbox[3] - bbox[1]) < 20:
            continue  # skip tiny decorative glyphs/icons
        caption = _nearby_caption(lines_text, bbox, ph)
        regions.append(VisualRegion(kind="figure", page=pno, bbox=bbox, caption=caption))
    return regions


def _tables_on_page(page: fitz.Page, pno: int, lines_text: List[Tuple[float, str]]) -> List[VisualRegion]:
    ph = page.rect.height
    regions: List[VisualRegion] = []
    found_any = False
    try:
        tf = page.find_tables()
        for t in tf.tables:
            bbox = tuple(t.bbox)
            caption = _nearby_caption(lines_text, bbox, ph)
            regions.append(VisualRegion(
                kind="table", page=pno, bbox=bbox, caption=caption,
                extra={"rows": len(t.rows) if hasattr(t, "rows") else t.row_count,
                       "columns": len(t.header.names) if getattr(t, "header", None) else t.col_count},
            ))
            found_any = True
    except Exception:
        pass
    if not found_any:
        # caption-only fallback: a line that reads like "Table 3.2 ..." with
        # no detectable ruling lines still deserves a metadata stub so it
        # isn't silently dropped.
        for y, text in lines_text:
            if TABLE_TYPE_HINT_RE.search(text) and re.match(r"^\s*table\b", text, re.I):
                regions.append(VisualRegion(kind="table", page=pno,
                                             bbox=(0, y, page.rect.width, y + 20),
                                             caption=text.strip(), extra={"rows": 0, "columns": 0}))
    return regions


def _equations_on_page(text_dict: Dict[str, Any], pno: int) -> List[VisualRegion]:
    regions: List[VisualRegion] = []
    for b in text_dict["blocks"]:
        for l in b.get("lines", []):
            text = clean_extracted_text("".join(s["text"] for s in l["spans"]).strip())
            if not text:
                continue
            if EQUATION_HINT_RE.search(text) and len(text) < 200:
                regions.append(VisualRegion(kind="equation", page=pno, bbox=tuple(l["bbox"]),
                                             caption="", extra={"raw_text": text}))
    return regions


def _diagrams_on_page(page: fitz.Page, pno: int) -> List[VisualRegion]:
    drawings = page.get_drawings()
    if not drawings:
        return []
    boxes = [tuple(d["rect"]) for d in drawings if d.get("rect")]
    if not boxes:
        return []
    # merge overlapping/adjacent rects into clusters (simple union-find by proximity)
    clusters: List[List[float]] = []
    for x0, y0, x1, y1 in boxes:
        placed = False
        for c in clusters:
            if not (x1 < c[0] - 5 or x0 > c[2] + 5 or y1 < c[1] - 5 or y0 > c[3] + 5):
                c[0], c[1], c[2], c[3] = min(c[0], x0), min(c[1], y0), max(c[2], x1), max(c[3], y1)
                placed = True
                break
        if not placed:
            clusters.append([x0, y0, x1, y1])
    regions: List[VisualRegion] = []
    for c in clusters:
        area = (c[2] - c[0]) * (c[3] - c[1])
        if area > 2500:  # ignore tiny rules/underlines
            regions.append(VisualRegion(kind="diagram", page=pno, bbox=tuple(c)))
    return regions


# --------------------------------------------------------------------------
# Standalone per-kind entry points — unchanged public signatures/behavior.
# Each opens its own document, exactly like before this optimization pass;
# they're independently usable/testable, they just aren't what
# run_layout_detection() calls internally anymore (see below).
# --------------------------------------------------------------------------
def detect_figures(pdf_path: str) -> List[VisualRegion]:
    """Raster/vector images embedded on the page -> figure candidates."""
    doc = fitz.open(pdf_path)
    regions: List[VisualRegion] = []
    for pno, page in enumerate(doc):
        lines_text = _lines_text_from_dict(page.get_text("dict"))
        regions.extend(_figures_on_page(page, pno, lines_text))
    doc.close()
    return regions


def detect_tables(pdf_path: str) -> List[VisualRegion]:
    """Use PyMuPDF's built-in table finder (ruling-line + whitespace based);
    falls back to caption-only detection ('Table 3.2 ...') if the finder is
    unavailable in the installed PyMuPDF version."""
    doc = fitz.open(pdf_path)
    regions: List[VisualRegion] = []
    for pno, page in enumerate(doc):
        lines_text = _lines_text_from_dict(page.get_text("dict"))
        regions.extend(_tables_on_page(page, pno, lines_text))
    doc.close()
    return regions


def detect_equations(pdf_path: str) -> List[VisualRegion]:
    """Lines whose text contains equation-like symbols/patterns. This is a
    text-layer heuristic (works for born-digital equations); OCR-only scanned
    equations are picked up later by ocr_engine + a secondary pass."""
    doc = fitz.open(pdf_path)
    regions: List[VisualRegion] = []
    for pno, page in enumerate(doc):
        regions.extend(_equations_on_page(page.get_text("dict"), pno))
    doc.close()
    return regions


def detect_diagram_like_boxes(pdf_path: str) -> List[VisualRegion]:
    """Vector-drawn (non-raster) content — flowcharts, hand-drawn-style
    diagrams rendered as PDF vector paths rather than embedded images.
    Clusters nearby drawing commands per page into bbox regions."""
    doc = fitz.open(pdf_path)
    regions: List[VisualRegion] = []
    for pno, page in enumerate(doc):
        regions.extend(_diagrams_on_page(page, pno))
    doc.close()
    return regions


def _round_bbox(bbox: Tuple[float, float, float, float], precision: float = 2.0) -> Tuple[float, float, float, float]:
    return tuple(round(c / precision) * precision for c in bbox)


def _bbox_iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
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


def _dedupe_overlapping_same_page(regions: List[VisualRegion], iou_threshold: float = 0.7) -> List[VisualRegion]:
    """Same artwork sometimes gets detected twice on one page (e.g. an image
    and a near-identical secondary xref/mask at a slightly shifted bbox).
    Collapse near-duplicates on the same page, keeping whichever copy has a
    caption if one does."""
    kept: List[VisualRegion] = []
    for r in regions:
        dup_idx = None
        for i, k in enumerate(kept):
            if k.page == r.page and _bbox_iou(k.bbox, r.bbox) >= iou_threshold:
                dup_idx = i
                break
        if dup_idx is None:
            kept.append(r)
        elif not kept[dup_idx].caption and r.caption:
            kept[dup_idx] = r  # prefer the copy that actually carries a caption
    return kept


def filter_repeated_regions(regions: List[VisualRegion], num_pages: int) -> List[VisualRegion]:
    """Every NCERT book has a handful of page-template graphics — full-page
    background/watermark panels, margin colour bars, side-tab running-header
    art — that PyMuPDF's image and table finders re-detect on every single
    page they appear on. That inflates figure/table counts by 5-10x on a
    mostly-text chapter and wastes a VLM call on decoration, never real
    content.

    Mirrors pdf_parser.find_repeated_lines(): a region whose (rounded) bbox
    recurs at the same position across multiple pages is treated as
    decorative page-template art, not chapter content, and dropped. Unlike
    text lines (where short common phrases can coincidentally repeat), a
    genuine figure/table essentially never occupies the exact same bbox on
    more than one page by chance — so even 2+ exact-position recurrences is
    a reliable decorative signal, including template art that only appears
    on alternating (e.g. left-page vs right-page) layouts.
    """
    if num_pages < 3:
        return regions  # not enough pages to tell "repeating template" from "coincidence"
    regions = _dedupe_overlapping_same_page(regions)
    position_counts = Counter(_round_bbox(r.bbox) for r in regions)
    threshold = max(2, num_pages // 3)
    repeated_positions = {pos for pos, count in position_counts.items() if count >= threshold}
    return [r for r in regions if _round_bbox(r.bbox) not in repeated_positions]


def run_layout_detection(pdf_path: str) -> Dict[str, List[VisualRegion]]:
    """Single fitz.open() + single page.get_text("dict") pass per page,
    shared across the figure/table/equation detectors (diagrams only need
    get_drawings(), not the text dict). Previously this opened the PDF 5x
    (a page-count probe + one open per detect_*() call) and re-ran
    get_text("dict") on every page 3x (once each in detect_figures,
    detect_tables, detect_equations). Output is identical: each detector's
    per-page logic is unchanged (see _figures_on_page / _tables_on_page /
    _equations_on_page / _diagrams_on_page above), regions are still
    accumulated in ascending page order within each kind, and
    filter_repeated_regions()/dedup still run exactly as before on the
    assembled per-kind lists.
    """
    doc = fitz.open(pdf_path)
    num_pages = doc.page_count

    figures: List[VisualRegion] = []
    tables: List[VisualRegion] = []
    equations: List[VisualRegion] = []
    diagrams: List[VisualRegion] = []

    for pno, page in enumerate(doc):
        text_dict = page.get_text("dict")  # computed ONCE per page, shared below
        lines_text = _lines_text_from_dict(text_dict)

        figures.extend(_figures_on_page(page, pno, lines_text))
        tables.extend(_tables_on_page(page, pno, lines_text))
        equations.extend(_equations_on_page(text_dict, pno))
        diagrams.extend(_diagrams_on_page(page, pno))

    doc.close()

    figures = filter_repeated_regions(figures, num_pages)
    tables = filter_repeated_regions(tables, num_pages)
    diagrams = filter_repeated_regions(diagrams, num_pages)
    # Equations are text-pattern hits on running body content, not
    # position-based image/vector detections — they don't recur at a fixed
    # page-template bbox the way decorative art does, so no filter needed.

    return {"figures": figures, "tables": tables, "equations": equations, "diagrams": diagrams}
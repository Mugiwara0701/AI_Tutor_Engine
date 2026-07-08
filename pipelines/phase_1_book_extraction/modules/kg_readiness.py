"""
modules/kg_readiness.py — Part 2 of the task: makes Phase 1's Master JSON
Knowledge-Graph-ready WITHOUT building any graph itself.

Explicitly OUT of scope here (per the task spec, enforced by never being
implemented anywhere in this module):
    - no graph nodes
    - no graph edges
    - no prerequisite graphs
    - no dependency graphs
    - no Knowledge Graph of any kind

What this module DOES do: given Stage D/E's Educational Objects (plus the
Stage A/B/C block hierarchy and the topic tree already built by
pipeline.py), it attaches CONTEXT and SEMANTIC METADATA to every object so
that a later, separate Phase 2 process can build a Concept Graph /
Learning Graph / Dependency Graph / Adaptive Learning Graph / Teaching
Graph from the Master JSON alone, without re-reading the source PDF.

Nothing here removes or overwrites any field Stage D/E already produced —
every function only ADDS keys to (copies of) the educational object dicts.
EducationalObject (schemas/chapter_schema.py) is a `Loose` (extra="allow")
pydantic model specifically so these additive fields are never dropped by
schema validation.
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ncert_pipeline.kg_readiness")


# ===========================================================================
# Educational role inference (dynamic, from educational_object_type + the
# Stage B block_type it was extracted from — never hard-coded per subject)
# ===========================================================================
# Stage B's block_type vocabulary (modules/stage_b_classify.py) mapped to
# the pedagogical-intent vocabulary the task spec calls out. Anything not
# listed here falls back to a type-driven default below.
_BLOCK_TYPE_ROLE = {
    "Definition": "Introduces Knowledge",
    "Formula Box": "Explains Knowledge",
    "Worked Example": "Worked Example",
    "Solution": "Solved Example",
    "Example": "Solved Example",
    "Illustration": "Illustration",
    "Activity": "Activity",
    "Law": "Reference",
    "Summary": "Revision",
    "Figure": "Illustration",
    "Diagram": "Illustration",
    "Flowchart": "Illustration",
    "Decision Tree": "Illustration",
    "Table": "Reference",
    "Accounting Format": "Applies Knowledge",
    "Programming Syntax": "Applies Knowledge",
    "Reference": "Reference",
    "Exercise": "Practice",
    "Ambiguous": "Reference",
}

# Fallback keyed by educational_object_type when block_type isn't in the
# table above (e.g. a future block_type the map hasn't been extended for
# yet) — still dynamic, still no subject-name branching.
_OBJECT_TYPE_ROLE_DEFAULT = {
    "concept": "Introduces Knowledge",
    "formula_or_procedure": "Explains Knowledge",
    "visual": "Illustration",
    "programming_syntax": "Applies Knowledge",
    "accounting_format": "Applies Knowledge",
    "unclassified_high_value": "Reference",
    "ambiguous": "Reference",
}


def infer_educational_role(obj: Dict[str, Any]) -> str:
    """Dynamically infers the pedagogical intent of one educational object
    from what Stage B/D already determined about it (block_type,
    educational_object_type) — never from a subject name. Always returns
    a role string; 'Reference' is the safe, information-preserving
    default when nothing more specific is known."""
    block_type = obj.get("block_type")
    if block_type in _BLOCK_TYPE_ROLE:
        return _BLOCK_TYPE_ROLE[block_type]
    obj_type = obj.get("educational_object_type", "")
    return _OBJECT_TYPE_ROLE_DEFAULT.get(obj_type, "Reference")


# ===========================================================================
# Cross-reference detection ("Using the above formula", "Refer to Figure
# 2.1", "As shown in Table 1", "According to the previous definition")
# ===========================================================================
_CROSS_REF_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("figure", re.compile(r"\b(?:refer(?:ring)?\s+to|as\s+shown\s+in|see)\s+(?:the\s+)?"
                           r"(figure\s*[\d.]*)", re.I)),
    ("table", re.compile(r"\b(?:refer(?:ring)?\s+to|as\s+shown\s+in|see)\s+(?:the\s+)?"
                          r"(table\s*[\d.]*)", re.I)),
    ("equation_or_formula", re.compile(
        r"\b(using|from)\s+the\s+(above|following|previous)\s+(formula|equation)\b", re.I)),
    ("definition", re.compile(
        r"\baccording\s+to\s+the\s+(above|previous|following)\s+definition\b", re.I)),
    ("concept_or_topic", re.compile(
        r"\bas\s+(?:discussed|explained|described|mentioned)\s+(?:above|earlier|previously)\b", re.I)),
]


def detect_cross_references(text: str) -> List[Dict[str, str]]:
    """Returns a list of {"type": ..., "mention": ...} records for every
    textbook cross-reference phrase detected in `text` -- stored as
    metadata only (per the spec: 'Do NOT resolve them into graph edges').
    Purely additive/informational; never raises on odd input."""
    if not text:
        return []
    found: List[Dict[str, str]] = []
    for ref_type, pattern in _CROSS_REF_PATTERNS:
        for m in pattern.finditer(text):
            found.append({"type": ref_type, "mention": m.group(0).strip()})
    return found


# ===========================================================================
# Block hierarchy helpers (reading order, block order, hierarchy path,
# local context, sibling/nearby lookup) — built once per chapter and
# reused across every educational object.
# ===========================================================================
def _flatten_blocks(blocks: List[Any]) -> List[Any]:
    flat: List[Any] = []

    def _walk(b):
        flat.append(b)
        for c in getattr(b, "children", []) or []:
            _walk(c)

    for b in blocks or []:
        _walk(b)
    return flat


def _block_local_text(block: Any, max_words: int = 40) -> str:
    """Short text snippet from a block's own lines (or its children's
    grouping_meta raw_text, mirroring modules/recognizers/base.py's
    block_raw_texts) — used as `local_context`. Word-capped, never the
    full body, to keep the Master JSON's per-object footprint small
    while still giving Phase 2 enough text to work with without
    re-reading the PDF."""
    if getattr(block, "children", None):
        parts = [(c.grouping_meta or {}).get("raw_text") or " ".join(l.text for l in c.lines)
                  for c in block.children]
    else:
        parts = [l.text for l in getattr(block, "lines", [])]
    text = " ".join(p for p in parts if p).strip()
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + " …"
    return text


class ChapterKGContext:
    """Precomputes everything shared across every educational object in one
    chapter, so enrich_educational_objects doesn't redo this work per
    object. Built once per chapter (mirrors semantic_processor's existing
    per-chapter cache pattern)."""

    def __init__(self, blocks: List[Any], topics_out: List[Dict[str, Any]], chapter_title: str):
        self.chapter_title = chapter_title
        self.flat_blocks = _flatten_blocks(blocks)
        self.block_by_id = {b.block_id: b for b in self.flat_blocks}
        self.reading_order_by_id = {b.block_id: i for i, b in enumerate(self.flat_blocks)}

        # Per-parent block order (position among siblings under the same
        # parent, or among top-level blocks when parent is None).
        self.block_order_by_id: Dict[str, int] = {}
        by_parent: Dict[Optional[str], List[str]] = {}
        for b in self.flat_blocks:
            by_parent.setdefault(b.parent, []).append(b.block_id)
        for parent, ids in by_parent.items():
            for i, bid in enumerate(ids):
                self.block_order_by_id[bid] = i
        self.siblings_by_id: Dict[str, List[str]] = {
            bid: [i for i in ids if i != bid] for ids in by_parent.values() for bid in ids
        }

        self.topics_by_id = {t["id"]: t for t in topics_out}
        # Deepest topic covering a given page (mirrors pipeline.py's
        # _topic_lookup_factory, operating on the already-built topics_out
        # dicts instead of structure.topics records).
        self._topics_sorted = [
            t for t in topics_out
            if t.get("page_start") is not None and t.get("page_end") is not None
        ]

    def topic_for_page(self, page: int) -> Optional[Dict[str, Any]]:
        candidates = [t for t in self._topics_sorted
                      if t["page_start"] <= page <= t["page_end"]]
        if not candidates:
            return None
        # Prefer the most specific (deepest / highest level number, i.e.
        # sub-heading over heading) match, then the latest-starting one.
        candidates.sort(key=lambda t: (t.get("level", 1), t["page_start"]))
        return candidates[-1]

    def hierarchy_path(self, topic: Optional[Dict[str, Any]]) -> List[str]:
        """[chapter_title, heading, sub-heading, ...] from root to leaf."""
        path = [self.chapter_title]
        chain: List[str] = []
        node = topic
        seen = set()
        while node is not None and node["id"] not in seen:
            seen.add(node["id"])
            chain.append(node["title"])
            parent_id = node.get("parent")
            node = self.topics_by_id.get(parent_id) if parent_id else None
        path.extend(reversed(chain))
        return path

    def nearby_object_ids(self, obj_id: str, block_id: str, all_ids_by_block: Dict[str, List[str]],
                           window: int = 2) -> List[str]:
        """Educational object ids that are structurally or positionally
        close to this one: siblings under the same parent block, plus
        objects within `window` positions in overall reading order —
        both are directly-observable-from-the-document relationships, not
        inferred graph edges."""
        nearby: List[str] = []
        for sib_block_id in self.siblings_by_id.get(block_id, []):
            nearby.extend(all_ids_by_block.get(sib_block_id, []))
        order = self.reading_order_by_id.get(block_id)
        if order is not None:
            for other_block, other_order in self.reading_order_by_id.items():
                if other_block == block_id:
                    continue
                if abs(other_order - order) <= window:
                    nearby.extend(all_ids_by_block.get(other_block, []))
        # de-dup while preserving order, excluding the object itself
        out, seen = [], set()
        for oid in nearby:
            if oid != obj_id and oid not in seen:
                seen.add(oid)
                out.append(oid)
        return out


def enrich_educational_objects(
    educational_objects: List[Dict[str, Any]],
    blocks: List[Any],
    topics_out: List[Dict[str, Any]],
    chapter_title: str,
    figures: Optional[List[Dict[str, Any]]] = None,
    tables: Optional[List[Dict[str, Any]]] = None,
    equations: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Returns a NEW list of educational object dicts, each augmented with
    the context-preservation and Knowledge-Graph-readiness metadata
    described in the task spec. Every field Stage D/E already produced is
    copied through unchanged; nothing is removed, nothing is overwritten.
    Never raises: any per-object enrichment failure is caught and logged,
    and that object is still returned with whatever enrichment succeeded
    (plus its original, untouched fields) rather than dropped.
    """
    ctx = ChapterKGContext(blocks, topics_out, chapter_title)
    figures, tables, equations = figures or [], tables or [], equations or []

    ids_by_block: Dict[str, List[str]] = {}
    for obj in educational_objects:
        ids_by_block.setdefault(obj.get("block_id"), []).append(obj.get("id"))

    figures_tables_by_page: Dict[int, Dict[str, List[str]]] = {}
    for kind, coll in (("figure", figures), ("table", tables)):
        for item in coll:
            page = item.get("page")
            bucket = figures_tables_by_page.setdefault(page, {"figure": [], "table": []})
            bucket[kind].append(item.get("id"))

    enriched: List[Dict[str, Any]] = []
    for obj in educational_objects:
        try:
            enriched.append(_enrich_one(obj, ctx, ids_by_block, figures_tables_by_page))
        except Exception:
            logger.exception("kg_readiness: enrichment failed for object %s — keeping "
                              "object with its original (unenriched) fields.", obj.get("id"))
            enriched.append(dict(obj))
    return enriched


def _enrich_one(obj: Dict[str, Any], ctx: ChapterKGContext, ids_by_block: Dict[str, List[str]],
                 figures_tables_by_page: Dict[int, Dict[str, List[str]]]) -> Dict[str, Any]:
    out = dict(obj)  # never mutate the caller's dict; additive-only copy
    block_id = obj.get("block_id")
    block = ctx.block_by_id.get(block_id)
    page = obj.get("page")

    topic = ctx.topic_for_page(page) if page is not None else None
    hierarchy_path = ctx.hierarchy_path(topic)
    local_context = _block_local_text(block) if block is not None else ""

    # ---- context preservation (spec section "PRESERVE CONTEXT") --------
    out["parent_chapter"] = ctx.chapter_title
    out["parent_heading"] = hierarchy_path[1] if len(hierarchy_path) > 1 else None
    out["parent_sub_heading"] = hierarchy_path[2] if len(hierarchy_path) > 2 else None
    out["parent_block_id"] = block.parent if block is not None else None
    out["hierarchy_path"] = hierarchy_path
    out["page_id"] = f"page-{page}" if page is not None else None
    out["reading_order"] = ctx.reading_order_by_id.get(block_id)
    out["block_order"] = ctx.block_order_by_id.get(block_id)
    out["source_block_id"] = block_id
    out["semantic_topic"] = topic.get("title") if topic else None
    out["associated_topic_id"] = topic.get("id") if topic else None
    out["local_context"] = local_context
    out["nearby_educational_objects"] = ctx.nearby_object_ids(obj.get("id"), block_id, ids_by_block)
    out["ocr_evidence"] = {
        "raw_text_available": bool(local_context),
        "block_confidence": getattr(block, "confidence", None) if block is not None else None,
    }
    out["layout_metadata"] = {
        "page": page,
        "page_end": obj.get("page_end"),
        "bbox": obj.get("bbox"),
        "block_type": obj.get("block_type"),
        "priority": obj.get("priority"),
    }
    out["extraction_provenance"] = {
        "recognizer": obj.get("recognizer"),
        "source": obj.get("source"),
        "confidence": obj.get("confidence"),
        "stage": "stage_d_extraction+stage_e_validation",
    }

    # ---- educational role (spec section "PRESERVE EDUCATIONAL ROLES") --
    out["educational_role"] = infer_educational_role(obj)

    # ---- cross references (spec section "PRESERVE CROSS REFERENCES") ---
    out["cross_references"] = detect_cross_references(local_context)
    out["visual_references"] = [r for r in out["cross_references"]
                                 if r["type"] in ("figure", "table")]

    # ---- KG metadata (spec section "KNOWLEDGE GRAPH METADATA") ----------
    obj_type = obj.get("educational_object_type", "")
    role = out["educational_role"]
    out["introduces_concept"] = obj_type == "concept" or role == "Introduces Knowledge"
    out["explains_concept"] = role in ("Explains Knowledge",)
    out["applies_concept"] = role in ("Applies Knowledge", "Worked Example", "Solved Example")
    out["demonstrates_concept"] = role in ("Worked Example", "Solved Example", "Illustration", "Activity")
    out["references_concept"] = bool(out["cross_references"]) or role == "Reference"

    out["uses_formula"] = (
        [obj.get("id")] if obj_type == "formula_or_procedure"
        else [r["mention"] for r in out["cross_references"] if r["type"] == "equation_or_formula"]
    )
    out["derived_from"] = block.parent if (block is not None and block.parent) else None
    out["belongs_to"] = {
        "topic": topic.get("id") if topic else None,
        "heading": out["parent_heading"],
        "chapter": ctx.chapter_title,
    }
    out["associated_topic"] = topic.get("title") if topic else None
    out["associated_heading"] = out["parent_heading"]
    out["associated_chapter"] = ctx.chapter_title

    page_visuals = figures_tables_by_page.get(page, {"figure": [], "table": []})
    out["visual_support"] = bool(page_visuals["figure"]) or bool(page_visuals["table"])
    out["figure_support"] = list(page_visuals["figure"])
    out["table_support"] = list(page_visuals["table"])

    out["prerequisite_candidates"] = list(topic.get("prerequisites", [])) if topic else []
    out["dependency_candidates"] = list(topic.get("related_topics", [])) if topic else []
    out["related_educational_objects"] = out["nearby_educational_objects"]

    return out

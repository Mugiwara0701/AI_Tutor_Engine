"""
modules/structural_validator.py — Milestone 2: Structural Validation.

SCOPE: this milestone strengthens Phase 1 validation. `modules/validator.py`
(Milestone-0/Phase-A work) already checks EXTRACTION QUALITY: does the
Chapter JSON dict match `schemas/chapter_schema.py`'s shape/types
(`validate_chapter`)? That is necessary but not sufficient -- a document
can be perfectly *type*-valid (every field the right Python type) while
being *structurally* broken (an object's `topic_ids` pointing at a topic
id that does not exist anywhere in `topics`; two different objects
sharing the same `id`; a `learning_graph` edge referencing a node that
was never declared; ...). This module is the second, independent gate
that catches exactly that class of problem. It does NOT redesign or
replace `validate_chapter` -- see `modules/validator.py`'s own updated
call site, which now runs both gates in sequence.

RULES IMPLEMENTED (per the task spec's own list, one `_check_*` function
each, composed by `validate_structural_completeness()` at the bottom):
  1. `_check_required_sections`       -- every top-level section the
                                          schema requires is present (not
                                          silently filled -- *flagged*).
  2. `_check_identity`                -- every canonical object (and every
                                          topic) has a non-empty `id`; no
                                          two objects anywhere in the
                                          document share an `id` or `urn`.
  3. `_check_chapter_membership`      -- every canonical object has a
                                          `chapter_reference`, and every
                                          object in the document agrees on
                                          the same one (a Chapter JSON
                                          describes exactly one chapter).
  4. `_check_topic_id_references`     -- every `topic_ids` entry (on any
                                          canonical object) resolves to a
                                          real `topics[].id`.
  5. `_check_concept_id_references`   -- every `concept_ids` entry (on any
                                          canonical object) AND every
                                          `TopicNode.concepts` entry (A4's
                                          canonical concept reference)
                                          resolves to a real `concepts[].id`.
  6. `_check_reverse_reference_consistency` -- forward link (object ->
                                          topic via `topic_ids`) and
                                          reverse link (topic -> object via
                                          the matching `TopicNode` list
                                          field, `modules.topic_linker.
                                          TOPIC_REVERSE_FIELDS`) agree with
                                          each other in both directions;
                                          same for concept<->topic.
  7. `_check_orphan_objects`          -- canonical objects linked to no
                                          topic at all, and topics that are
                                          neither reachable from the
                                          hierarchy nor referenced by
                                          anything.
  8. `_check_duplicate_references`    -- duplicate entries inside a single
                                          reference list (`topic_ids`,
                                          `concept_ids`, `children`, graph
                                          `nodes`, ...) and duplicate graph
                                          edges.
  9. `_check_broken_graph_edges`      -- every `learning_graph`/
                                          `concept_graph` edge's
                                          source/target resolves to a
                                          declared node, and every declared
                                          node resolves to a real
                                          topic/concept id.
  10. `_check_missing_provenance`     -- every canonical object carries at
                                          least one real provenance fact
                                          (not an all-`None` envelope).
  11. `_check_parent_child_hierarchy` -- `TopicNode.parent`/`children`
                                          agree with each other, contain no
                                          cycle, and `topic_tree` (the
                                          nested view `json_writer.
                                          _build_topic_tree` derives from
                                          the same flat list) contains
                                          every topic exactly once.
  12. `_check_source_text_leakage`     -- (Milestone 3) no canonical
                                          object/topic/page/block/
                                          educational_object carries a
                                          field name that only ever means
                                          "raw copied textbook prose"
                                          (ERROR), and every AI-paraphrased
                                          free-text field Phase 1 IS
                                          allowed to carry stays within
                                          its word cap (WARNING if not --
                                          a possible leak of source text
                                          into a paraphrase-only field).

Every rule returns a list of issue dicts and NEVER raises on malformed
input -- a rule that cannot make sense of a section treats that as a
finding (an ERROR issue), never as "nothing to check". The top-level
entry point additionally wraps every rule call in its own try/except so
that one rule's bug can never make the *whole* validator silently report
"pass" (a corollary of the task's "must never silently pass structurally
incomplete output" requirement, applied to the validator's own
robustness): a crashing rule is recorded as a failed check and turns the
overall report into `status="fail"`, exactly like a real structural
error would.

SEVERITY: every issue is classified ERROR, WARNING, or INFO (the task
spec's own three-level scheme):
  - ERROR   -- the document is structurally broken (a reference points at
              nothing, an id collides, a required section is missing).
              Any ERROR makes the overall report `status="fail"`.
  - WARNING -- the document is internally inconsistent or incomplete in a
              way that will degrade a downstream consumer (a reverse
              reference is missing, an object has no provenance, a
              reference list has a duplicate) but is not itself a broken
              pointer.
  - INFO    -- worth surfacing but not actionable on its own (a topic
              structurally has no content at all, which is a normal shape
              for a pure "section heading" topic).

OUT OF SCOPE (deliberately, per "do not redesign the architecture"):
  - `TopicNode.prerequisites` / `related_topics` / `next_topics` are
    natural-language fields (pipeline.py populates `next_topics` with
    TITLE strings, and `prerequisites`/`related_topics` come straight
    from free-form VLM output) -- never validated as id references here.
    Only `topic_ids` / `concept_ids` / `TopicNode.concepts` are the
    documented canonical-reference fields (see schemas/chapter_schema.py's
    A4 docstring on `TopicNode.concepts`), and only those are checked
    against #4/#5 above.
  - `Concept.related_concepts` holds concept NAMES, not ids (see
    `graph_builder.build_concept_graph`'s own `name_to_id` lookup) -- not
    checked as an id reference either, for the same reason.
  - This module reads `chapter_dict` only. It never mutates it, never
    calls the VLM, never talks to storage, and never regenerates an
    id/urn to "fix" anything -- purely a read-only second validation gate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import logging

from schemas.chapter_schema import ChapterJSON
from modules.topic_linker import TOPIC_REVERSE_FIELDS
from config import MAX_SEMANTIC_DESCRIPTION_WORDS, MAX_CAPTION_WORDS

logger = logging.getLogger("ncert_pipeline.structural_validator")

STRUCTURAL_VALIDATION_VERSION = "1.0.0"

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

# --------------------------------------------------------------------------
# Section inventory
# --------------------------------------------------------------------------

# Every top-level ChapterJSON field, in the schema's own declared order --
# used only to detect a section that is missing OUTRIGHT (a key absent
# from the dict), which is different from (and a stronger finding than)
# `modules.validator.fill_missing_sections`'s silent []/{} fill. Derived
# from the schema itself (never a second hand-maintained list) so this
# module can't drift from schemas/chapter_schema.py.
REQUIRED_SECTIONS: List[str] = list(ChapterJSON.model_fields.keys())

# Top-level list-sections whose entries are CanonicalObjectBase-derived
# (id/urn/object_type/topic_ids/concept_ids/provenance/...) per
# schemas/chapter_schema.py. `topics`/`pages`/`blocks`/`educational_objects`
# are excluded -- TopicNode/PageInfo/AnnotatedBlock/EducationalObject are
# NOT CanonicalObjectBase subclasses (see that file) and are validated by
# their own, narrower rules below instead (topic hierarchy, provenance is
# not expected on those at all).
CANONICAL_OBJECT_SECTIONS: List[str] = [
    "concepts", "glossary", "definitions", "examples", "activities",
    "figures", "tables", "equations", "diagrams", "charts", "graphs",
    "maps", "timelines", "boxes", "notes", "warnings",
]

# section name (plural, as it appears on ChapterJSON) -> object_type
# (singular, as `modules.topic_linker.TOPIC_REVERSE_FIELDS` and
# `canonical.canonical_fields(object_type=...)` key it). One-to-one with
# CANONICAL_OBJECT_SECTIONS above.
_SECTION_TO_OBJECT_TYPE: Dict[str, str] = {
    "concepts": "concept",
    "glossary": "glossary_entry",
    "definitions": "definition",
    "examples": "example",
    "activities": "activity",
    "figures": "figure",
    "tables": "table",
    "equations": "equation",
    "diagrams": "diagram",
    "charts": "chart",
    "graphs": "graph",
    "maps": "map",
    "timelines": "timeline",
    "boxes": "box",
    "notes": "note",
    "warnings": "warning",
}


# --------------------------------------------------------------------------
# Issue construction (mirrors knowledge_graph/validation.py's own
# `_issue`/`_error`/`_warning` convention -- plain dicts, not a dataclass,
# since this report is meant to be stored as-is in `extraction_logs`, same
# "plain, storable dict" reasoning that module already documents).
# --------------------------------------------------------------------------

def _issue(
    severity: str, rule: str, message: str, *,
    section: Optional[str] = None, object_id: Optional[str] = None,
    object_type: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if section is not None:
        d["section"] = section
    if object_id is not None:
        d["object_id"] = object_id
    if object_type is not None:
        d["object_type"] = object_type
    if details:
        d["details"] = details
    return d


def _error(rule: str, message: str, **kw: Any) -> Dict[str, Any]:
    return _issue(ERROR, rule, message, **kw)


def _warn(rule: str, message: str, **kw: Any) -> Dict[str, Any]:
    return _issue(WARNING, rule, message, **kw)


def _info(rule: str, message: str, **kw: Any) -> Dict[str, Any]:
    return _issue(INFO, rule, message, **kw)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def _get_section(chapter_dict: Dict[str, Any], section: str) -> List[Any]:
    """Read-only accessor: returns `chapter_dict[section]` if it is a
    list, else `[]`. Never raises, never mutates `chapter_dict` -- a
    section that is missing or the wrong type is itself reported by
    `_check_required_sections`; every other rule just treats it as empty
    so one malformed section can't crash the other ten checks."""
    value = chapter_dict.get(section)
    return value if isinstance(value, list) else []


def _get_dict_section(chapter_dict: Dict[str, Any], section: str) -> Dict[str, Any]:
    value = chapter_dict.get(section)
    return value if isinstance(value, dict) else {}


def _iter_canonical_objects(chapter_dict: Dict[str, Any]) -> Iterable[Tuple[str, int, Dict[str, Any]]]:
    """Yields (section, index, obj) for every well-formed (dict) entry
    across every `CANONICAL_OBJECT_SECTIONS` list. Silently skips
    non-dict entries here -- `_check_identity` is the one place that
    reports those (`malformed_object_entry`), so callers of this helper
    never need to re-check `isinstance`."""
    for section in CANONICAL_OBJECT_SECTIONS:
        for idx, obj in enumerate(_get_section(chapter_dict, section)):
            if isinstance(obj, dict):
                yield section, idx, obj


def _obj_label(section: str, idx: int, obj: Dict[str, Any]) -> str:
    oid = obj.get("id")
    return oid if isinstance(oid, str) and oid else f"{section}[{idx}]"


# --------------------------------------------------------------------------
# 1. Required sections
# --------------------------------------------------------------------------

def _check_required_sections(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Unlike `modules.validator.fill_missing_sections` (which silently
    defaults a missing section to `[]`/`{}` so downstream code never
    KeyErrors), this rule treats a section that is missing OUTRIGHT as a
    genuine structural-completeness finding: it means whatever produced
    this dict never even attempted that part of the document. Runs
    BEFORE `fill_missing_sections` in the real `validate_chapter` call
    order (see modules/validator.py), so it sees the document as it
    actually arrived."""
    issues: List[Dict[str, Any]] = []
    for section in REQUIRED_SECTIONS:
        if section not in chapter_dict:
            issues.append(_error(
                "missing_required_section",
                f"required top-level section '{section}' is absent from the document",
                section=section,
            ))
    return issues


# --------------------------------------------------------------------------
# 2. Identity
# --------------------------------------------------------------------------

def _check_identity(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    ids_seen: Dict[str, List[str]] = {}   # id -> [locations]
    urns_seen: Dict[str, List[str]] = {}  # urn -> [locations]

    def _register(section: str, idx: int, obj: Dict[str, Any], object_type: Optional[str]) -> None:
        location = f"{section}[{idx}]"
        oid = obj.get("id")
        if not isinstance(oid, str) or not oid.strip():
            issues.append(_error(
                "missing_identity", f"{location} has no valid 'id' (identity is required)",
                section=section, object_type=object_type, details={"location": location},
            ))
        else:
            ids_seen.setdefault(oid, []).append(location)

        urn = obj.get("urn")
        if urn is None or (isinstance(urn, str) and not urn.strip()):
            issues.append(_warn(
                "missing_urn", f"{location} (id={oid!r}) has no 'urn'",
                section=section, object_id=oid, object_type=object_type,
            ))
        elif isinstance(urn, str):
            urns_seen.setdefault(urn, []).append(location)
        else:
            issues.append(_warn(
                "urn_wrong_type", f"{location} (id={oid!r}) 'urn' is not a string",
                section=section, object_id=oid, object_type=object_type,
            ))

    # -- topics: identity-bearing structural objects, even though they
    # are not CanonicalObjectBase subclasses (see module docstring). --
    for idx, t in enumerate(_get_section(chapter_dict, "topics")):
        if not isinstance(t, dict):
            issues.append(_error(
                "malformed_object_entry", f"topics[{idx}] is not an object",
                section="topics", details={"index": idx},
            ))
            continue
        _register("topics", idx, t, "topic")

    # -- every canonical object section --
    for section in CANONICAL_OBJECT_SECTIONS:
        object_type = _SECTION_TO_OBJECT_TYPE[section]
        raw = chapter_dict.get(section)
        if not isinstance(raw, list):
            continue
        for idx, obj in enumerate(raw):
            if not isinstance(obj, dict):
                issues.append(_error(
                    "malformed_object_entry", f"{section}[{idx}] is not an object",
                    section=section, object_type=object_type, details={"index": idx},
                ))
                continue
            _register(section, idx, obj, object_type)
            declared_type = obj.get("object_type")
            if not isinstance(declared_type, str) or not declared_type.strip():
                issues.append(_warn(
                    "missing_object_type", f"{section}[{idx}] (id={obj.get('id')!r}) has no 'object_type'",
                    section=section, object_id=obj.get("id"), object_type=object_type,
                ))

    for oid, locations in ids_seen.items():
        if len(locations) > 1:
            issues.append(_error(
                "duplicate_object_id",
                f"id {oid!r} is used by {len(locations)} different objects: {locations}",
                object_id=oid, details={"locations": locations},
            ))

    for urn, locations in urns_seen.items():
        if len(locations) > 1:
            issues.append(_error(
                "duplicate_urn",
                f"urn {urn!r} is used by {len(locations)} different objects: {locations}",
                details={"urn": urn, "locations": locations},
            ))

    return issues


# --------------------------------------------------------------------------
# 3. Chapter membership
# --------------------------------------------------------------------------

def _check_chapter_membership(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A Chapter JSON describes exactly one chapter, so every canonical
    object's `chapter_reference` must (a) be set and (b) agree with every
    other object's. We deliberately do NOT try to recompute the expected
    value from `document`/`chapter_metadata` (that would require
    reproducing `pipeline.py`'s `book_slug` input, which this dict does
    not carry) -- internal agreement is the structural fact this dict
    itself can prove or disprove."""
    issues: List[Dict[str, Any]] = []
    values: Counter = Counter()
    missing: List[str] = []

    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        ref = obj.get("chapter_reference")
        label = _obj_label(section, idx, obj)
        if not isinstance(ref, str) or not ref.strip():
            missing.append(label)
            issues.append(_error(
                "missing_chapter_reference",
                f"{label} has no 'chapter_reference'",
                section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
            ))
        else:
            values[ref] += 1

    if len(values) > 1:
        majority_ref, _ = values.most_common(1)[0]
        for section, idx, obj in _iter_canonical_objects(chapter_dict):
            ref = obj.get("chapter_reference")
            if isinstance(ref, str) and ref.strip() and ref != majority_ref:
                issues.append(_error(
                    "chapter_reference_mismatch",
                    f"{_obj_label(section, idx, obj)} has chapter_reference "
                    f"{ref!r}, but the rest of the document uses {majority_ref!r}",
                    section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
                    details={"expected": majority_ref, "actual": ref},
                ))

    return issues


# --------------------------------------------------------------------------
# 4. topic_ids -> topics[].id
# --------------------------------------------------------------------------

def _valid_topic_ids(chapter_dict: Dict[str, Any]) -> Set[str]:
    return {
        t["id"] for t in _get_section(chapter_dict, "topics")
        if isinstance(t, dict) and isinstance(t.get("id"), str) and t["id"]
    }


def _check_topic_id_references(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    valid_topic_ids = _valid_topic_ids(chapter_dict)

    def _check_list(section: str, idx: int, obj: Dict[str, Any], field: str) -> None:
        refs = obj.get(field)
        if not isinstance(refs, list):
            return
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                issues.append(_error(
                    "invalid_topic_reference",
                    f"{_obj_label(section, idx, obj)}.{field} contains a non-string/empty entry: {ref!r}",
                    section=section, object_id=obj.get("id"), details={"field": field, "value": ref},
                ))
            elif ref not in valid_topic_ids:
                issues.append(_error(
                    "broken_topic_reference",
                    f"{_obj_label(section, idx, obj)}.{field} references topic "
                    f"{ref!r}, which does not exist in 'topics'",
                    section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
                    details={"field": field, "topic_id": ref},
                ))

    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        _check_list(section, idx, obj, "topic_ids")

    # topics' own `parent`/`children` are checked by the hierarchy rule
    # (#11), not here -- this rule is scoped to the `topic_ids` reference
    # field per the task spec's own wording.
    return issues


# --------------------------------------------------------------------------
# 5. concept_ids -> concepts[].id  (+ TopicNode.concepts, A4's canonical ref)
# --------------------------------------------------------------------------

def _valid_concept_ids(chapter_dict: Dict[str, Any]) -> Set[str]:
    return {
        c["id"] for c in _get_section(chapter_dict, "concepts")
        if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]
    }


def _check_concept_id_references(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    valid_concept_ids = _valid_concept_ids(chapter_dict)

    def _check_list(section: str, idx: int, obj: Dict[str, Any], field: str, label_obj: Dict[str, Any]) -> None:
        refs = obj.get(field)
        if not isinstance(refs, list):
            return
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                issues.append(_error(
                    "invalid_concept_reference",
                    f"{_obj_label(section, idx, label_obj)}.{field} contains a non-string/empty entry: {ref!r}",
                    section=section, object_id=label_obj.get("id"), details={"field": field, "value": ref},
                ))
            elif ref not in valid_concept_ids:
                issues.append(_error(
                    "broken_concept_reference",
                    f"{_obj_label(section, idx, label_obj)}.{field} references concept "
                    f"{ref!r}, which does not exist in 'concepts'",
                    section=section, object_id=label_obj.get("id"), object_type=label_obj.get("object_type"),
                    details={"field": field, "concept_id": ref},
                ))

    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        _check_list(section, idx, obj, "concept_ids", obj)

    # A4: TopicNode.concepts holds concept IDS (the canonical reference,
    # per schemas/chapter_schema.py's own TopicNode.concepts docstring) --
    # `concept_names` is the derived display list and is intentionally
    # NOT checked here.
    for idx, t in enumerate(_get_section(chapter_dict, "topics")):
        if isinstance(t, dict):
            _check_list("topics", idx, t, "concepts", t)

    return issues


# --------------------------------------------------------------------------
# 6. Reverse-reference consistency
# --------------------------------------------------------------------------

def _check_reverse_reference_consistency(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For every (object_type -> TopicNode reverse-list field) pair
    `modules.topic_linker.TOPIC_REVERSE_FIELDS` declares (the SAME table
    Milestone 1's own linker uses to populate these lists -- reused, not
    reimplemented), checks both directions:
      - forward: object.topic_ids says "I belong to topic T" -> T's
        reverse list should contain this object's id.
      - reverse: topic.<field> says "object O belongs to me" -> O should
        exist in the matching section AND O.topic_ids should contain
        this topic's id.
    Object types with no reverse field declared (`chart`/`graph`/`map`/
    `timeline`/`glossary_entry` -- see TOPIC_REVERSE_FIELDS' own comment
    on why those have no reverse slot on TopicNode today) are skipped
    entirely: there is nothing to be consistent WITH.
    """
    issues: List[Dict[str, Any]] = []
    topics = [t for t in _get_section(chapter_dict, "topics") if isinstance(t, dict) and t.get("id")]
    topics_by_id = {t["id"]: t for t in topics}

    for section in CANONICAL_OBJECT_SECTIONS:
        object_type = _SECTION_TO_OBJECT_TYPE[section]
        reverse_field = TOPIC_REVERSE_FIELDS.get(object_type)
        if not reverse_field:
            continue

        objects = [o for o in _get_section(chapter_dict, section) if isinstance(o, dict) and o.get("id")]
        objects_by_id = {o["id"]: o for o in objects}

        # forward -> reverse
        for obj in objects:
            for tid in obj.get("topic_ids") or []:
                topic = topics_by_id.get(tid)
                if topic is None:
                    continue  # already reported as broken_topic_reference (#4)
                bucket = topic.get(reverse_field)
                if not isinstance(bucket, list) or obj["id"] not in bucket:
                    issues.append(_warn(
                        "reverse_reference_missing",
                        f"{section}[id={obj['id']!r}] links to topic {tid!r} via "
                        f"topic_ids, but topics[id={tid!r}].{reverse_field} does "
                        f"not list it back",
                        section=section, object_id=obj["id"], object_type=object_type,
                        details={"topic_id": tid, "reverse_field": reverse_field},
                    ))

        # reverse -> forward
        for topic in topics:
            bucket = topic.get(reverse_field)
            if not isinstance(bucket, list):
                continue
            for oid in bucket:
                if not isinstance(oid, str) or not oid:
                    issues.append(_warn(
                        "invalid_reverse_reference",
                        f"topics[id={topic['id']!r}].{reverse_field} contains a "
                        f"non-string/empty entry: {oid!r}",
                        section="topics", object_id=topic["id"],
                        details={"reverse_field": reverse_field, "value": oid},
                    ))
                    continue
                target = objects_by_id.get(oid)
                if target is None:
                    issues.append(_error(
                        "broken_reverse_reference",
                        f"topics[id={topic['id']!r}].{reverse_field} references "
                        f"{oid!r}, which does not exist in '{section}'",
                        section="topics", object_id=topic["id"], object_type=object_type,
                        details={"reverse_field": reverse_field, section: oid},
                    ))
                elif topic["id"] not in (target.get("topic_ids") or []):
                    issues.append(_warn(
                        "reverse_reference_missing",
                        f"topics[id={topic['id']!r}].{reverse_field} lists "
                        f"{oid!r}, but {section}[id={oid!r}].topic_ids does not "
                        f"list this topic back",
                        section=section, object_id=oid, object_type=object_type,
                        details={"topic_id": topic["id"], "reverse_field": reverse_field},
                    ))

    return issues


# --------------------------------------------------------------------------
# 7. Orphan objects
# --------------------------------------------------------------------------

def _check_orphan_objects(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        topic_ids = obj.get("topic_ids")
        if not topic_ids:
            issues.append(_warn(
                "orphan_object",
                f"{_obj_label(section, idx, obj)} is not linked to any topic (empty topic_ids)",
                section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
            ))

    # A topic is a structural orphan if it is neither a declared root
    # (no parent, or parent unresolved -- reported separately by the
    # hierarchy rule), nor referenced as a child by any other topic, AND
    # carries no content of its own in any reverse-list/definitions/
    # concepts field. This is common and legitimate for a pure
    # "section heading" topic -- reported as INFO, not WARNING/ERROR.
    topics = [t for t in _get_section(chapter_dict, "topics") if isinstance(t, dict) and t.get("id")]
    referenced_as_child: Set[str] = set()
    for t in topics:
        for cid in t.get("children") or []:
            if isinstance(cid, str):
                referenced_as_child.add(cid)

    content_fields = [
        "concepts", "definitions", "examples", "activities", "figures",
        "tables", "equations", "diagrams", "charts", "graphs", "maps",
        "timelines", "boxes", "notes", "warnings",
    ]
    for t in topics:
        has_parent = bool(t.get("parent"))
        is_child_of_someone = t["id"] in referenced_as_child
        has_content = any(t.get(f) for f in content_fields)
        has_children = bool(t.get("children"))
        if not has_parent and not is_child_of_someone and not has_content and not has_children:
            issues.append(_info(
                "orphan_topic",
                f"topics[id={t['id']!r}] has no parent, is not any other "
                f"topic's child, and carries no content -- structurally isolated",
                section="topics", object_id=t["id"],
            ))

    return issues


# --------------------------------------------------------------------------
# 8. Duplicate references
# --------------------------------------------------------------------------

def _check_duplicate_references(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    def _check_list_field(section: str, obj_id: Any, field: str, values: Any) -> None:
        if not isinstance(values, list):
            return
        counts = Counter(v for v in values if isinstance(v, str))
        for v, n in counts.items():
            if n > 1:
                issues.append(_warn(
                    "duplicate_reference_in_list",
                    f"{section}[id={obj_id!r}].{field} contains {v!r} {n} times",
                    section=section, object_id=obj_id, details={"field": field, "value": v, "count": n},
                ))

    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        _check_list_field(section, obj.get("id"), "topic_ids", obj.get("topic_ids"))
        _check_list_field(section, obj.get("id"), "concept_ids", obj.get("concept_ids"))

    for t in _get_section(chapter_dict, "topics"):
        if not isinstance(t, dict):
            continue
        for field in ("children", "concepts", "keywords"):
            _check_list_field("topics", t.get("id"), field, t.get(field))

    for graph_section in ("learning_graph", "concept_graph"):
        graph = _get_dict_section(chapter_dict, graph_section)
        _check_list_field(graph_section, graph_section, "nodes", graph.get("nodes"))

        edges = graph.get("edges")
        if isinstance(edges, list):
            edge_keys = Counter()
            for e in edges:
                if isinstance(e, dict):
                    key = (e.get("source"), e.get("target"), e.get("relationship_type"))
                    edge_keys[key] += 1
            for key, n in edge_keys.items():
                if n > 1:
                    issues.append(_warn(
                        "duplicate_graph_edge",
                        f"{graph_section}.edges contains the edge "
                        f"{key[0]!r} -> {key[1]!r} ({key[2]!r}) {n} times",
                        section=graph_section,
                        details={"source": key[0], "target": key[1], "relationship_type": key[2], "count": n},
                    ))

    return issues


# --------------------------------------------------------------------------
# 9. Broken graph edges
# --------------------------------------------------------------------------

def _check_broken_graph_edges(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    valid_topic_ids = _valid_topic_ids(chapter_dict)
    valid_concept_ids = _valid_concept_ids(chapter_dict)

    def _check_graph(graph_section: str, valid_referent_ids: Set[str], referent_label: str) -> None:
        graph = _get_dict_section(chapter_dict, graph_section)
        nodes = graph.get("nodes")
        node_set = {n for n in nodes if isinstance(n, str)} if isinstance(nodes, list) else set()

        if isinstance(nodes, list):
            for n in nodes:
                if not isinstance(n, str) or not n:
                    issues.append(_error(
                        "invalid_graph_node",
                        f"{graph_section}.nodes contains a non-string/empty entry: {n!r}",
                        section=graph_section,
                    ))
                elif n not in valid_referent_ids:
                    issues.append(_warn(
                        "dangling_graph_node",
                        f"{graph_section}.nodes declares {n!r}, which does not "
                        f"exist among {referent_label}",
                        section=graph_section, object_id=n,
                    ))

        missing_nodes = valid_referent_ids - node_set
        if missing_nodes:
            issues.append(_warn(
                "graph_node_coverage_incomplete",
                f"{graph_section}.nodes is missing {len(missing_nodes)} "
                f"{referent_label} that exist in the document",
                section=graph_section, details={"missing": sorted(missing_nodes)},
            ))

        edges = graph.get("edges")
        if not isinstance(edges, list):
            return
        for i, e in enumerate(edges):
            if not isinstance(e, dict):
                issues.append(_error(
                    "malformed_graph_edge", f"{graph_section}.edges[{i}] is not an object",
                    section=graph_section, details={"index": i},
                ))
                continue
            source, target = e.get("source"), e.get("target")
            for role, ref in (("source", source), ("target", target)):
                if not isinstance(ref, str) or not ref:
                    issues.append(_error(
                        "malformed_graph_edge",
                        f"{graph_section}.edges[{i}].{role} is not a valid string: {ref!r}",
                        section=graph_section, details={"index": i, "role": role},
                    ))
                elif ref not in node_set:
                    issues.append(_error(
                        "broken_graph_edge",
                        f"{graph_section}.edges[{i}] references {role} {ref!r}, "
                        f"which is not declared in {graph_section}.nodes",
                        section=graph_section, object_id=ref,
                        details={"index": i, "role": role, "edge": {"source": source, "target": target}},
                    ))

    _check_graph("learning_graph", valid_topic_ids, "topics")
    _check_graph("concept_graph", valid_concept_ids, "concepts")
    return issues


# --------------------------------------------------------------------------
# 10. Missing provenance
# --------------------------------------------------------------------------

_PROVENANCE_SUBSTANCE_FIELDS = (
    "source_page", "source_block_id", "source_heading", "section",
    "bounding_box", "extraction_stage", "recognizer", "evidence_span",
)


def _check_missing_provenance(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for section, idx, obj in _iter_canonical_objects(chapter_dict):
        provenance = obj.get("provenance")
        label = _obj_label(section, idx, obj)
        if not isinstance(provenance, dict) or not provenance:
            issues.append(_warn(
                "missing_provenance", f"{label} has no 'provenance' object at all",
                section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
            ))
            continue
        has_substance = any(provenance.get(f) not in (None, "", [], {}) for f in _PROVENANCE_SUBSTANCE_FIELDS)
        if not has_substance:
            issues.append(_warn(
                "missing_provenance",
                f"{label}.provenance carries no source information "
                f"(source_page/source_block_id/extraction_stage/... are all empty)",
                section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
            ))
        if not provenance.get("timestamp"):
            issues.append(_info(
                "missing_provenance_timestamp", f"{label}.provenance has no 'timestamp'",
                section=section, object_id=obj.get("id"), object_type=obj.get("object_type"),
            ))
    return issues


# --------------------------------------------------------------------------
# 11. Parent-child hierarchy
# --------------------------------------------------------------------------

def _flatten_topic_tree(nodes: List[Any]) -> List[str]:
    """Read-only walk of `topic_tree` (the nested shape
    `json_writer._build_topic_tree` produces), collecting every node id
    in document order. Tolerates malformed nodes (returns whatever ids it
    can find) -- structural problems in the tree itself are reported by
    the caller, not raised here."""
    out: List[str] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if isinstance(nid, str) and nid:
            out.append(nid)
        out.extend(_flatten_topic_tree(n.get("children") or []))
    return out


def _check_parent_child_hierarchy(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    topics = [t for t in _get_section(chapter_dict, "topics") if isinstance(t, dict) and t.get("id")]
    topics_by_id = {t["id"]: t for t in topics}

    # parent -> children agreement, and dangling parent references.
    for t in topics:
        parent = t.get("parent")
        if parent is None:
            continue
        if not isinstance(parent, str) or not parent:
            issues.append(_error(
                "invalid_parent_reference",
                f"topics[id={t['id']!r}].parent is not a valid string: {parent!r}",
                section="topics", object_id=t["id"],
            ))
            continue
        parent_topic = topics_by_id.get(parent)
        if parent_topic is None:
            issues.append(_error(
                "broken_parent_reference",
                f"topics[id={t['id']!r}].parent references {parent!r}, "
                f"which does not exist in 'topics'",
                section="topics", object_id=t["id"], details={"parent": parent},
            ))
            continue
        children = parent_topic.get("children")
        if not isinstance(children, list) or t["id"] not in children:
            issues.append(_warn(
                "parent_child_mismatch",
                f"topics[id={t['id']!r}].parent is {parent!r}, but "
                f"topics[id={parent!r}].children does not list {t['id']!r} back",
                section="topics", object_id=t["id"], details={"parent": parent},
            ))
        parent_level, child_level = parent_topic.get("level"), t.get("level")
        if isinstance(parent_level, int) and isinstance(child_level, int) and child_level != parent_level + 1:
            issues.append(_warn(
                "unexpected_level_jump",
                f"topics[id={t['id']!r}] has level {child_level}, but its parent "
                f"{parent!r} has level {parent_level} (expected {parent_level + 1})",
                section="topics", object_id=t["id"],
                details={"parent_level": parent_level, "level": child_level},
            ))

    # children -> parent agreement + dangling child references.
    for t in topics:
        children = t.get("children")
        if not isinstance(children, list):
            continue
        for cid in children:
            if not isinstance(cid, str) or not cid:
                issues.append(_error(
                    "invalid_child_reference",
                    f"topics[id={t['id']!r}].children contains a non-string/empty entry: {cid!r}",
                    section="topics", object_id=t["id"],
                ))
                continue
            child_topic = topics_by_id.get(cid)
            if child_topic is None:
                issues.append(_error(
                    "broken_child_reference",
                    f"topics[id={t['id']!r}].children references {cid!r}, "
                    f"which does not exist in 'topics'",
                    section="topics", object_id=t["id"], details={"child": cid},
                ))
            elif child_topic.get("parent") != t["id"]:
                issues.append(_warn(
                    "parent_child_mismatch",
                    f"topics[id={t['id']!r}].children lists {cid!r}, but "
                    f"topics[id={cid!r}].parent is {child_topic.get('parent')!r}, not {t['id']!r}",
                    section="topics", object_id=cid, details={"expected_parent": t["id"]},
                ))

    # Cycle detection: walk every topic's parent chain.
    visited_globally: Set[str] = set()
    for start in topics_by_id:
        if start in visited_globally:
            continue
        chain: List[str] = []
        seen: Set[str] = set()
        cur: Optional[str] = start
        while cur is not None:
            if cur in seen:
                cycle = chain[chain.index(cur):] + [cur]
                issues.append(_error(
                    "hierarchy_cycle_detected",
                    f"topics parent-chain starting at {start!r} contains a cycle: {' -> '.join(cycle)}",
                    section="topics", object_id=start, details={"cycle": cycle},
                ))
                break
            seen.add(cur)
            chain.append(cur)
            visited_globally.add(cur)
            nxt = topics_by_id.get(cur)
            cur = nxt.get("parent") if isinstance(nxt, dict) else None
            if not isinstance(cur, str) or cur not in topics_by_id:
                break

    # topic_tree <-> flat topics[] agreement.
    topic_tree = chapter_dict.get("topic_tree")
    if isinstance(topic_tree, list) and topics:
        flat_ids = _flatten_topic_tree(topic_tree)
        flat_counts = Counter(flat_ids)
        topic_id_set = set(topics_by_id.keys())

        for tid, n in flat_counts.items():
            if n > 1:
                issues.append(_error(
                    "duplicate_topic_tree_node",
                    f"topic_tree contains node {tid!r} {n} times",
                    section="topic_tree", object_id=tid, details={"count": n},
                ))

        missing_from_tree = topic_id_set - set(flat_ids)
        for tid in missing_from_tree:
            issues.append(_error(
                "topic_missing_from_tree",
                f"topics[id={tid!r}] does not appear anywhere in 'topic_tree'",
                section="topic_tree", object_id=tid,
            ))

        extra_in_tree = set(flat_ids) - topic_id_set
        for tid in extra_in_tree:
            issues.append(_error(
                "topic_tree_dangling_node",
                f"topic_tree references {tid!r}, which does not exist in 'topics'",
                section="topic_tree", object_id=tid,
            ))

    return issues


# --------------------------------------------------------------------------
# 12. Source-text leakage (Milestone 3 -- Copyright-Safe Serialization)
# --------------------------------------------------------------------------
#
# Phase 1 is a structural compiler: it may serialize identities,
# headings/labels, hierarchy, references, provenance, numeric values, and
# short AI-*paraphrased* (never quoted) summaries that are already
# word-capped at generation time by `modules.semantic_processor.
# _enforce_word_cap` (MAX_SEMANTIC_DESCRIPTION_WORDS). It must NEVER
# serialize copied textbook prose -- paragraphs, verbatim definitions,
# copied examples/descriptions -- and it must never generate its own AI
# summaries either (that is Phase 2's job). This rule is the independent,
# read-only second gate for that requirement: it never trusts the
# generator (semantic_processor.py, content_blocks.py, ...) to have
# gotten it right, exactly the same "second gate" relationship every
# other rule in this module has to its own upstream producer.
#
# Two independent signals are checked, on every dict found in ANY
# top-level list section (CANONICAL_OBJECT_SECTIONS, plus `topics`,
# `pages`, `blocks`, `educational_objects` -- i.e. every place pipeline.py
# could plausibly have attached a field to):
#
#   (a) BANNED FIELD NAMES -- a field name that only ever means "here is
#       the raw source paragraph" (see `_BANNED_PROSE_FIELD_NAMES` below).
#       Presence is an ERROR regardless of content or length: the field
#       existing at all is the violation, matching the task spec's "Do
#       NOT serialize textbook paragraphs / copied explanations / copied
#       definitions / copied examples / copied descriptions" -- there is
#       no safe length for a field whose entire purpose is to hold one of
#       those.
#
#   (b) OVERLONG ALLOWED-PROSE FIELDS -- the small set of fields Phase 1
#       IS allowed to carry free text in (`_ALLOWED_PROSE_FIELDS`, each
#       AI-paraphrased and word-capped at generation time) exceeding its
#       own word cap. `_enforce_word_cap` already truncates these at
#       generation time; this is the same "never trust the generator"
#       second gate as every other rule here -- a WARNING (not an ERROR)
#       because an overlong *paraphrase* is a quality problem to fix, not
#       proof of copied prose the way a banned field name is.
#
# Deliberately NOT attempted here (out of scope for a purely structural,
# read-only rule, not a redesign): fuzzy/n-gram matching against the
# actual source PDF text to detect near-verbatim paraphrase-in-name-only.
# That needs the original page text as an input this module never
# receives (`chapter_dict` only, per this module's own docstring) and
# belongs, if ever built, in Stage D/E's own pipeline where that text is
# still in scope -- this rule only catches the field-name and word-count
# signals that are visible from the serialized IR alone.
_ALLOWED_PROSE_FIELDS: Dict[str, int] = {
    "semantic_summary": MAX_SEMANTIC_DESCRIPTION_WORDS,
    "visual_summary": MAX_SEMANTIC_DESCRIPTION_WORDS,
    "semantic_description": MAX_SEMANTIC_DESCRIPTION_WORDS,
    "semantic_meaning": MAX_SEMANTIC_DESCRIPTION_WORDS,
    # Milestone 3.3: Figure/Table/Diagram `caption`/`title` are PDF/OCR-
    # sourced short labels, not AI paraphrase -- but they belong in this
    # dict for the same reason semantic_meaning etc. do: `modules.
    # copyright_sanitizer.sanitize_visual_captions` now enforces
    # MAX_CAPTION_WORDS at generation time, and this is the "never trust
    # the generator" second gate that WARNs if one ever slips through over
    # cap, instead of that leak going undetected.
    "caption": MAX_CAPTION_WORDS,
    "title": MAX_CAPTION_WORDS,
}

_BANNED_PROSE_FIELD_NAMES: Set[str] = {
    "raw_text", "source_text", "full_text", "paragraph", "paragraph_text",
    "copied_text", "verbatim_text", "book_text", "extracted_text",
    "original_text", "definition_text", "example_text", "explanation",
    "explanation_text", "description_text", "summary_text", "body_text",
    "content_text", "chapter_text", "textbook_text",
}

# Every top-level list section a leaked field could plausibly land in --
# CANONICAL_OBJECT_SECTIONS plus the four non-CanonicalObjectBase list
# sections (`topics`/`pages`/`blocks`/`educational_objects`) this module's
# other rules already treat separately from canonical objects.
_LEAKAGE_SCAN_SECTIONS: Tuple[str, ...] = tuple(CANONICAL_OBJECT_SECTIONS) + (
    "topics", "pages", "blocks", "educational_objects",
)


def _check_source_text_leakage(chapter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    for section in _LEAKAGE_SCAN_SECTIONS:
        for idx, obj in enumerate(_get_section(chapter_dict, section)):
            if not isinstance(obj, dict):
                continue
            label = _obj_label(section, idx, obj)

            for field in sorted(_BANNED_PROSE_FIELD_NAMES):
                if field in obj and obj.get(field):
                    issues.append(_error(
                        "banned_prose_field_present",
                        f"{label} carries a {field!r} field -- Phase 1 must never "
                        f"serialize raw/copied textbook prose, only structural data",
                        section=section, object_id=obj.get("id"),
                        object_type=obj.get("object_type"),
                        details={"field": field},
                    ))

            for field, cap in _ALLOWED_PROSE_FIELDS.items():
                value = obj.get(field)
                if isinstance(value, str) and value.strip():
                    word_count = len(value.split())
                    if word_count > cap:
                        issues.append(_warn(
                            "prose_field_exceeds_word_cap",
                            f"{label}.{field} is {word_count} words, over the "
                            f"{cap}-word cap -- possible source-text leak into an "
                            f"AI-paraphrase-only field",
                            section=section, object_id=obj.get("id"),
                            object_type=obj.get("object_type"),
                            details={"field": field, "word_count": word_count, "cap": cap},
                        ))

    return issues


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

_RULES: List[Tuple[str, Any]] = [
    ("required_sections", _check_required_sections),
    ("identity", _check_identity),
    ("chapter_membership", _check_chapter_membership),
    ("topic_id_references", _check_topic_id_references),
    ("concept_id_references", _check_concept_id_references),
    ("reverse_reference_consistency", _check_reverse_reference_consistency),
    ("orphan_objects", _check_orphan_objects),
    ("duplicate_references", _check_duplicate_references),
    ("broken_graph_edges", _check_broken_graph_edges),
    ("missing_provenance", _check_missing_provenance),
    ("parent_child_hierarchy", _check_parent_child_hierarchy),
    ("source_text_leakage", _check_source_text_leakage),
]


def validate_structural_completeness(chapter_dict: Any) -> Dict[str, Any]:
    """The single entry point this module exposes. Runs every rule above
    against `chapter_dict` and returns a plain, storable report dict
    (same "plain dict, not a dataclass" convention `knowledge_graph.
    validation.validate_knowledge_graph` already uses, for the same
    reason: this report is meant to be stashed directly into
    `extraction_logs`).

    Never raises. If `chapter_dict` itself is not a dict, or any
    individual rule raises internally, that is recorded as an ERROR
    issue (not silently skipped) and the overall report's `status` is
    `"fail"` -- this is what makes good on "the validator must never
    silently pass structurally incomplete output": a rule that cannot
    run at all is treated as a rule that found a problem, never as one
    that found nothing.

    Read-only: `chapter_dict` is never mutated.
    """
    issues: List[Dict[str, Any]] = []
    rules_run: List[str] = []
    rules_crashed: List[str] = []

    if not isinstance(chapter_dict, dict):
        issues.append(_error(
            "invalid_input",
            f"validate_structural_completeness() expects a dict, got {type(chapter_dict).__name__}",
        ))
        chapter_dict = {}
    else:
        for name, fn in _RULES:
            try:
                issues.extend(fn(chapter_dict))
                rules_run.append(name)
            except Exception as exc:  # noqa: BLE001 -- see docstring: never silently skip
                rules_crashed.append(name)
                logger.exception("Structural validation rule '%s' crashed", name)
                issues.append(_error(
                    f"{name}_check_crashed",
                    f"structural validation rule '{name}' raised {exc.__class__.__name__}: {exc}",
                    details={"rule": name},
                ))

    errors = [i for i in issues if i["severity"] == ERROR]
    warnings_ = [i for i in issues if i["severity"] == WARNING]
    info = [i for i in issues if i["severity"] == INFO]

    status = "fail" if (errors or rules_crashed) else "pass"

    issues_by_rule = dict(Counter(i["rule"] for i in issues))

    report = {
        "validator": "structural_validator",
        "validator_version": STRUCTURAL_VALIDATION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "rules_run": rules_run,
        "rules_crashed": rules_crashed,
        "issues": issues,
        "errors": errors,
        "warnings": warnings_,
        "info": info,
        "summary": {
            "total_issues": len(issues),
            "error_count": len(errors),
            "warning_count": len(warnings_),
            "info_count": len(info),
            "issues_by_rule": issues_by_rule,
        },
    }
    logger.info(
        "Structural validation: status=%s errors=%d warnings=%d info=%d",
        status, len(errors), len(warnings_), len(info),
    )
    return report
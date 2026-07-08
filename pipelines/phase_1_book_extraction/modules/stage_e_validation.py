"""
stage_e_validation.py — Stage E: Educational Validation.

Responsibility (and ONLY this responsibility): validate educational
knowledge. Pure deterministic validation — no VLM calls, no semantic
image deduplication, only exact duplicate detection, per the frozen spec.

Input:  Educational Objects (stage_d_extraction output)
Output: Validated Educational Objects — NOT Master JSON. Master JSON
        belongs entirely to Phase 2 (schemas/chapter_schema.py +
        modules/graph_builder.py, both explicitly out of Phase 1's scope).

Removes:
    - duplicate formulas
    - duplicate definitions
    - duplicate arithmetic (i.e. duplicate discarded-substitution counts
      are not itself a thing to dedupe against; "arithmetic" here means an
      educational object whose only content is a bare numeric expression
      that slipped through Stage D with no reusable formula attached)
Normalizes: whitespace/casing on the fields used for the dedupe key only —
    the object's own field values are left exactly as Stage D produced
    them, since normalizing user-facing content is not this stage's job.
Preserves: block_id, bbox, page, lineage (source/confidence) on every
    surviving object.
"""
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("ncert_pipeline.stage_e")


def _normalize_for_dedupe(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _dedupe_key(obj: Dict[str, Any]) -> Tuple[str, str]:
    obj_type = obj.get("educational_object_type", "")
    if obj_type == "formula_or_procedure":
        return ("formula", _normalize_for_dedupe(obj.get("reusable_formula", "")))
    if obj_type == "concept":
        return ("definition", _normalize_for_dedupe(obj.get("term", "")))
    # Everything else (visual/unclassified/ambiguous) is keyed by its own
    # block_id, which is already unique per block -- these categories were
    # never candidates for cross-block duplication in the first place.
    return ("other", obj.get("block_id", obj.get("id", "")))


def _is_bare_arithmetic(obj: Dict[str, Any]) -> bool:
    """An educational object that ended up with no reusable formula/term at
    all and whose only trace is a bare numeric expression is exactly the
    'stores worked-example calculations directly into JSON' failure mode
    the architecture review flagged -- drop it here rather than let it
    reach the validated output with nothing educationally reusable in it."""
    if obj.get("educational_object_type") != "formula_or_procedure":
        return False
    formula = (obj.get("reusable_formula") or "").strip()
    if formula:
        return False
    # No reusable formula AND no VLM-derived procedure either -> nothing
    # left worth keeping.
    return not (obj.get("reusable_procedure") or "").strip()


def validate_educational_objects(objects: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Returns (validated_objects, report). Never raises: a batch run
    should not fail because one object dedupes oddly; anything ambiguous
    is kept and flagged in the report rather than silently dropped."""
    report = {
        "input_count": len(objects),
        "removed_duplicate_formulas": 0,
        "removed_duplicate_definitions": 0,
        "removed_bare_arithmetic": 0,
        "warnings": [],
    }

    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    validated: List[Dict[str, Any]] = []

    for obj in objects:
        if _is_bare_arithmetic(obj):
            report["removed_bare_arithmetic"] += 1
            continue

        key = _dedupe_key(obj)
        if key[0] in ("formula", "definition") and key[1]:
            if key in seen:
                # Preserve lineage of the duplicate by recording it against
                # the surviving object rather than silently discarding it.
                survivor = seen[key]
                survivor.setdefault("duplicate_lineage", []).append(
                    {"block_id": obj.get("block_id"), "page": obj.get("page")})
                if key[0] == "formula":
                    report["removed_duplicate_formulas"] += 1
                else:
                    report["removed_duplicate_definitions"] += 1
                continue
            seen[key] = obj

        validated.append(obj)

    report["output_count"] = len(validated)
    logger.info(
        "Stage E: %d -> %d educational object(s) (removed %d duplicate formula(s), "
        "%d duplicate definition(s), %d bare-arithmetic object(s)).",
        report["input_count"], report["output_count"], report["removed_duplicate_formulas"],
        report["removed_duplicate_definitions"], report["removed_bare_arithmetic"],
    )
    return validated, report

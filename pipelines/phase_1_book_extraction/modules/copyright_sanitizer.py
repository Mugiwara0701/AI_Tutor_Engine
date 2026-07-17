"""
modules/copyright_sanitizer.py — Milestone 3.2: Copyright-Safe Serialization.

Implements the HIGH-RISK recommendations from the Milestone 3.1 audit
(M3.1_AUDIT.md §2.1, §4). This module is the single, centrally-enforced
checkpoint the audit's architectural concern #1 says does not currently
exist ("a single, centrally-enforced 'any prose-shaped field must pass
through paraphrase+cap before serialization' checkpoint does not
currently exist"): every HIGH-risk field this module knows about is
sanitized here, in ONE place, regardless of which recognizer or code
path produced it.

Scope (per M3.1 §2.1, HIGH only — this milestone's instructions are to
implement the HIGH-risk findings; MEDIUM/LOW findings are left for a
future milestone, see MILESTONE_3_2_SUMMARY.md "Deferred to future
milestones"):

  1. `reusable_procedure` / `procedure_steps` on `formula_or_procedure`
     Educational Objects produced by the DETERMINISTIC recognizers
     (ProcedureRecognizer, AlgorithmRecognizer, JournalProcedureRecognizer
     — modules/recognizers/procedure_recognizers.py). These joined raw
     OCR/PDF line text with no cap and no paraphrase.
     -> REPLACED WITH STRUCTURAL METADATA (step count + step-marker
     shape per step), per the audit's own recommended action.

  2. `reusable_syntax` on `programming_syntax` Educational Objects
     produced by the DETERMINISTIC recognizers (ProgrammingSyntaxRecognizer,
     PseudocodeRecognizer — modules/recognizers/programming_recognizers.py).
     Full code/pseudocode snippets kept verbatim by design.
     -> ARCHITECTURAL DECISION (documented below, see
     `PRESERVE_CODE_SNIPPETS_VERBATIM`): the audit flagged this as
     "REVIEW REQUIRED — decide product intent first" rather than giving
     a single recommended action, since code snippets may be an
     intentional, in-scope product feature for a CS tutor. Absent an
     explicit product/legal sign-off (this milestone has none), the safe
     default is the same as every other HIGH-risk finding: replace with
     structural metadata. A config flag lets a future milestone flip this
     on for programming_syntax objects specifically, once that sign-off
     exists, without touching this module's logic again.

  3. `raw_text` on `Equation` records (pipeline.py's flat top-level
     `equations` list — sourced from layout_detector/stage_a_geometry).
     Stored unconditionally so "nothing disappears from the Master JSON".
     -> REMOVED from the production record; replaced with a boolean
     structural hint (`has_raw_text_hint`). The original text is not
     silently lost — the caller receives it back as a debug entry (see
     `EquationSanitizeResult`/`ObjectSanitizeResult` below) for the
     debug-only extraction artifact, per the milestone's "keep debugging
     information in debug/extraction artifacts rather than production
     JSON" requirement.

  4. `vlm_raw_output` / `vlm_validation_errors` on `Equation` records
     (populated only when a VLM call fails to produce valid JSON, kept
     "so the pipeline can be reprocessed/audited later").
     -> MOVED to the debug artifact instead of the production Chapter
     JSON; the production record keeps `vlm_analysis_skipped`/
     `educational_intent`/`block_type` (all already-SAFE structural
     fields, per M3.1 §2.4) so Phase 2 still knows a VLM call was
     attempted and failed, without the model's possibly-source-echoing
     raw text ever reaching disk in the production document.

Design constraints this module honors (per the Milestone 3.2 task):
  - Deterministic: every function here is a pure function of its input;
    no randomness, no I/O, no VLM calls.
  - Backwards compatible where practical: every field this module
    removes was already NOT part of the frozen Pydantic schema contract
    (schemas/chapter_schema.py's `Equation`/`EducationalObject` are both
    `extra="allow"` — see M3.1 §3.2) — no `ChapterJSON` schema class
    changes are required, and no id/urn/confidence/provenance field is
    ever touched. See MIGRATIONS.md for the compatibility note and the
    accompanying SCHEMA_VERSION bump (these are still a MEANING change
    for any consumer that *was* reading the removed fields, hence MAJOR,
    not silent).
  - Does not redesign the compiler: recognizers, Stage A-E, and the VLM
    two-net (paraphrase + `_enforce_word_cap`) design are untouched.
    This module only runs as a serialization-time gate, downstream of
    everything Stage D/E already decided.

Callers (pipeline.py) run these functions ONCE, after Stage E validation
and Knowledge-Graph-readiness enrichment have both already read whatever
they needed from the raw fields (Stage E's `_is_bare_arithmetic`-style
checks in modules/stage_e_validation.py read `reusable_procedure`'s
*content*, not just its presence, to decide whether an object should be
dropped) — sanitizing any earlier would silently break that filtering.
See pipeline.py's own call-site comment for the exact ordering guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import config

# --------------------------------------------------------------------------
# Architectural decision (see module docstring, item 2): whether
# `programming_syntax` Educational Objects built by the DETERMINISTIC
# recognizers keep their full verbatim `reusable_syntax` code/pseudocode
# text, or have it replaced with structural metadata like every other
# HIGH-risk field in this module.
#
# Centralized in config.py (see config.PRESERVE_CODE_SNIPPETS_VERBATIM's own
# docstring for the full reasoning) alongside every other pipeline knob,
# rather than a module-local constant -- this module just reads it.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Step-marker classification (reusable_procedure / procedure_steps ->
# structural metadata). Mirrors the marker shapes
# modules/recognizers/procedure_recognizers.py's own `_STEP_RE` /
# `_ALGO_KEYWORDS_RE` / `_JOURNAL_KEYWORDS_RE` already look for, but only
# ever reports WHICH SHAPE a line's marker had, never the line's own text.
# --------------------------------------------------------------------------
_STEP_N_RE = re.compile(r"^\s*step\s*\d+\b", re.I)
_NUMBERED_RE = re.compile(r"^\s*[0-9]+[.)]")
_FIRST_RE = re.compile(r"^\s*first(?:ly)?\b", re.I)
_THEN_RE = re.compile(r"^\s*then\b", re.I)
_NEXT_RE = re.compile(r"^\s*next\b", re.I)
_FINALLY_RE = re.compile(r"^\s*finally\b", re.I)
_ALGO_KEYWORDS_RE = re.compile(r"\b(input|output|repeat|while|if\s+.+\s+then|algorithm|pseudocode)\b", re.I)
_JOURNAL_KEYWORDS_RE = re.compile(r"\b(dr\.?|cr\.?|debit|credit|journal entry|ledger)\b", re.I)


def _step_marker_type(step_text: str) -> str:
    """Classifies ONE step's leading-marker shape without retaining any
    of its prose. Order matters (first match wins) — mirrors the
    intent-order a human skimming these markers would use."""
    s = step_text.strip()
    if _STEP_N_RE.match(s):
        return "step_n"
    if _NUMBERED_RE.match(s):
        return "numbered"
    if _FIRST_RE.match(s):
        return "first"
    if _THEN_RE.match(s):
        return "then"
    if _NEXT_RE.match(s):
        return "next"
    if _FINALLY_RE.match(s):
        return "finally"
    if _JOURNAL_KEYWORDS_RE.search(s):
        return "journal_keyword"
    if _ALGO_KEYWORDS_RE.search(s):
        return "algo_keyword"
    return "other"


def _procedure_structural_metadata(procedure_steps: List[str]) -> Dict[str, Any]:
    """Turns a list of raw procedure-step lines into copyright-safe
    structural metadata: how many steps there were and what shape each
    step's own marker took (e.g. "Step 1:" vs "1)" vs "First,") — never
    the step's own words."""
    steps = [s for s in (procedure_steps or []) if isinstance(s, str) and s.strip()]
    return {
        "procedure_step_count": len(steps),
        "procedure_step_marker_types": [_step_marker_type(s) for s in steps],
    }


def _code_structural_metadata(code_text: str) -> Dict[str, Any]:
    """Turns a raw code/pseudocode snippet into copyright-safe structural
    metadata: how many non-blank lines it had and whether it carried any
    content at all — never the code's own tokens/text."""
    lines = [l for l in (code_text or "").splitlines() if l.strip()]
    return {
        "code_line_count": len(lines),
        "has_code_content": bool(lines),
    }


# --------------------------------------------------------------------------
# Debug-entry containers. These carry exactly what was stripped out of the
# production record, keyed by that record's own canonical `id` (or, if a
# record has no id yet, its list position) so a debug artifact consumer
# can correlate a debug entry back to the production object it came from
# without the production object itself ever pointing at the debug data.
# --------------------------------------------------------------------------
@dataclass
class SanitizeReport:
    """Aggregate result of sanitizing one list of records (equations, or
    educational_objects). `sanitized` is the list to serialize into the
    production Chapter JSON; `debug_entries` is what should instead be
    written to the extraction_debug/ artifact (see
    extraction_debug/persistence.py) — never both."""
    sanitized: List[Dict[str, Any]] = field(default_factory=list)
    debug_entries: List[Dict[str, Any]] = field(default_factory=list)
    fields_removed_count: int = 0


def _record_key(record: Dict[str, Any], fallback_index: int) -> str:
    rid = record.get("id")
    return str(rid) if rid else f"_index_{fallback_index}"


def sanitize_equations(equations: List[Dict[str, Any]]) -> SanitizeReport:
    """Implements M3.1 §2.1 finding 3 (`raw_text`) and the MEDIUM finding
    `vlm_raw_output`/`vlm_validation_errors` (explicitly called out by the
    Milestone 3.2 task's own "keep debugging information in debug/
    extraction artifacts rather than production JSON" requirement).

    Every other field on an Equation record (`latex`, `spoken_form`,
    `variables`, `semantic_meaning`, `confidence`, `block_type`,
    `educational_intent`, `vlm_analysis_skipped`, `skip_reason`, plus
    every canonical id/urn/provenance field) is SAFE per M3.1 §2.4/§2.3
    and passes through unchanged."""
    report = SanitizeReport()
    for idx, eq in enumerate(equations or []):
        clean = dict(eq)
        key = _record_key(clean, idx)
        debug_payload: Dict[str, Any] = {}

        raw_text = clean.pop("raw_text", None)
        if raw_text:
            debug_payload["raw_text"] = raw_text
            report.fields_removed_count += 1
        # Structural hint replaces the removed prose: Phase 2 can still
        # tell "this equation region had some source-text hint available"
        # apart from "there was truly nothing here" without ever reading
        # the hint's own words.
        clean["has_raw_text_hint"] = bool(raw_text)

        vlm_raw_output = clean.pop("vlm_raw_output", None)
        if vlm_raw_output:
            debug_payload["vlm_raw_output"] = vlm_raw_output
            report.fields_removed_count += 1

        vlm_validation_errors = clean.pop("vlm_validation_errors", None)
        if vlm_validation_errors:
            debug_payload["vlm_validation_errors"] = vlm_validation_errors
            report.fields_removed_count += 1

        report.sanitized.append(clean)
        if debug_payload:
            report.debug_entries.append({
                "record_type": "equation",
                "record_key": key,
                **debug_payload,
            })
    return report


def sanitize_educational_objects(objects: List[Dict[str, Any]]) -> SanitizeReport:
    """Implements M3.1 §2.1 findings 1 (`reusable_procedure`/
    `procedure_steps`) and 2 (`reusable_syntax`).

    Only touches objects whose `source` is `"deterministic"` (i.e. built
    by a Recognizer's own `recognize()`, not its `vlm_fallback()`) —
    VLM-fallback-sourced `reusable_procedure` text already went through
    `semantic_processor.process_equation_semantics()`'s paraphrase
    instruction + `_enforce_word_cap()` two-net design (see
    modules/recognizers/base.py's `FormulaFamilyRecognizer.vlm_fallback`)
    and is already LOW-risk per M3.1 §2.3 — re-stripping it here would
    throw away a legitimate, already-safe paraphrase for no reason.
    `source` defaults to `"deterministic"` for any object missing the
    field (the RecognitionResult dataclass's own default), so an object
    with no explicit `source` is treated the same conservative way."""
    report = SanitizeReport()
    for idx, obj in enumerate(objects or []):
        clean = dict(obj)
        key = _record_key(clean, idx)
        is_deterministic = clean.get("source", "deterministic") == "deterministic"
        educational_object_type = clean.get("educational_object_type")
        debug_payload: Dict[str, Any] = {}

        if is_deterministic and educational_object_type == "formula_or_procedure" and (
                "reusable_procedure" in clean or "procedure_steps" in clean):
            reusable_procedure = clean.pop("reusable_procedure", None)
            procedure_steps = clean.pop("procedure_steps", None)
            if reusable_procedure:
                debug_payload["reusable_procedure"] = reusable_procedure
                report.fields_removed_count += 1
            if procedure_steps:
                debug_payload["procedure_steps"] = procedure_steps
                report.fields_removed_count += 1
            clean.update(_procedure_structural_metadata(procedure_steps or []))

        if is_deterministic and educational_object_type == "programming_syntax" and "reusable_syntax" in clean:
            if config.PRESERVE_CODE_SNIPPETS_VERBATIM:
                # Documented product/legal decision (see module docstring
                # and PRESERVE_CODE_SNIPPETS_VERBATIM above) — kept as-is.
                pass
            else:
                reusable_syntax = clean.pop("reusable_syntax", None)
                if reusable_syntax:
                    debug_payload["reusable_syntax"] = reusable_syntax
                    report.fields_removed_count += 1
                clean.update(_code_structural_metadata(reusable_syntax or ""))

        report.sanitized.append(clean)
        if debug_payload:
            report.debug_entries.append({
                "record_type": "educational_object",
                "record_key": key,
                "educational_object_type": educational_object_type,
                **debug_payload,
            })
    return report


def sanitize_chapter_records(
    equations: List[Dict[str, Any]],
    educational_objects: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Convenience entry point for pipeline.py: sanitizes both lists in
    one call and returns
    (clean_equations, clean_educational_objects, debug_entries) — the
    shape pipeline.py's single call site actually wants, so it doesn't
    need to know about `SanitizeReport` itself."""
    eq_report = sanitize_equations(equations)
    obj_report = sanitize_educational_objects(educational_objects)
    return eq_report.sanitized, obj_report.sanitized, eq_report.debug_entries + obj_report.debug_entries

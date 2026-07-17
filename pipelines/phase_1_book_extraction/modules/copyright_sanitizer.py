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

--------------------------------------------------------------------------
Milestone 3.3 additions (MEDIUM/LOW findings deferred by M3.2, see
MILESTONE_3_2_SUMMARY.md §6 "Recommendations deferred to future
milestones"):

  5. `semantic_description` on Activity/Box/Warning/Note/Example blocks
     (`pipeline.py`'s `_finalize_blocks()`). Previously populated with
     `_enforce_word_cap(body[:200])` — a raw character-slice of the
     block's own source text, still copied prose even after the word
     cap trims it (the cap shortens copied text, it does not make it
     non-copied). Figures/Tables/Equations never had this problem: their
     `semantic_description`/`semantic_meaning` stay `""` at Phase 1
     pending real VLM paraphrase in a later phase.
     -> `sanitize_content_blocks()` REMOVES the raw description from the
     production record (same "not silently lost, moved to debug" pattern
     as every other field here) and replaces it with `""` plus a boolean
     `has_semantic_description_hint` — i.e. brought in line with how
     Figures/Tables/Equations already behave, per M3.1's own recommended
     action for this finding.

  6. `rules` on `accounting_format` Educational Objects specifically of
     `format_type == "accounting_rule"` (`AccountingRuleRecognizer` —
     modules/recognizers/accounting_recognizers.py). Each entry is the
     *entire raw line* that matched the golden-rule regex, not just the
     matched phrase, and the list is unbounded.
     -> REPLACED WITH STRUCTURAL METADATA: `matched_rule_count` +
     `matched_rule_types` (which golden-rule *category* each line
     matched — "debit_receiver"/"credit_giver"/"debit_comes_in"/
     "credit_goes_out"/"debit_expenses_losses"/"credit_incomes_gains"/
     "other" — never the line's own words), mirroring the
     `procedure_step_marker_types` treatment finding 1 already got.

  7. `caption`/`title` on Figure/Diagram/Table records (`pipeline.py`,
     sourced from `modules/layout_detector.py`'s `_nearby_caption()` and
     the table caption-only fallback — both raw PDF/OCR line text with
     no upstream length limit).
     -> `sanitize_visual_captions()` applies a defensive word cap
     (`config.MAX_CAPTION_WORDS`) via the same `_enforce_word_cap`-style
     truncation Figures/Tables/Equations' AI-paraphrased fields already
     use — this is a defensive ceiling on a short factual label, not a
     paraphrase step, so (unlike findings 1-5 above) the field is
     truncated in place rather than replaced with metadata. The
     untruncated original is moved to the debug artifact, and ONLY for
     records that actually exceeded the cap (the common case — a normal
     "Fig 3.2: ..." caption — produces no debug entry at all).

Deliberately NOT done here (left open, see this module's own limits):
  - `evidence_span` is never populated anywhere in this checkout (M3.1
    §2.1 LOW finding) — nothing to sanitize yet; flagged for whoever
    wires it up to add it to `_BANNED_PROSE_FIELD_NAMES` or
    `_ALLOWED_PROSE_FIELDS` at that time, not before.
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


# --------------------------------------------------------------------------
# Accounting golden-rule classification (`rules` -> structural metadata).
# Mirrors the six alternatives in
# modules/recognizers/accounting_recognizers.py's own `_GOLDEN_RULE_RE`,
# but only ever reports WHICH RULE CATEGORY a matched line belongs to,
# never the line's own text.
# --------------------------------------------------------------------------
_DEBIT_RECEIVER_RE = re.compile(r"\bdebit the receiver\b", re.I)
_CREDIT_GIVER_RE = re.compile(r"\bcredit the giver\b", re.I)
_DEBIT_COMES_IN_RE = re.compile(r"\bdebit what comes in\b", re.I)
_CREDIT_GOES_OUT_RE = re.compile(r"\bcredit what goes out\b", re.I)
_DEBIT_EXPENSES_RE = re.compile(r"\bdebit all expenses(?: and losses)?\b", re.I)
_CREDIT_INCOMES_RE = re.compile(r"\bcredit all incomes?(?: and gains)?\b", re.I)


def _accounting_rule_type(rule_text: str) -> str:
    """Classifies ONE matched golden-rule line's category without
    retaining any of its prose. Order matters (first match wins), same
    convention as `_step_marker_type` above."""
    s = rule_text.strip()
    if _DEBIT_RECEIVER_RE.search(s):
        return "debit_receiver"
    if _CREDIT_GIVER_RE.search(s):
        return "credit_giver"
    if _DEBIT_COMES_IN_RE.search(s):
        return "debit_comes_in"
    if _CREDIT_GOES_OUT_RE.search(s):
        return "credit_goes_out"
    if _DEBIT_EXPENSES_RE.search(s):
        return "debit_expenses_losses"
    if _CREDIT_INCOMES_RE.search(s):
        return "credit_incomes_gains"
    return "other"


def _accounting_rules_structural_metadata(rules: List[str]) -> Dict[str, Any]:
    """Turns a list of raw golden-rule lines into copyright-safe
    structural metadata: how many rule lines matched and which category
    each one belongs to — never the line's own words."""
    lines = [r for r in (rules or []) if isinstance(r, str) and r.strip()]
    return {
        "matched_rule_count": len(lines),
        "matched_rule_types": [_accounting_rule_type(r) for r in lines],
    }


def _enforce_word_cap_local(text: str, max_words: int) -> str:
    """Same "split on whitespace, keep the first N words, rejoin with a
    single space" logic as `semantic_processor._enforce_word_cap` —
    reimplemented here (not imported) so this module keeps its own
    "no I/O, no external dependency" guarantee (see module docstring)
    intact; semantic_processor.py unconditionally imports fitz/PIL at
    module load time for its VLM page-rendering functions, which this
    caption-length check has no need of."""
    words = (text or "").split()
    return " ".join(words[:max_words])


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
    `procedure_steps`), 2 (`reusable_syntax`), and Milestone 3.3 finding 6
    (`rules` on `accounting_format`/`accounting_rule` objects).

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

        if is_deterministic and educational_object_type == "accounting_format" and (
                clean.get("format_type") == "accounting_rule") and "rules" in clean:
            rules = clean.pop("rules", None)
            if rules:
                debug_payload["rules"] = rules
                report.fields_removed_count += 1
            clean.update(_accounting_rules_structural_metadata(rules or []))

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


def sanitize_content_blocks(blocks: List[Dict[str, Any]], record_type: str = "content_block") -> SanitizeReport:
    """Milestone 3.3, finding 5: Activity/Box/Warning/Note/Example records
    (`pipeline.py`'s `_finalize_blocks()`), whose `semantic_description`
    is a raw, word-capped-but-still-copied slice of the block's own
    source text (`_enforce_word_cap(body[:200])`), not an AI paraphrase.

    Brings these five block kinds in line with how Figures/Tables/
    Equations already behave at Phase 1 (per M3.1's recommended action:
    "route through the same paraphrase+cap path ... instead of raw-
    truncation") — since no real paraphrase step exists for these blocks
    yet, the safe interim behavior is the same one Figures/Tables/
    Equations already use: leave the field empty rather than populate it
    with copied prose, and record only that a description candidate
    existed (`has_semantic_description_hint`) so a future paraphrase
    step (or Phase 2) knows there was something to describe.

    `record_type` is stamped onto each debug entry so a debug-artifact
    consumer can tell an activity's stripped description from a note's
    (pipeline.py passes "activity"/"box"/"warning"/"note"/"example")."""
    report = SanitizeReport()
    for idx, block in enumerate(blocks or []):
        clean = dict(block)
        key = _record_key(clean, idx)
        debug_payload: Dict[str, Any] = {}

        description = clean.pop("semantic_description", None)
        if isinstance(description, str) and description.strip():
            debug_payload["semantic_description"] = description
            report.fields_removed_count += 1
        clean["semantic_description"] = ""
        clean["has_semantic_description_hint"] = bool(description and description.strip())

        report.sanitized.append(clean)
        if debug_payload:
            report.debug_entries.append({
                "record_type": record_type,
                "record_key": key,
                **debug_payload,
            })
    return report


def sanitize_visual_captions(records: List[Dict[str, Any]], record_type: str) -> SanitizeReport:
    """Milestone 3.3, finding 7: Figure/Diagram/Table `caption`/`title`
    fields, sourced directly from nearby PDF/OCR line text
    (`modules/layout_detector.py`'s `_nearby_caption()` and the table
    caption-only fallback) with no upstream length limit.

    Unlike findings 1/2/3/5/6 above, a caption is a legitimate short
    factual label (a figure/table number and title) that Phase 2 needs
    verbatim to cross-reference against the source — so this does NOT
    reduce it to structural metadata. It applies the same style of
    defensive word cap every AI-paraphrased field already gets
    (`semantic_processor._enforce_word_cap`'s own "split on whitespace,
    keep the first N words" logic, reimplemented locally below rather
    than imported — semantic_processor pulls in fitz/PIL for page
    rendering, which this otherwise-pure, no-I/O, no-external-dependency
    module has no other reason to need), capped here at
    `config.MAX_CAPTION_WORDS` instead of `MAX_SEMANTIC_DESCRIPTION_WORDS`,
    and truncates in place. The untruncated original is moved to the
    debug artifact, and only for records that actually exceeded the cap —
    an ordinary short caption produces no debug entry and is returned
    completely unchanged.

    `record_type` is stamped onto each debug entry the same way
    `sanitize_content_blocks` does (pipeline.py passes
    "figure"/"diagram"/"table")."""
    report = SanitizeReport()
    for idx, record in enumerate(records or []):
        clean = dict(record)
        key = _record_key(clean, idx)
        debug_payload: Dict[str, Any] = {}

        for field in ("caption", "title"):
            value = clean.get(field)
            if isinstance(value, str) and value.strip():
                capped = _enforce_word_cap_local(value, config.MAX_CAPTION_WORDS)
                if capped != value:
                    debug_payload[field] = value
                    report.fields_removed_count += 1
                    clean[field] = capped

        report.sanitized.append(clean)
        if debug_payload:
            report.debug_entries.append({
                "record_type": record_type,
                "record_key": key,
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

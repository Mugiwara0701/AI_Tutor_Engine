"""
modules/heading_canonicalization/enums.py — M4.3A: shared closed/open
vocabularies for the heading canonicalization framework.

Mirrors modules/heading_recognizers/enums.py's own convention in this
project: str-backed Enums, JSON-serializable via `.value`, directly
comparable against the equivalent string. Nothing in this module
decides HOW a heading is canonicalized (that is a concrete
canonicalizer's job, in a later M4.3 milestone) — these are the
shared vocabularies the framework's models, pipeline, and validation
contracts need to exist at all.
"""
from __future__ import annotations

from enum import Enum


class CanonicalHeadingType(str, Enum):
    """The structural role a heading plays once canonicalized (its
    place in the document outline), independent of which recognizer
    or numbering system produced it. Deliberately NOT a closed set in
    spirit — like HeadingClassification, new members may be added
    later as additive changes — but M4.3A only defines the
    placeholders a `CanonicalHeading` may carry; no canonicalizer in
    this milestone actually assigns one of these (see this package's
    `README.md`, "Out of scope")."""

    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    SUBSUBSECTION = "subsubsection"
    #: A structural keyword heading with no numeric position of its
    #: own (e.g. "Summary", "Exercises") — mirrors
    #: HeadingClassification.SECTION_KEYWORD's role on the recognition
    #: side, carried forward as a canonical *type* rather than a
    #: recognition pattern.
    KEYWORD_SECTION = "keyword_section"
    UNSPECIFIED = "unspecified"


class NumberingSystem(str, Enum):
    """Which numeral/marker system a heading's original numbering was
    written in. A later M4.3 milestone (M4.3B: Number System
    Canonicalization) is what actually determines this value for a
    given heading and converts it to a normalized form; M4.3A only
    defines the vocabulary and the placeholder field that will carry
    it (`CanonicalHeading.numbering_system`)."""

    ARABIC = "arabic"
    ROMAN = "roman"
    DEVANAGARI = "devanagari"
    ALPHABETIC = "alphabetic"
    HIERARCHICAL = "hierarchical"
    #: Heading has a canonical type but no numbering marker at all
    #: (e.g. a bare keyword heading) — distinct from UNKNOWN, which
    #: means "not yet determined" rather than "determined to be none".
    NONE = "none"
    UNKNOWN = "unknown"


class ValidationStatus(str, Enum):
    """Coarse-grained validation state a `CanonicalHeading` carries.
    PENDING is the only status the M4.3A framework itself ever
    assigns (see `models.CanonicalHeading`'s default) — SUCCESS /
    WARNING / ERROR are assigned by a structural validator
    canonicalizer, which is out of scope for this milestone (see
    "Out of Scope" in the M4.3A spec: "sequence validation, duplicate
    detection, hierarchy validation")."""

    PENDING = "pending"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ValidationSeverity(str, Enum):
    """Severity of a single `ValidationDiagnostic` entry. Closed set:
    validation.py's `ValidationResult.status` derivation has one rule
    per member, so adding a severity is a framework change."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CanonicalizerState(str, Enum):
    """Lifecycle state a `CanonicalizerRegistry` tracks per registered
    canonicalizer. Mirrors `heading_recognizers.enums.RecognizerState`
    exactly, applied to canonicalizers instead of recognizers."""

    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


class CanonicalizationOutcome(str, Enum):
    """The result shape of one canonicalizer's attempt against one
    `CanonicalHeading` within a pipeline run. Mirrors
    `heading_recognizers.enums.RecognitionOutcome`'s four-way split,
    adapted to canonicalization semantics:

    APPLIED — canonicalize() returned an updated CanonicalHeading.
    UNCHANGED — canonicalize() returned None (this canonicalizer's
        transformation does not apply to this heading — the
        canonicalization analogue of RecognitionOutcome.NO_MATCH).
    FAILED — canonicalize() raised and safe_canonicalize() caught it.
    SKIPPED — the pipeline never called canonicalize() at all
        (canonicalizer disabled, or supports() returned False).
    """

    APPLIED = "applied"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    SKIPPED = "skipped"


__all__ = [
    "CanonicalHeadingType",
    "NumberingSystem",
    "ValidationStatus",
    "ValidationSeverity",
    "CanonicalizerState",
    "CanonicalizationOutcome",
]

"""
modules/semantic_interpretation_engine/models.py — M5.2D: the core
immutable, versioned, serializable semantic data models.

Design philosophy:
- Every model is a frozen dataclass (immutable after construction).
- Every model exposes `to_dict()` for deterministic JSON serialization.
- No model subclasses or modifies any M5.1–M5.2C model.  They wrap
  or reference M5.2C outputs by value (e.g. storing object_key strings
  rather than holding live references to StructuralObject instances).
- SemanticEnrichmentResult is the top-level output of the engine; it
  wraps M5.2C's StructuralAnalysisResult by value (via stored keys /
  plain dicts) so M5.2C types do not appear in M5.2D's public surface.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from modules.semantic_interpretation_engine.enums import (
    CompatibilitySeverity,
    ConfidenceLevel,
    EnrichmentOutcome,
    InstructionalContext,
    LearningIntent,
    PedagogicalRole,
    SemanticRole,
)
from modules.semantic_interpretation_engine.exceptions import (
    SemanticValidationError,
)

__all__ = [
    # Confidence
    "ConfidenceScore",
    "ConfidenceEvidence",
    "ConfidenceBreakdown",
    # Semantic interpretation
    "SemanticInterpretation",
    "SemanticObject",
    # Compatibility
    "CompatibilityResult",
    # Semantic anchor
    "SemanticAnchor",
    # Top-level result
    "SemanticEnrichmentResult",
    # Version constant
    "DEFAULT_SEMANTIC_VERSION",
]

DEFAULT_SEMANTIC_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return an immutable copy of *value*, or an empty dict."""
    if value is None:
        return {}
    return dict(value)


def _frozen_tuple(value: Optional[Tuple]) -> Tuple:
    if value is None:
        return ()
    return tuple(value)


# ---------------------------------------------------------------------------
# Confidence models (Deliverable #1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfidenceEvidence:
    """
    A single piece of evidence contributing to a ConfidenceScore.

    Attributes:
        label:   Short human-readable label (e.g. "required_roles_present").
        weight:  Contribution weight in [0.0, 1.0].
        passed:  Whether this evidence item was satisfied.
        detail:  Optional explanatory note.
    """

    label: str
    weight: float
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise SemanticValidationError("ConfidenceEvidence.label must not be empty.")
        if not 0.0 <= self.weight <= 1.0:
            raise SemanticValidationError(
                f"ConfidenceEvidence.weight must be in [0.0, 1.0]; got {self.weight!r}."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "weight": self.weight,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ConfidenceScore:
    """
    A single confidence measurement in [0.0, 1.0] with a corresponding
    ordinal band and the evidence items that produced it.

    Attributes:
        value:   Raw score in [0.0, 1.0].
        level:   Ordinal band (HIGH / MEDIUM / LOW / NONE).
        evidence: Evidence items that determined the score.
    """

    value: float
    level: ConfidenceLevel
    evidence: Tuple[ConfidenceEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise SemanticValidationError(
                f"ConfidenceScore.value must be in [0.0, 1.0]; got {self.value!r}."
            )
        object.__setattr__(self, "evidence", _frozen_tuple(self.evidence))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "level": self.level.value,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """
    Per-dimension confidence scores for a SemanticEnrichmentResult.

    Attributes:
        structural:  Confidence in the structural interpretation
                     (wrapping M5.2C's StructuralAnalysisResult).
        semantic:    Confidence in the semantic role assignment.
        enrichment:  Overall enrichment quality score.
    """

    structural: ConfidenceScore
    semantic: ConfidenceScore
    enrichment: ConfidenceScore

    def to_dict(self) -> Dict[str, Any]:
        return {
            "structural": self.structural.to_dict(),
            "semantic": self.semantic.to_dict(),
            "enrichment": self.enrichment.to_dict(),
        }


# ---------------------------------------------------------------------------
# Semantic interpretation models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticInterpretation:
    """
    The semantic meaning assigned to a single structural component role.

    Attributes:
        structural_role:     The role string from M5.2C's StructuralPattern
                             (e.g. "definition", "steps", "observation").
        semantic_role:       The SemanticRole this structural role maps to.
        pedagogical_role:    The broad PedagogicalRole of this component.
        learning_intent:     The LearningIntent this component serves.
        instructional_context:
                             Where in an instructional sequence this
                             component typically sits.
        confidence:          Per-interpretation confidence score.
        notes:               Optional free-text annotation (deterministic;
                             set by resolver, not by LLM).
    """

    structural_role: str
    semantic_role: SemanticRole
    pedagogical_role: PedagogicalRole
    learning_intent: LearningIntent
    instructional_context: InstructionalContext
    confidence: ConfidenceScore
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.structural_role:
            raise SemanticValidationError(
                "SemanticInterpretation.structural_role must not be empty."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "structural_role": self.structural_role,
            "semantic_role": self.semantic_role.value,
            "pedagogical_role": self.pedagogical_role.value,
            "learning_intent": self.learning_intent.value,
            "instructional_context": self.instructional_context.value,
            "confidence": self.confidence.to_dict(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SemanticObject:
    """
    The fully enriched semantic representation of an educational object.

    Wraps M5.2C's StructuralObject (by key) and adds semantic layer.

    Attributes:
        object_key:          Matches StructuralObject.object_key from M5.2C.
        object_type_key:     Matches StructuralObject.object_type_key from M5.2C.
        pattern_key:         The resolved StructuralPattern key (may be None).
        interpretations:     Per-role SemanticInterpretation entries, ordered
                             deterministically by structural_role.
        pedagogical_role:    The dominant PedagogicalRole for the whole object.
        learning_intent:     The dominant LearningIntent for the whole object.
        instructional_context:
                             The dominant InstructionalContext.
        metadata:            Arbitrary pass-through metadata (frozen mapping).
        version:             Semantic model version.
    """

    object_key: str
    object_type_key: str
    pattern_key: Optional[str]
    interpretations: Tuple[SemanticInterpretation, ...] = field(default_factory=tuple)
    pedagogical_role: PedagogicalRole = PedagogicalRole.UNKNOWN
    learning_intent: LearningIntent = LearningIntent.UNKNOWN
    instructional_context: InstructionalContext = InstructionalContext.UNKNOWN
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_SEMANTIC_VERSION

    def __post_init__(self) -> None:
        if not self.object_key:
            raise SemanticValidationError("SemanticObject.object_key must not be empty.")
        # object_type_key is optional (may be absent when no StructuralObject is provided)
        object.__setattr__(self, "interpretations", _frozen_tuple(self.interpretations))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_key": self.object_key,
            "object_type_key": self.object_type_key,
            "pattern_key": self.pattern_key,
            "interpretations": [i.to_dict() for i in self.interpretations],
            "pedagogical_role": self.pedagogical_role.value,
            "learning_intent": self.learning_intent.value,
            "instructional_context": self.instructional_context.value,
            "metadata": dict(self.metadata),
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Compatibility result (Deliverable #2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompatibilityResult:
    """
    Rich explanation of a compatibility check, wrapping the boolean
    outcome produced by M5.2C's CompatibilityValidator with human-
    readable diagnostic detail.

    M5.2C's CompatibilityValidator is NOT modified; this model wraps
    its output in M5.2D's CompatibilityInterpreter.

    Attributes:
        compatible:           True if the object type is compatible.
        severity:             OK / WARNING / ERROR.
        reason:               Human-readable explanation.
        affected_components:  Component keys or role names implicated.
        suggested_resolution: Actionable suggestion for the caller.
        object_type_key:      The EducationalObjectType.key that was checked.
        object_type_version:  The version of that type.
    """

    compatible: bool
    severity: CompatibilitySeverity
    reason: str
    affected_components: Tuple[str, ...] = field(default_factory=tuple)
    suggested_resolution: str = ""
    object_type_key: str = ""
    object_type_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "affected_components", _frozen_tuple(self.affected_components))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compatible": self.compatible,
            "severity": self.severity.value,
            "reason": self.reason,
            "affected_components": list(self.affected_components),
            "suggested_resolution": self.suggested_resolution,
            "object_type_key": self.object_type_key,
            "object_type_version": self.object_type_version,
        }


# ---------------------------------------------------------------------------
# Semantic anchor (Deliverable #5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticAnchor:
    """
    A stable, unique semantic identifier for an educational object.
    SemanticAnchors are the primary inputs M5.2E (Relationship Discovery)
    will consume.

    Attributes:
        anchor_id:        Globally unique identifier (UUID4 string, assigned
                          deterministically from object_key + semantic_role).
        semantic_role:    The dominant SemanticRole of the anchored object.
        object_reference: The object_key this anchor points to.
        confidence:       Confidence in the anchor assignment.
        pattern_key:      Pattern key used during interpretation (may be None).
        version:          Anchor schema version.
    """

    anchor_id: str
    semantic_role: SemanticRole
    object_reference: str
    confidence: ConfidenceScore
    pattern_key: Optional[str] = None
    version: str = DEFAULT_SEMANTIC_VERSION

    def __post_init__(self) -> None:
        if not self.anchor_id:
            raise SemanticValidationError("SemanticAnchor.anchor_id must not be empty.")
        if not self.object_reference:
            raise SemanticValidationError("SemanticAnchor.object_reference must not be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "semantic_role": self.semantic_role.value,
            "object_reference": self.object_reference,
            "confidence": self.confidence.to_dict(),
            "pattern_key": self.pattern_key,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Top-level enrichment result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticEnrichmentResult:
    """
    The top-level output of the SemanticEnrichmentEngine.

    Wraps M5.2C's StructuralAnalysisResult (stored as a plain dict
    snapshot so M5.2C types do not leak into M5.2D's public API) and
    adds the full semantic layer.

    Attributes:
        object_key:              Matches StructuralObject.object_key.
        outcome:                 Overall enrichment outcome.
        semantic_object:         The enriched SemanticObject (present unless
                                 outcome is UNRECOGNIZED/ERROR).
        confidence:              Per-dimension ConfidenceBreakdown.
        compatibility_result:    Rich compatibility report (Deliverable #2).
        anchor:                  SemanticAnchor for M5.2E (Deliverable #5).
        structural_snapshot:     Frozen dict copy of
                                 StructuralAnalysisResult.to_dict() — the
                                 M5.2C result this enrichment is based on.
        diagnostics:             Ordered tuple of diagnostic strings.
        version:                 Result schema version.
    """

    object_key: str
    outcome: EnrichmentOutcome
    semantic_object: Optional[SemanticObject]
    confidence: ConfidenceBreakdown
    compatibility_result: CompatibilityResult
    anchor: Optional[SemanticAnchor]
    structural_snapshot: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Tuple[str, ...] = field(default_factory=tuple)
    version: str = DEFAULT_SEMANTIC_VERSION

    def __post_init__(self) -> None:
        if not self.object_key:
            raise SemanticValidationError("SemanticEnrichmentResult.object_key must not be empty.")
        object.__setattr__(self, "structural_snapshot", _frozen_mapping(self.structural_snapshot))
        object.__setattr__(self, "diagnostics", _frozen_tuple(self.diagnostics))

    def is_complete(self) -> bool:
        return self.outcome == EnrichmentOutcome.COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_key": self.object_key,
            "outcome": self.outcome.value,
            "semantic_object": self.semantic_object.to_dict() if self.semantic_object else None,
            "confidence": self.confidence.to_dict(),
            "compatibility_result": self.compatibility_result.to_dict(),
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "structural_snapshot": dict(self.structural_snapshot),
            "diagnostics": list(self.diagnostics),
            "version": self.version,
        }

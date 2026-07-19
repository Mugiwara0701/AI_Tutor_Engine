"""
modules/semantic_interpretation_engine/validation.py — M5.2D:
validation contracts for semantic models.

Reuses M5.1's ValidationResult / ValidationDiagnostic / DiagnosticSeverity
exactly as M5.2C did — no duplication of those contracts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.semantic_interpretation_engine.enums import EnrichmentOutcome

if TYPE_CHECKING:
    from modules.semantic_interpretation_engine.models import SemanticEnrichmentResult

__all__ = [
    "validate_semantic_enrichment_result",
    "validate_anchor_uniqueness",
    "validate_confidence_consistency",
]


def validate_semantic_enrichment_result(result: "SemanticEnrichmentResult") -> ValidationResult:
    """
    Validate the internal consistency of a SemanticEnrichmentResult.

    Checks:
    - object_key is non-empty.
    - If outcome is COMPLETE, semantic_object and anchor must be present.
    - If outcome is ERROR/UNRECOGNIZED, diagnostics should be non-empty.
    - Confidence scores are in [0.0, 1.0].
    - semantic_object.object_key matches result.object_key.
    """
    diagnostics: List[ValidationDiagnostic] = []

    if not result.object_key:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="SIE001",
            message="SemanticEnrichmentResult.object_key must not be empty.",
            processor_name="validate_semantic_enrichment_result",
        ))

    if result.outcome == EnrichmentOutcome.COMPLETE:
        if result.semantic_object is None:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="SIE002",
                message=(
                    "SemanticEnrichmentResult.outcome is COMPLETE but "
                    "semantic_object is None."
                ),
                processor_name="validate_semantic_enrichment_result",
            ))
        if result.anchor is None:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="SIE003",
                message=(
                    "SemanticEnrichmentResult.outcome is COMPLETE but "
                    "anchor is None."
                ),
                processor_name="validate_semantic_enrichment_result",
            ))

    if result.outcome in (EnrichmentOutcome.ERROR, EnrichmentOutcome.UNRECOGNIZED):
        if not result.diagnostics:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="SIE004",
                message=(
                    f"SemanticEnrichmentResult.outcome is "
                    f"{result.outcome.value!r} but no diagnostics were recorded."
                ),
                processor_name="validate_semantic_enrichment_result",
            ))

    for dim_name, score in [
        ("structural", result.confidence.structural),
        ("semantic", result.confidence.semantic),
        ("enrichment", result.confidence.enrichment),
    ]:
        if not 0.0 <= score.value <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="SIE005",
                message=(
                    f"ConfidenceScore for {dim_name!r} is out of range "
                    f"[0.0, 1.0]: {score.value!r}."
                ),
                processor_name="validate_semantic_enrichment_result",
            ))

    if (
        result.semantic_object is not None
        and result.semantic_object.object_key != result.object_key
    ):
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="SIE006",
            message=(
                f"SemanticObject.object_key {result.semantic_object.object_key!r} "
                f"does not match SemanticEnrichmentResult.object_key "
                f"{result.object_key!r}."
            ),
            processor_name="validate_semantic_enrichment_result",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_anchor_uniqueness(
    results: "list[SemanticEnrichmentResult]",
) -> ValidationResult:
    """
    Validate that all SemanticAnchors across *results* have unique anchor_ids.
    """
    diagnostics: List[ValidationDiagnostic] = []
    seen_ids: dict = {}

    for result in results:
        if result.anchor is None:
            continue
        aid = result.anchor.anchor_id
        if aid in seen_ids:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="SIE007",
                message=(
                    f"Duplicate anchor_id {aid!r} found in results for "
                    f"object_keys {seen_ids[aid]!r} and {result.object_key!r}."
                ),
                processor_name="validate_anchor_uniqueness",
            ))
        else:
            seen_ids[aid] = result.object_key

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_confidence_consistency(result: "SemanticEnrichmentResult") -> ValidationResult:
    """
    Validate that ConfidenceLevel bands are consistent with score thresholds.
    This is a lightweight cross-check; the ConfidenceEvaluator already
    assigns levels correctly, but this guards against stale/mutated data.
    """
    diagnostics: List[ValidationDiagnostic] = []
    from modules.semantic_interpretation_engine.enums import ConfidenceLevel

    for dim_name, score in [
        ("structural", result.confidence.structural),
        ("semantic", result.confidence.semantic),
        ("enrichment", result.confidence.enrichment),
    ]:
        if score.level == ConfidenceLevel.HIGH and score.value < 0.80:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="SIE008",
                message=(
                    f"{dim_name} confidence level is HIGH but score is "
                    f"{score.value} (< 0.80)."
                ),
                processor_name="validate_confidence_consistency",
            ))
        elif score.level == ConfidenceLevel.MEDIUM and score.value < 0.50:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="SIE009",
                message=(
                    f"{dim_name} confidence level is MEDIUM but score is "
                    f"{score.value} (< 0.50)."
                ),
                processor_name="validate_confidence_consistency",
            ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

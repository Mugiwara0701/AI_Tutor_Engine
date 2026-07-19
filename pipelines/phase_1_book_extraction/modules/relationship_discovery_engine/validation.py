"""
modules/relationship_discovery_engine/validation.py — M5.2E:
top-level validation functions for relationships and graphs.

Reuses M5.1's ValidationResult / ValidationDiagnostic / DiagnosticSeverity
contracts exactly — never duplicates them.
"""
from __future__ import annotations

from typing import List, TYPE_CHECKING

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.relationship_discovery_engine.enums import GraphBuildOutcome
from modules.relationship_discovery_engine.models import (
    RelationshipDiscoveryResult,
    SemanticGraph,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "validate_discovery_result",
    "validate_graph_export_ready",
    "validate_confidence_propagation",
]


def validate_discovery_result(result: RelationshipDiscoveryResult) -> ValidationResult:
    """
    Validate the internal consistency of a RelationshipDiscoveryResult.

    Checks:
    - relationships tuple is present (may be empty for EMPTY outcome).
    - All relationship_ids are non-empty.
    - All source/target anchor_ids are non-empty.
    - Confidence values are in [0.0, 1.0].
    """
    diagnostics: List[ValidationDiagnostic] = []

    for rel in result.relationships:
        if not rel.relationship_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDV001",
                message="SemanticRelationship has empty relationship_id.",
                processor_name="validate_discovery_result",
            ))
        if not rel.source_anchor_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDV002",
                message=f"Relationship {rel.relationship_id!r}: empty source_anchor_id.",
                processor_name="validate_discovery_result",
            ))
        if not rel.target_anchor_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDV003",
                message=f"Relationship {rel.relationship_id!r}: empty target_anchor_id.",
                processor_name="validate_discovery_result",
            ))
        if not 0.0 <= rel.confidence.value <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDV004",
                message=(
                    f"Relationship {rel.relationship_id!r}: confidence "
                    f"{rel.confidence.value!r} out of range [0.0, 1.0]."
                ),
                processor_name="validate_discovery_result",
            ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_graph_export_ready(graph: SemanticGraph) -> ValidationResult:
    """
    Validate that a SemanticGraph is ready for M5.3 export.

    Checks:
    - Outcome is COMPLETE or PARTIAL (not ERROR or EMPTY for export).
    - graph_id is non-empty.
    - At least one node is present.
    - to_dict() does not raise.
    """
    diagnostics: List[ValidationDiagnostic] = []

    if graph.outcome == GraphBuildOutcome.ERROR:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="GEV001",
            message="SemanticGraph outcome is ERROR — not suitable for export.",
            processor_name="validate_graph_export_ready",
        ))

    if graph.outcome == GraphBuildOutcome.EMPTY:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="GEV002",
            message="SemanticGraph is EMPTY — no nodes or edges to export.",
            processor_name="validate_graph_export_ready",
        ))

    if not graph.metadata.graph_id:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="GEV003",
            message="SemanticGraph.metadata.graph_id must not be empty.",
            processor_name="validate_graph_export_ready",
        ))

    if not graph.nodes:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="GEV004",
            message="SemanticGraph has no nodes.",
            processor_name="validate_graph_export_ready",
        ))

    try:
        graph.to_dict()
    except Exception as exc:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="GEV005",
            message=f"SemanticGraph.to_dict() raised: {exc}",
            processor_name="validate_graph_export_ready",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_confidence_propagation(result: RelationshipDiscoveryResult) -> ValidationResult:
    """
    Validate that confidence values were correctly propagated.

    Checks:
    - All RelationshipConfidence values are in [0.0, 1.0].
    - All source/target confidence values are in [0.0, 1.0].
    - Evidence lists are non-empty.
    """
    diagnostics: List[ValidationDiagnostic] = []

    for rel in result.relationships:
        c = rel.confidence
        if not 0.0 <= c.value <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="CPV001",
                message=(
                    f"Relationship {rel.relationship_id!r}: "
                    f"RelationshipConfidence.value {c.value!r} out of range."
                ),
                processor_name="validate_confidence_propagation",
            ))
        if not 0.0 <= c.source_confidence <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="CPV002",
                message=(
                    f"Relationship {rel.relationship_id!r}: "
                    f"source_confidence {c.source_confidence!r} out of range."
                ),
                processor_name="validate_confidence_propagation",
            ))
        if not 0.0 <= c.target_confidence <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="CPV003",
                message=(
                    f"Relationship {rel.relationship_id!r}: "
                    f"target_confidence {c.target_confidence!r} out of range."
                ),
                processor_name="validate_confidence_propagation",
            ))
        if not c.evidence:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="CPV004",
                message=(
                    f"Relationship {rel.relationship_id!r}: "
                    f"RelationshipConfidence has no evidence items."
                ),
                processor_name="validate_confidence_propagation",
            ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

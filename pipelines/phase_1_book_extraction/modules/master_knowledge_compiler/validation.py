"""
modules/master_knowledge_compiler/validation.py — M5.3: validation
functions for the Master Knowledge Compiler.

Reuses M5.1's ValidationResult / ValidationDiagnostic / SUCCESS contracts.
"""
from __future__ import annotations

import json
from typing import List, TYPE_CHECKING

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.master_knowledge_compiler.enums import CompilationOutcome, PackageStatus

if TYPE_CHECKING:
    from modules.master_knowledge_compiler.models import (
        ConceptIndex,
        DependencyMap,
        MasterKnowledgePackage,
        RetrievalIndex,
    )

__all__ = [
    "validate_concept_index",
    "validate_dependency_map",
    "validate_retrieval_index",
    "validate_package",
    "validate_serialization",
]


def validate_concept_index(index: "ConceptIndex") -> ValidationResult:
    """Validate ConceptIndex consistency."""
    diagnostics: List[ValidationDiagnostic] = []

    seen_ids = set()
    for entry in index.entries:
        if not entry.node_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV001",
                message="ConceptEntry has empty node_id.",
                processor_name="validate_concept_index",
            ))
        elif entry.node_id in seen_ids:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV002",
                message=f"Duplicate ConceptEntry node_id {entry.node_id!r}.",
                processor_name="validate_concept_index",
            ))
        else:
            seen_ids.add(entry.node_id)

        if not 0.0 <= entry.confidence <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV003",
                message=f"ConceptEntry {entry.node_id!r}: confidence {entry.confidence} out of [0,1].",
                processor_name="validate_concept_index",
            ))

    if index.statistics.total_concepts != len(index.entries):
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="MKV004",
            message=(
                f"ConceptIndex.statistics.total_concepts "
                f"{index.statistics.total_concepts} != len(entries) {len(index.entries)}."
            ),
            processor_name="validate_concept_index",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_dependency_map(dep_map: "DependencyMap") -> ValidationResult:
    """Validate DependencyMap consistency."""
    diagnostics: List[ValidationDiagnostic] = []

    known_ids = set(dep_map.topological_order)

    for edge in dep_map.edges:
        if edge.source_node_id not in known_ids:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="MKV005",
                message=f"DependencyEdge source {edge.source_node_id!r} not in topological_order.",
                processor_name="validate_dependency_map",
            ))
        if edge.target_node_id not in known_ids:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="MKV006",
                message=f"DependencyEdge target {edge.target_node_id!r} not in topological_order.",
                processor_name="validate_dependency_map",
            ))
        if not 0.0 <= edge.confidence <= 1.0:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV007",
                message=f"DependencyEdge confidence {edge.confidence} out of [0,1].",
                processor_name="validate_dependency_map",
            ))

    if dep_map.statistics.has_cycles:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="MKV008",
            message="DependencyMap contains cycles — learning progression may not be fully ordered.",
            processor_name="validate_dependency_map",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_retrieval_index(index: "RetrievalIndex") -> ValidationResult:
    """Validate RetrievalIndex consistency."""
    diagnostics: List[ValidationDiagnostic] = []

    if not index.entries and index.outcome != CompilationOutcome.EMPTY:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="MKV009",
            message="RetrievalIndex has no entries but outcome is not EMPTY.",
            processor_name="validate_retrieval_index",
        ))

    for entry in index.entries:
        if not entry.key:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV010",
                message="IndexEntry has empty key.",
                processor_name="validate_retrieval_index",
            ))
        if entry.count != len(entry.node_ids):
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="MKV011",
                message=f"IndexEntry {entry.key!r}: count {entry.count} != len(node_ids) {len(entry.node_ids)}.",
                processor_name="validate_retrieval_index",
            ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_package(package: "MasterKnowledgePackage") -> ValidationResult:
    """
    Validate the overall MasterKnowledgePackage consistency.
    """
    diagnostics: List[ValidationDiagnostic] = []

    if not package.manifest.package_id:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="MKV012",
            message="MasterKnowledgePackage.manifest.package_id is empty.",
            processor_name="validate_package",
        ))

    if package.outcome == CompilationOutcome.ERROR:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="MKV013",
            message="MasterKnowledgePackage.outcome is ERROR.",
            processor_name="validate_package",
        ))

    stat = package.statistics
    if stat.total_concepts != len(package.concept_index.entries):
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="MKV014",
            message=(
                f"Statistics.total_concepts {stat.total_concepts} "
                f"!= len(concept_index.entries) {len(package.concept_index.entries)}."
            ),
            processor_name="validate_package",
        ))

    if stat.total_learning_steps != len(package.learning_progression.steps):
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="MKV015",
            message=(
                f"Statistics.total_learning_steps {stat.total_learning_steps} "
                f"!= len(learning_progression.steps) {len(package.learning_progression.steps)}."
            ),
            processor_name="validate_package",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


def validate_serialization(package: "MasterKnowledgePackage") -> ValidationResult:
    """Validate that the package serializes deterministically to JSON."""
    diagnostics: List[ValidationDiagnostic] = []

    try:
        d1 = json.dumps(package.to_dict(), sort_keys=True)
        d2 = json.dumps(package.to_dict(), sort_keys=True)
        if d1 != d2:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKV016",
                message="MasterKnowledgePackage serialization is NOT deterministic.",
                processor_name="validate_serialization",
            ))
    except Exception as exc:
        diagnostics.append(ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="MKV017",
            message=f"MasterKnowledgePackage serialization raised: {exc}",
            processor_name="validate_serialization",
        ))

    return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

"""
modules/knowledge_optimization/validation.py — M5.4: validation functions
reusing M5.1 ValidationResult / ValidationDiagnostic contracts.
"""
from __future__ import annotations

import json
from typing import List

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS, ValidationDiagnostic, ValidationResult,
)
from modules.knowledge_optimization.enums import OptimizationOutcome
from modules.knowledge_optimization.models import (
    LearningAnalytics, OptimizedKnowledgePackage,
    OptimizedRetrievalIndex, RuntimeCache,
)

__all__ = [
    "validate_optimized_package",
    "validate_retrieval_index",
    "validate_runtime_cache",
    "validate_analytics",
    "validate_serialization",
]


def validate_optimized_package(pkg: OptimizedKnowledgePackage) -> ValidationResult:
    diag: List[ValidationDiagnostic] = []

    if not pkg.manifest.optimized_package_id:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW001",
            "optimized_package_id is empty.", "validate_optimized_package"))

    if pkg.outcome == OptimizationOutcome.FAILED:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW002",
            "OptimizedKnowledgePackage.outcome is FAILED.", "validate_optimized_package"))

    if not pkg.source_package_id:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW003",
            "source_package_id is empty.", "validate_optimized_package"))

    if pkg.statistics.total_concepts_optimized != len(pkg.retrieval_index.entries):
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW004",
            f"Statistics.total_concepts_optimized {pkg.statistics.total_concepts_optimized} "
            f"!= len(retrieval_index.entries) {len(pkg.retrieval_index.entries)}.",
            "validate_optimized_package"))

    return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS


def validate_retrieval_index(idx: OptimizedRetrievalIndex) -> ValidationResult:
    diag: List[ValidationDiagnostic] = []

    if not idx.entries and idx.outcome != OptimizationOutcome.EMPTY:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW005",
            "OptimizedRetrievalIndex has no entries but outcome is not EMPTY.",
            "validate_retrieval_index"))

    for entry in idx.entries:
        if not entry.key:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW006",
                "OptimizedIndexEntry has empty key.", "validate_retrieval_index"))
        if entry.count != len(entry.node_ids):
            diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW007",
                f"Entry {entry.key!r}: count {entry.count} != len(node_ids) {len(entry.node_ids)}.",
                "validate_retrieval_index"))

    return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS


def validate_runtime_cache(cache: RuntimeCache) -> ValidationResult:
    diag: List[ValidationDiagnostic] = []

    if not cache.concept_lookup and cache.outcome != OptimizationOutcome.EMPTY:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW008",
            "RuntimeCache.concept_lookup is empty but outcome is not EMPTY.",
            "validate_runtime_cache"))

    if cache.total_entries != len(cache.entries):
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW009",
            f"total_entries {cache.total_entries} != len(entries) {len(cache.entries)}.",
            "validate_runtime_cache"))

    return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS


def validate_analytics(analytics: LearningAnalytics) -> ValidationResult:
    diag: List[ValidationDiagnostic] = []

    if not 0.0 <= analytics.graph_density <= 1.0:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW010",
            f"graph_density {analytics.graph_density} out of [0.0, 1.0].",
            "validate_analytics"))

    if not 0.0 <= analytics.orphan_ratio <= 1.0:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW011",
            f"orphan_ratio {analytics.orphan_ratio} out of [0.0, 1.0].",
            "validate_analytics"))

    if analytics.total_concepts_analyzed != len(analytics.per_concept):
        diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOW012",
            f"total_concepts_analyzed {analytics.total_concepts_analyzed} "
            f"!= len(per_concept) {len(analytics.per_concept)}.",
            "validate_analytics"))

    return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS


def validate_serialization(pkg: OptimizedKnowledgePackage) -> ValidationResult:
    diag: List[ValidationDiagnostic] = []
    try:
        d1 = json.dumps(pkg.to_dict(), sort_keys=True)
        d2 = json.dumps(pkg.to_dict(), sort_keys=True)
        if d1 != d2:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW013",
                "OptimizedKnowledgePackage serialization is NOT deterministic.",
                "validate_serialization"))
    except Exception as exc:
        diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOW014",
            f"to_dict() raised: {exc}", "validate_serialization"))

    return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS

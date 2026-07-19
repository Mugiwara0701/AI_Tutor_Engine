"""
modules/knowledge_optimization/package_validator.py — M5.4
Deliverable #1: Package Validation.

Validates a MasterKnowledgePackage (M5.3) for optimizer readiness.
Reuses M5.1 ValidationResult contracts.
"""
from __future__ import annotations

from typing import List, Optional, Set

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS, ValidationDiagnostic, ValidationResult,
)
from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config

__all__ = ["PackageValidator", "default_package_validator"]


class PackageValidator:
    """Validates a MasterKnowledgePackage before optimization."""

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def validate(self, package: object) -> ValidationResult:
        diag: List[ValidationDiagnostic] = []

        # Manifest
        manifest = getattr(package, "manifest", None)
        if manifest is None:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV001",
                "MasterKnowledgePackage.manifest is missing.", "PackageValidator"))
        else:
            if not getattr(manifest, "package_id", ""):
                diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV002",
                    "manifest.package_id is empty.", "PackageValidator"))
            if not getattr(manifest, "graph_id", ""):
                diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOV003",
                    "manifest.graph_id is empty.", "PackageValidator"))

        # Outcome
        outcome = getattr(package, "outcome", None)
        if outcome is not None and str(outcome.value if hasattr(outcome, "value") else outcome) == "error":
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV004",
                "MasterKnowledgePackage.outcome is ERROR — cannot optimize.", "PackageValidator"))

        # ConceptIndex
        ci = getattr(package, "concept_index", None)
        if ci is None:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV005",
                "concept_index is missing.", "PackageValidator"))
        else:
            entries = getattr(ci, "entries", ())
            if not entries:
                diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOV006",
                    "concept_index has no entries.", "PackageValidator"))
            # Uniqueness
            seen: Set[str] = set()
            for e in entries:
                nid = getattr(e, "node_id", "")
                if nid in seen:
                    diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV007",
                        f"Duplicate node_id {nid!r} in concept_index.", "PackageValidator"))
                seen.add(nid)

        # DependencyMap
        dep = getattr(package, "dependency_map", None)
        if dep is None:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOV008",
                "dependency_map is missing.", "PackageValidator"))

        # LearningProgression
        lp = getattr(package, "learning_progression", None)
        if lp is None:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.WARNING, "KOV009",
                "learning_progression is missing.", "PackageValidator"))

        # Serialization check
        try:
            package.to_dict()  # type: ignore[union-attr]
        except Exception as exc:
            diag.append(ValidationDiagnostic(DiagnosticSeverity.ERROR, "KOV010",
                f"to_dict() raised: {exc}", "PackageValidator"))

        return ValidationResult(diagnostics=tuple(diag)) if diag else SUCCESS


default_package_validator = PackageValidator()

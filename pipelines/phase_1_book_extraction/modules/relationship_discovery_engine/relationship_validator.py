"""
modules/relationship_discovery_engine/relationship_validator.py —
M5.2E Deliverable #2: Relationship Validation.

Validates individual SemanticRelationship objects and lists thereof.
Reuses M5.1's ValidationResult / ValidationDiagnostic / DiagnosticSeverity
contracts exactly — no duplication.
"""
from __future__ import annotations

from typing import FrozenSet, List, Set, Tuple

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.enums import RelationshipType
from modules.relationship_discovery_engine.models import SemanticRelationship

__all__ = [
    "RelationshipValidator",
    "default_relationship_validator",
]

_VALID_RELATIONSHIP_TYPES: FrozenSet[str] = frozenset(rt.value for rt in RelationshipType)


class RelationshipValidator:
    """
    Validates a list of SemanticRelationship objects using M5.1's
    ValidationResult / ValidationDiagnostic contracts.

    Checks:
    - Valid node references (non-empty source/target anchor_ids).
    - Valid relationship types (must be in RelationshipType enum).
    - Confidence threshold (>= config.min_relationship_confidence).
    - Duplicate detection (same relationship_id in the list).
    - Self-loop detection (source == target when allow_self_loops=False).
    """

    def __init__(
        self,
        config: RelationshipDiscoveryEngineConfig = None,
    ) -> None:
        self._cfg = config or default_config

    def validate_relationship(
        self, rel: SemanticRelationship
    ) -> ValidationResult:
        """Validate a single SemanticRelationship."""
        diagnostics: List[ValidationDiagnostic] = []

        if not rel.source_anchor_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDE001",
                message="SemanticRelationship.source_anchor_id must not be empty.",
                processor_name="RelationshipValidator",
            ))

        if not rel.target_anchor_id:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDE002",
                message="SemanticRelationship.target_anchor_id must not be empty.",
                processor_name="RelationshipValidator",
            ))

        if rel.relationship_type.value not in _VALID_RELATIONSHIP_TYPES:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDE003",
                message=(
                    f"SemanticRelationship.relationship_type "
                    f"{rel.relationship_type.value!r} is not a valid RelationshipType."
                ),
                processor_name="RelationshipValidator",
            ))

        if rel.confidence.value < self._cfg.min_relationship_confidence:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="RDE004",
                message=(
                    f"SemanticRelationship {rel.relationship_id!r} confidence "
                    f"{rel.confidence.value:.4f} is below threshold "
                    f"{self._cfg.min_relationship_confidence}."
                ),
                processor_name="RelationshipValidator",
            ))

        if (
            not self._cfg.allow_self_loops
            and rel.source_anchor_id
            and rel.target_anchor_id
            and rel.source_anchor_id == rel.target_anchor_id
        ):
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="RDE005",
                message=(
                    f"SemanticRelationship {rel.relationship_id!r} is a self-loop "
                    f"(source == target == {rel.source_anchor_id!r})."
                ),
                processor_name="RelationshipValidator",
            ))

        return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

    def validate_list(
        self, relationships: Tuple[SemanticRelationship, ...]
    ) -> ValidationResult:
        """Validate a list of SemanticRelationships (including duplicate check)."""
        diagnostics: List[ValidationDiagnostic] = []
        seen_ids: Set[str] = set()

        for rel in relationships:
            # Per-relationship validation
            vr = self.validate_relationship(rel)
            diagnostics.extend(vr.diagnostics)

            # Duplicate detection
            if rel.relationship_id in seen_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="RDE006",
                    message=(
                        f"Duplicate relationship_id {rel.relationship_id!r} detected."
                    ),
                    processor_name="RelationshipValidator",
                ))
            else:
                seen_ids.add(rel.relationship_id)

        return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


#: Module-level singleton.
default_relationship_validator = RelationshipValidator()

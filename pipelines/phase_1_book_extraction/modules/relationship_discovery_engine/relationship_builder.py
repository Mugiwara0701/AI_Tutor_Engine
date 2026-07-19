"""
modules/relationship_discovery_engine/relationship_builder.py —
M5.2E Deliverable #1 (part): Relationship Construction.

Assembles SemanticRelationship immutable models from the outputs of
RelationshipClassifier and ConfidencePropagator.

relationship_id is deterministic: UUID5 from
(RELATIONSHIP_NAMESPACE, f"{source_anchor_id}:{target_anchor_id}:{rule_key}").
"""
from __future__ import annotations

import uuid
from typing import Optional

from modules.relationship_discovery_engine.confidence_propagator import (
    ConfidencePropagator,
    default_confidence_propagator,
)
from modules.relationship_discovery_engine.exceptions import RelationshipResolutionError
from modules.relationship_discovery_engine.models import SemanticRelationship
from modules.relationship_discovery_engine.relationship_classifier import (
    ClassificationResult,
)

__all__ = [
    "RelationshipBuilder",
    "default_relationship_builder",
    "RELATIONSHIP_NAMESPACE",
]

# Stable namespace for relationship_id generation (UUID5).
# This value is fixed and must never change.
RELATIONSHIP_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")


def _deterministic_relationship_id(
    source_anchor_id: str,
    target_anchor_id: str,
    rule_key: str,
) -> str:
    name = f"{source_anchor_id}:{target_anchor_id}:{rule_key}"
    return str(uuid.uuid5(RELATIONSHIP_NAMESPACE, name))


class RelationshipBuilder:
    """
    Constructs a SemanticRelationship from a ClassificationResult.

    anchor_id values come from M5.2D's SemanticAnchor — never
    regenerated here.
    """

    def __init__(
        self,
        confidence_propagator: Optional[ConfidencePropagator] = None,
    ) -> None:
        self._propagator = confidence_propagator or default_confidence_propagator

    def build(
        self,
        source_result: object,
        target_result: object,
        classification: ClassificationResult,
    ) -> SemanticRelationship:
        """
        Build a SemanticRelationship from *source_result*,
        *target_result*, and a *classification*.
        """
        source_anchor = getattr(source_result, "anchor", None)
        target_anchor = getattr(target_result, "anchor", None)

        if source_anchor is None:
            raise RelationshipResolutionError(
                "source_result has no anchor — cannot build relationship."
            )
        if target_anchor is None:
            raise RelationshipResolutionError(
                "target_result has no anchor — cannot build relationship."
            )

        source_anchor_id: str = source_anchor.anchor_id
        target_anchor_id: str = target_anchor.anchor_id
        source_conf: float = getattr(getattr(source_anchor, "confidence", None), "value", 0.0)
        target_conf: float = getattr(getattr(target_anchor, "confidence", None), "value", 0.0)

        confidence = self._propagator.propagate(
            source_confidence=source_conf,
            target_confidence=target_conf,
            rule=classification.rule,
        )

        relationship_id = _deterministic_relationship_id(
            source_anchor_id=source_anchor_id,
            target_anchor_id=target_anchor_id,
            rule_key=classification.rule.rule_key,
        )

        return SemanticRelationship(
            relationship_id=relationship_id,
            source_anchor_id=source_anchor_id,
            target_anchor_id=target_anchor_id,
            relationship_type=classification.rule.relationship_type,
            direction=classification.rule.direction,
            confidence=confidence,
            discovery_rule=classification.rule.rule_key,
        )


#: Module-level singleton.
default_relationship_builder = RelationshipBuilder()

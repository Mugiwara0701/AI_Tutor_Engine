"""
modules/relationship_discovery_engine/relationship_classifier.py —
M5.2E Deliverable #1 (part): Relationship Type Classification.

Given a (source, target) SemanticEnrichmentResult pair, the
RelationshipClassifier looks up the appropriate RelationshipRule from
the RELATIONSHIP_RULES table and returns the classified relationship
type, direction, and rule metadata.
"""
from __future__ import annotations

from typing import Optional

from modules.relationship_discovery_engine.enums import RelationshipDirection, RelationshipType
from modules.relationship_discovery_engine.exceptions import RelationshipClassificationError
from modules.relationship_discovery_engine.rules import RelationshipRule, lookup_rule

__all__ = [
    "ClassificationResult",
    "RelationshipClassifier",
    "default_relationship_classifier",
]

_FALLBACK_RULE = RelationshipRule(
    relationship_type=RelationshipType.RELATED_TO,
    direction=RelationshipDirection.FORWARD,
    base_weight=0.30,
    rule_key="rule_fallback_related_to",
)


class ClassificationResult:
    """
    Result of classifying a single (source, target) pair.
    Mutable intermediate — not frozen (converted to SemanticRelationship
    later by RelationshipBuilder).
    """

    __slots__ = ("rule", "source_role", "target_role", "exact_match")

    def __init__(
        self,
        rule: RelationshipRule,
        source_role: str,
        target_role: str,
        exact_match: bool,
    ) -> None:
        self.rule = rule
        self.source_role = source_role
        self.target_role = target_role
        self.exact_match = exact_match


class RelationshipClassifier:
    """
    Classifies a (source, target) anchor pair by looking up the
    RELATIONSHIP_RULES table.

    Falls back to RELATED_TO for unknown role pairs.
    """

    def classify(
        self,
        source_result: object,
        target_result: object,
    ) -> ClassificationResult:
        """
        Classify the relationship between *source_result* and
        *target_result* (SemanticEnrichmentResults from M5.2D).
        """
        source_role = self._dominant_role(source_result)
        target_role = self._dominant_role(target_result)

        rule = lookup_rule(source_role, target_role)
        if rule is not None:
            return ClassificationResult(
                rule=rule,
                source_role=source_role,
                target_role=target_role,
                exact_match=True,
            )

        # No exact match — use fallback
        return ClassificationResult(
            rule=_FALLBACK_RULE,
            source_role=source_role,
            target_role=target_role,
            exact_match=False,
        )

    @staticmethod
    def _dominant_role(result: object) -> str:
        """Extract the dominant SemanticRole string from a result."""
        anchor = getattr(result, "anchor", None)
        if anchor is not None:
            role = getattr(anchor, "semantic_role", None)
            if role is not None:
                return str(role.value) if hasattr(role, "value") else str(role)

        sem_obj = getattr(result, "semantic_object", None)
        if sem_obj is not None:
            role = getattr(sem_obj, "semantic_role", None)
            if role is not None:
                return str(role.value) if hasattr(role, "value") else str(role)
            # Try interpretations
            interps = getattr(sem_obj, "interpretations", ())
            if interps:
                best = max(interps, key=lambda i: getattr(getattr(i, "confidence", None), "value", 0.0))
                role = getattr(best, "semantic_role", None)
                if role is not None:
                    return str(role.value) if hasattr(role, "value") else str(role)

        return "unknown"


#: Module-level singleton.
default_relationship_classifier = RelationshipClassifier()

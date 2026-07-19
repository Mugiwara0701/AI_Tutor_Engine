"""
modules/relationship_discovery_engine/confidence_propagator.py —
M5.2E Deliverable #3: Confidence Propagation.

Propagates confidence from M5.2D's SemanticAnchor scores through to
RelationshipConfidence.  Deterministic, evidence-based — no LLM,
no randomness.
"""
from __future__ import annotations

from typing import List, Optional

from modules.relationship_discovery_engine.exceptions import ConfidencePropagationError
from modules.relationship_discovery_engine.models import (
    RelationshipConfidence,
    RelationshipEvidence,
)
from modules.relationship_discovery_engine.rules import RelationshipRule

__all__ = [
    "ConfidencePropagator",
    "default_confidence_propagator",
]

_FALLBACK_BASE_WEIGHT = 0.30  # Used when no exact rule matched


class ConfidencePropagator:
    """
    Derives a RelationshipConfidence from:
    1. Source anchor confidence (from M5.2D).
    2. Target anchor confidence (from M5.2D).
    3. Rule base_weight (from rules.RELATIONSHIP_RULES).
    4. Optional extra evidence (e.g. from relationship hints).

    No M5.2D model is modified.
    """

    def propagate(
        self,
        *,
        source_confidence: float,
        target_confidence: float,
        rule: Optional[RelationshipRule] = None,
        extra_evidence: Optional[List[RelationshipEvidence]] = None,
    ) -> RelationshipConfidence:
        """
        Produce a RelationshipConfidence.

        Parameters
        ----------
        source_confidence:
            SemanticAnchor.confidence.value of the source object.
        target_confidence:
            SemanticAnchor.confidence.value of the target object.
        rule:
            The matched RelationshipRule (or None for fallback).
        extra_evidence:
            Additional evidence items to include.
        """
        if not 0.0 <= source_confidence <= 1.0:
            raise ConfidencePropagationError(
                f"source_confidence must be in [0.0, 1.0]; got {source_confidence!r}."
            )
        if not 0.0 <= target_confidence <= 1.0:
            raise ConfidencePropagationError(
                f"target_confidence must be in [0.0, 1.0]; got {target_confidence!r}."
            )

        base_weight = rule.base_weight if rule else _FALLBACK_BASE_WEIGHT

        evidence: List[RelationshipEvidence] = [
            RelationshipEvidence(
                label="rule_match",
                weight=0.40,
                passed=rule is not None,
                detail=f"rule_key={rule.rule_key!r}" if rule else "no matching rule; fallback",
            ),
            RelationshipEvidence(
                label="source_anchor_confidence",
                weight=0.30,
                passed=source_confidence >= 0.50,
                detail=f"source_confidence={source_confidence:.4f}",
            ),
            RelationshipEvidence(
                label="target_anchor_confidence",
                weight=0.30,
                passed=target_confidence >= 0.50,
                detail=f"target_confidence={target_confidence:.4f}",
            ),
        ]

        if extra_evidence:
            evidence.extend(extra_evidence)

        # Weighted score
        total_weight = sum(e.weight for e in evidence)
        if total_weight == 0.0:
            raw_score = 0.0
        else:
            raw_score = sum(e.weight for e in evidence if e.passed) / total_weight

        # Scale by base_weight and mean anchor confidence
        anchor_mean = (source_confidence + target_confidence) / 2.0
        final_score = round(raw_score * base_weight * (0.5 + 0.5 * anchor_mean), 4)
        final_score = min(1.0, max(0.0, final_score))

        return RelationshipConfidence(
            value=final_score,
            source_confidence=source_confidence,
            target_confidence=target_confidence,
            evidence=tuple(evidence),
        )


#: Module-level singleton.
default_confidence_propagator = ConfidencePropagator()

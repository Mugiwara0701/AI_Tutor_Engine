"""
modules/semantic_interpretation_engine/anchor_builder.py — M5.2D
Deliverable #5: Semantic Anchor Builder.

Produces deterministic SemanticAnchor instances from SemanticObject
data.  anchor_id is a UUID5 (name-based SHA-1) derived from the
object_key and the dominant semantic role, ensuring the same input
always produces the same anchor_id (fully deterministic, no randomness).
"""
from __future__ import annotations

import uuid
from typing import Optional

from modules.semantic_interpretation_engine.enums import ConfidenceLevel, SemanticRole
from modules.semantic_interpretation_engine.exceptions import SemanticAnchorError
from modules.semantic_interpretation_engine.models import (
    ConfidenceEvidence,
    ConfidenceScore,
    SemanticAnchor,
    SemanticObject,
)

__all__ = [
    "SemanticAnchorBuilder",
    "default_anchor_builder",
    "ANCHOR_NAMESPACE",
]

# Stable UUID namespace for anchor_id generation (UUID5).
# This value is fixed and must never change — changing it would
# invalidate all previously generated anchor_ids.
ANCHOR_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _deterministic_anchor_id(object_key: str, semantic_role: SemanticRole) -> str:
    """
    Produce a UUID5 from (ANCHOR_NAMESPACE, f"{object_key}:{semantic_role.value}").
    Deterministic: same inputs always produce the same output.
    """
    name = f"{object_key}:{semantic_role.value}"
    return str(uuid.uuid5(ANCHOR_NAMESPACE, name))


class SemanticAnchorBuilder:
    """
    Builds SemanticAnchor instances from SemanticObject data.

    The anchor_id is deterministic (UUID5 from object_key + semantic_role).
    """

    def build(
        self,
        semantic_object: SemanticObject,
        engine_version: str = "1.0.0",
    ) -> SemanticAnchor:
        """
        Produce a SemanticAnchor for *semantic_object*.

        Parameters
        ----------
        semantic_object:
            The fully resolved SemanticObject to anchor.
        engine_version:
            The M5.2D engine version string (used in the anchor's version field).
        """
        obj_key = getattr(semantic_object, "object_key", "")
        if not obj_key:
            raise SemanticAnchorError(
                "Cannot build SemanticAnchor: semantic_object.object_key is empty."
            )

        dominant_role = self._dominant_role(semantic_object)
        anchor_id = _deterministic_anchor_id(semantic_object.object_key, dominant_role)

        # Build anchor confidence from the SemanticObject's interpretations
        evidence = self._build_evidence(semantic_object, dominant_role)
        score = round(
            sum(e.weight for e in evidence if e.passed)
            / max(sum(e.weight for e in evidence), 1e-9),
            4,
        )
        level = self._level_for(score)

        confidence = ConfidenceScore(
            value=score,
            level=level,
            evidence=tuple(evidence),
        )

        return SemanticAnchor(
            anchor_id=anchor_id,
            semantic_role=dominant_role,
            object_reference=semantic_object.object_key,
            confidence=confidence,
            pattern_key=semantic_object.pattern_key,
            version=engine_version,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dominant_role(obj: SemanticObject) -> SemanticRole:
        """
        Select the dominant SemanticRole from the object's interpretations.

        Strategy:
        1. Use the interpretation with the highest confidence score.
        2. Exclude UNKNOWN roles if any non-UNKNOWN exists.
        3. Fall back to UNKNOWN if no interpretations exist.
        """
        if not obj.interpretations:
            return SemanticRole.UNKNOWN

        non_unknown = [
            i for i in obj.interpretations
            if i.semantic_role != SemanticRole.UNKNOWN
        ]
        candidates = non_unknown if non_unknown else list(obj.interpretations)
        best = max(candidates, key=lambda i: i.confidence.value)
        return best.semantic_role

    @staticmethod
    def _build_evidence(obj: SemanticObject, role: SemanticRole) -> list:
        evidence = []

        evidence.append(ConfidenceEvidence(
            label="role_not_unknown",
            weight=0.40,
            passed=role != SemanticRole.UNKNOWN,
            detail=f"dominant_role={role.value}",
        ))

        has_interpretations = len(obj.interpretations) > 0
        evidence.append(ConfidenceEvidence(
            label="interpretations_present",
            weight=0.35,
            passed=has_interpretations,
            detail=f"count={len(obj.interpretations)}",
        ))

        evidence.append(ConfidenceEvidence(
            label="pattern_resolved",
            weight=0.25,
            passed=obj.pattern_key is not None,
            detail=f"pattern_key={obj.pattern_key!r}",
        ))

        return evidence

    @staticmethod
    def _level_for(score: float) -> ConfidenceLevel:
        if score >= 0.80:
            return ConfidenceLevel.HIGH
        if score >= 0.50:
            return ConfidenceLevel.MEDIUM
        if score >= 0.20:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE


#: Module-level singleton.
default_anchor_builder = SemanticAnchorBuilder()

"""
modules/semantic_interpretation_engine/confidence.py — M5.2D:
Confidence evaluation logic.

Deterministic, evidence-based confidence scoring.  No randomness,
no LLM involvement.  Scores are computed from structural signals
available in M5.2C's StructuralAnalysisResult and the resolved hints.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from modules.structural_understanding_engine.enums import AnalysisOutcome

from modules.semantic_interpretation_engine.config import (
    SemanticInterpretationEngineConfig,
    default_config,
)
from modules.semantic_interpretation_engine.enums import ConfidenceLevel
from modules.semantic_interpretation_engine.exceptions import ConfidenceEvaluationError
from modules.semantic_interpretation_engine.models import (
    ConfidenceBreakdown,
    ConfidenceEvidence,
    ConfidenceScore,
)

__all__ = [
    "ConfidenceEvaluator",
    "default_confidence_evaluator",
]


def _level_for(score: float, cfg: SemanticInterpretationEngineConfig) -> ConfidenceLevel:
    if score >= cfg.high_confidence_threshold:
        return ConfidenceLevel.HIGH
    if score >= cfg.medium_confidence_threshold:
        return ConfidenceLevel.MEDIUM
    if score >= cfg.low_confidence_threshold:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NONE


def _weighted_score(evidence: List[ConfidenceEvidence]) -> float:
    """Compute a normalised score from evidence items."""
    total_weight = sum(e.weight for e in evidence)
    if total_weight == 0.0:
        return 0.0
    earned = sum(e.weight for e in evidence if e.passed)
    return round(earned / total_weight, 4)


class ConfidenceEvaluator:
    """
    Computes ConfidenceBreakdown from M5.2C's StructuralAnalysisResult
    data (passed as plain values to avoid tight coupling) and the number
    of resolved semantic interpretations.
    """

    def __init__(self, config: Optional[SemanticInterpretationEngineConfig] = None) -> None:
        self._cfg = config or default_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        *,
        analysis_outcome: AnalysisOutcome,
        present_roles: Tuple[str, ...],
        missing_roles: Tuple[str, ...],
        pattern_key: Optional[str],
        interpretation_count: int,
        has_anchor: bool,
    ) -> ConfidenceBreakdown:
        """
        Produce a ConfidenceBreakdown from structural and semantic signals.

        Parameters
        ----------
        analysis_outcome:
            The AnalysisOutcome from M5.2C's StructuralAnalysisResult.
        present_roles:
            Roles that were found during structural analysis.
        missing_roles:
            Required roles that were absent.
        pattern_key:
            The resolved pattern key (None if unrecognised).
        interpretation_count:
            Number of SemanticInterpretation entries produced.
        has_anchor:
            Whether a SemanticAnchor was built.
        """
        structural = self._structural_confidence(
            analysis_outcome=analysis_outcome,
            present_roles=present_roles,
            missing_roles=missing_roles,
            pattern_key=pattern_key,
        )
        semantic = self._semantic_confidence(
            analysis_outcome=analysis_outcome,
            interpretation_count=interpretation_count,
            present_role_count=len(present_roles),
        )
        enrichment = self._enrichment_confidence(
            structural=structural,
            semantic=semantic,
            has_anchor=has_anchor,
        )
        return ConfidenceBreakdown(
            structural=structural,
            semantic=semantic,
            enrichment=enrichment,
        )

    # ------------------------------------------------------------------
    # Internal scorers
    # ------------------------------------------------------------------

    def _structural_confidence(
        self,
        *,
        analysis_outcome: AnalysisOutcome,
        present_roles: Tuple[str, ...],
        missing_roles: Tuple[str, ...],
        pattern_key: Optional[str],
    ) -> ConfidenceScore:
        evidence: List[ConfidenceEvidence] = []

        # 1. Pattern was resolved
        evidence.append(ConfidenceEvidence(
            label="pattern_resolved",
            weight=0.35,
            passed=pattern_key is not None,
            detail=f"pattern_key={pattern_key!r}",
        ))

        # 2. Outcome is COMPLETE
        evidence.append(ConfidenceEvidence(
            label="analysis_complete",
            weight=0.35,
            passed=analysis_outcome == AnalysisOutcome.COMPLETE,
            detail=f"outcome={analysis_outcome.value}",
        ))

        # 3. No missing required roles
        evidence.append(ConfidenceEvidence(
            label="no_missing_required_roles",
            weight=0.20,
            passed=len(missing_roles) == 0,
            detail=f"missing={list(missing_roles) if missing_roles else []}",
        ))

        # 4. At least one role present
        evidence.append(ConfidenceEvidence(
            label="roles_present",
            weight=0.10,
            passed=len(present_roles) > 0,
            detail=f"present_count={len(present_roles)}",
        ))

        value = _weighted_score(evidence)
        return ConfidenceScore(
            value=value,
            level=_level_for(value, self._cfg),
            evidence=tuple(evidence),
        )

    def _semantic_confidence(
        self,
        *,
        analysis_outcome: AnalysisOutcome,
        interpretation_count: int,
        present_role_count: int,
    ) -> ConfidenceScore:
        evidence: List[ConfidenceEvidence] = []

        # 1. At least one interpretation produced
        evidence.append(ConfidenceEvidence(
            label="interpretations_produced",
            weight=0.50,
            passed=interpretation_count > 0,
            detail=f"count={interpretation_count}",
        ))

        # 2. Interpretations cover all present roles
        full_coverage = (
            interpretation_count == present_role_count
            and present_role_count > 0
        )
        evidence.append(ConfidenceEvidence(
            label="full_role_coverage",
            weight=0.30,
            passed=full_coverage,
            detail=f"interpretations={interpretation_count}, present_roles={present_role_count}",
        ))

        # 3. Analysis was not an unrecognised pattern
        evidence.append(ConfidenceEvidence(
            label="structural_basis_valid",
            weight=0.20,
            passed=analysis_outcome != AnalysisOutcome.UNRECOGNIZED_PATTERN,
            detail=f"outcome={analysis_outcome.value}",
        ))

        value = _weighted_score(evidence)
        return ConfidenceScore(
            value=value,
            level=_level_for(value, self._cfg),
            evidence=tuple(evidence),
        )

    def _enrichment_confidence(
        self,
        *,
        structural: ConfidenceScore,
        semantic: ConfidenceScore,
        has_anchor: bool,
    ) -> ConfidenceScore:
        """Overall enrichment quality is a weighted blend of structural + semantic."""
        evidence: List[ConfidenceEvidence] = []

        evidence.append(ConfidenceEvidence(
            label="structural_confidence",
            weight=0.40,
            passed=structural.value >= self._cfg.medium_confidence_threshold,
            detail=f"structural.value={structural.value}",
        ))

        evidence.append(ConfidenceEvidence(
            label="semantic_confidence",
            weight=0.40,
            passed=semantic.value >= self._cfg.medium_confidence_threshold,
            detail=f"semantic.value={semantic.value}",
        ))

        evidence.append(ConfidenceEvidence(
            label="anchor_built",
            weight=0.20,
            passed=has_anchor,
            detail="SemanticAnchor present" if has_anchor else "no anchor",
        ))

        value = _weighted_score(evidence)
        return ConfidenceScore(
            value=value,
            level=_level_for(value, self._cfg),
            evidence=tuple(evidence),
        )


#: Module-level singleton.
default_confidence_evaluator = ConfidenceEvaluator()
